import os
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

load_dotenv()

es = Elasticsearch(
    os.environ["ELASTIC_CLOUD_URL"],
    api_key=os.environ["ELASTIC_API_KEY"]
)

INDEX_NAME = "precedentiq_cases"
CL_TOKEN = os.environ.get("COURTLISTENER_TOKEN", "")

# ── 1. Create index ──────────────────────────────────────────────
def create_index():
    if es.indices.exists(index=INDEX_NAME):
        print(f"Index '{INDEX_NAME}' already exists, skipping creation.")
        return
    es.indices.create(
        index=INDEX_NAME,
        body={
            "mappings": {
                "properties": {
                    "case_id":       {"type": "keyword"},
                    "title":         {"type": "text"},
                    "full_text":     {"type": "text"},
                    "summary":       {"type": "text"},
                    "jurisdiction":  {"type": "keyword"},
                    "court":         {"type": "keyword"},
                    "year":          {"type": "integer"},
                    "outcome":       {"type": "keyword"},
                    "charge_types":  {"type": "keyword"},
                    "citation":      {"type": "keyword"},
                    "source_url":    {"type": "keyword"},
                    "indexed_at":    {"type": "date"}
                }
            }
        }
    )
    print(f"Index '{INDEX_NAME}' created successfully.")

# ── 2. Fetch from CourtListener ──────────────────────────────────
def fetch_courtlistener(query, max_docs=40):
    print(f"\nFetching US cases: '{query}'...")
    docs = []

    headers = {
        "Authorization": f"Token {CL_TOKEN}",
        "User-Agent": "PrecedentIQ/1.0 (hackathon)"
    }
    params = {
        "q": query,
        "type": "o",
        "order_by": "score desc",
        "format": "json"
    }

    try:
        resp = requests.get(
            "https://www.courtlistener.com/api/rest/v4/search/",
            params=params,
            headers=headers,
            timeout=20
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        print(f"  Got {len(results)} results")

        for r in results[:max_docs]:
            # Text is nested inside opinions array
            opinions = r.get("opinions", [])
            snippet = ""
            if opinions:
                snippet = opinions[0].get("snippet", "") or ""

            # Also try top-level snippet as fallback
            if not snippet:
                snippet = r.get("snippet", "") or ""

            # Skip if truly empty
            if not snippet or len(snippet.strip()) < 20:
                continue

            full_text = snippet[:8000]

            date_str = r.get("dateFiled") or "2000-01-01"
            try:
                year = int(date_str[:4])
            except:
                year = 2000

            citations = r.get("citation", [])
            citation = citations[0] if citations else ""

            docs.append({
                "case_id":      f"CL-{r.get('cluster_id', r.get('id', ''))}",
                "title":        r.get("caseName") or r.get("caseNameFull") or "Untitled",
                "full_text":    full_text,
                "summary":      full_text[:500],
                "jurisdiction": "US",
                "court":        r.get("court", ""),
                "year":         year,
                "outcome":      "unknown",
                "charge_types": [query],
                "citation":     citation,
                "source_url":   f"https://www.courtlistener.com{r.get('absolute_url', '')}",
                "indexed_at":   datetime.utcnow().isoformat()
            })

    except requests.exceptions.HTTPError as e:
        print(f"  HTTP Error: {e.response.status_code} — {e.response.text[:200]}")
    except Exception as e:
        print(f"  Error: {e}")

    print(f"  Prepared {len(docs)} docs")
    return docs

# ── 3. Bulk index ────────────────────────────────────────────────
def bulk_index(docs):
    if not docs:
        print("  No docs to index, skipping.")
        return
    actions = [
        {"_index": INDEX_NAME, "_id": d["case_id"], "_source": d}
        for d in docs
    ]
    success, errors = bulk(es, actions, raise_on_error=False)
    print(f"  Indexed {success} docs. Errors: {len(errors) if errors else 0}")

# ── 4. Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    create_index()

    queries = [
        "wrongful termination employment discrimination",
        "contract breach damages",
        "securities fraud insider trading",
        "intellectual property trademark infringement",
        "medical malpractice negligence",
        "criminal fraud white collar",
        "landlord tenant lease dispute",
        "personal injury negligence",
        "divorce custody settlement",
        "police misconduct civil rights",
    ]

    for query in queries:
        docs = fetch_courtlistener(query, max_docs=40)
        bulk_index(docs)
        time.sleep(13)

    count = es.count(index=INDEX_NAME)
    print(f"\nDone! Total docs in Elastic: {count['count']}")