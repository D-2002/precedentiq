import os
import uuid
from datetime import datetime
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

load_dotenv()

es = Elasticsearch(
    os.environ["ELASTIC_CLOUD_URL"],
    api_key=os.environ["ELASTIC_API_KEY"]
)

# ── Tool 1: Search case law ──────────────────────────────────────
def search_case_law(query: str, jurisdiction: str = None, limit: int = 10):
    """Search indexed legal precedents by legal concepts or fact patterns."""
    must = [{"multi_match": {
        "query": query,
        "fields": ["full_text", "title", "charge_types"],
        "type": "best_fields"
    }}]

    filters = []
    if jurisdiction:
        filters.append({"term": {"jurisdiction": jurisdiction}})

    body = {
        "query": {
            "bool": {
                "must": must,
                "filter": filters
            }
        },
        "_source": [
            "title", "court", "year", "citation",
            "jurisdiction", "charge_types", "source_url", "summary"
        ],
        "size": limit
    }

    resp = es.search(index="precedentiq_cases", body=body)
    hits = resp["hits"]["hits"]

    results = []
    for h in hits:
        s = h["_source"]
        results.append({
            "title":        s.get("title", ""),
            "court":        s.get("court", ""),
            "year":         s.get("year", ""),
            "citation":     s.get("citation", ""),
            "jurisdiction": s.get("jurisdiction", ""),
            "charge_types": s.get("charge_types", []),
            "source_url":   s.get("source_url", ""),
            "summary":      s.get("summary", "")[:300]
        })

    return results

# ── Tool 2: Search memory ────────────────────────────────────────
def search_memory(query: str, limit: int = 3):
    """Search past strategy briefs for similar cases."""
    body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["full_brief", "charge_types", "case_title"]
            }
        },
        "_source": [
            "case_title", "jurisdiction", "charge_types",
            "weak_arguments", "top_precedents", "created_at", "full_brief"
        ],
        "size": limit
    }

    resp = es.search(index="precedentiq_memory", body=body)
    hits = resp["hits"]["hits"]

    return [h["_source"] for h in hits]

# ── Tool 3: Get case stats ───────────────────────────────────────
def get_case_stats(jurisdiction: str = None):
    """Get statistics about indexed cases."""
    body = {
        "size": 0,
        "aggs": {
            "by_jurisdiction": {
                "terms": {"field": "jurisdiction"},
                "aggs": {
                    "by_year": {
                        "date_histogram": {
                            "field": "indexed_at",
                            "calendar_interval": "year"
                        }
                    }
                }
            }
        }
    }

    if jurisdiction:
        body["query"] = {"term": {"jurisdiction": jurisdiction}}

    resp = es.search(index="precedentiq_cases", body=body)
    total = resp["hits"]["total"]["value"]
    buckets = resp["aggregations"]["by_jurisdiction"]["buckets"]

    return {
        "total_cases": total,
        "by_jurisdiction": [
            {"jurisdiction": b["key"], "count": b["doc_count"]}
            for b in buckets
        ]
    }

# ── Tool 4: Save to memory ───────────────────────────────────────
def save_to_memory(
    doc_id: str,
    case_title: str,
    jurisdiction: str,
    charge_types: list,
    top_precedents: str,
    weak_arguments: str,
    missing_evidence: str,
    full_brief: str
):
    """Save a completed strategy brief to agent memory."""
    memory_id = str(uuid.uuid4())

    doc = {
        "memory_id":        memory_id,
        "doc_id":           doc_id,
        "case_title":       case_title,
        "jurisdiction":     jurisdiction,
        "charge_types":     charge_types,
        "top_precedents":   top_precedents,
        "weak_arguments":   weak_arguments,
        "missing_evidence": missing_evidence,
        "full_brief":       full_brief,
        "precedent_count":  len(top_precedents.split("\n")),
        "created_at":       datetime.utcnow().isoformat()
    }

    es.index(index="precedentiq_memory", id=memory_id, body=doc)
    return {"memory_id": memory_id, "status": "saved"}

# ── Tool 5: Store uploaded document ─────────────────────────────
def store_document(doc_id: str, filename: str, raw_text: str, jurisdiction: str):
    """Store an uploaded case document."""
    doc = {
        "doc_id":       doc_id,
        "filename":     filename,
        "raw_text":     raw_text[:50000],
        "jurisdiction": jurisdiction,
        "uploaded_at":  datetime.utcnow().isoformat(),
        "status":       "pending"
    }
    es.index(index="precedentiq_documents", id=doc_id, body=doc)
    return {"doc_id": doc_id, "status": "stored"}