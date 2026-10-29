import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv()

es = Elasticsearch(
    os.environ["ELASTIC_CLOUD_URL"],
    api_key=os.environ["ELASTIC_API_KEY"]
)

def create_index(name, mappings):
    if es.indices.exists(index=name):
        print(f"  '{name}' already exists, skipping.")
        return
    es.indices.create(index=name, body={"mappings": mappings})
    print(f"  '{name}' created.")

# ── Index 2: Private uploaded documents ─────────────────────────
create_index("precedentiq_documents", {
    "properties": {
        "doc_id":        {"type": "keyword"},
        "filename":      {"type": "keyword"},
        "raw_text":      {"type": "text"},
        "jurisdiction":  {"type": "keyword"},   # auto-detected
        "uploaded_at":   {"type": "date"},
        "status":        {"type": "keyword"}    # pending / analyzed
    }
})

# ── Index 3: Agent memory (strategy briefs) ──────────────────────
create_index("precedentiq_memory", {
    "properties": {
        "memory_id":        {"type": "keyword"},
        "doc_id":           {"type": "keyword"},   # links to uploaded doc
        "case_title":       {"type": "text"},
        "jurisdiction":     {"type": "keyword"},
        "charge_types":     {"type": "keyword"},
        "top_precedents":   {"type": "text"},      # serialized list
        "weak_arguments":   {"type": "text"},
        "missing_evidence": {"type": "text"},
        "full_brief":       {"type": "text"},      # complete strategy brief
        "precedent_count":  {"type": "integer"},
        "created_at":       {"type": "date"}
    }
})

# ── Index 4: Extracted structured facts ─────────────────────────
create_index("precedentiq_facts", {
    "properties": {
        "fact_id":          {"type": "keyword"},
        "doc_id":           {"type": "keyword"},
        "parties":          {"type": "text"},
        "jurisdiction":     {"type": "keyword"},
        "court_level":      {"type": "keyword"},   # high court / supreme / district
        "charge_types":     {"type": "keyword"},
        "key_clauses":      {"type": "text"},
        "dates":            {"type": "text"},
        "claimed_damages":  {"type": "text"},
        "weak_points":      {"type": "text"},      # Gemini-identified weaknesses
        "extracted_at":     {"type": "date"}
    }
})

print("\nAll indexes ready.")

# Verify
for idx in ["precedentiq_cases", "precedentiq_documents",
            "precedentiq_memory", "precedentiq_facts"]:
    count = es.count(index=idx)["count"]
    print(f"  {idx}: {count} docs")