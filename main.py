import os
import uuid
import PyPDF2
from io import BytesIO
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Import agent (do this after load_dotenv)
from agent import analyze_case

app = FastAPI(title="PrecedentIQ API", version="1.0.0")

# Allow all origins for hackathon (tighten for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ── Health check ─────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "service": "PrecedentIQ"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# ── Analyze uploaded file ────────────────────────────────────────
@app.post("/analyze")
async def analyze_document(file: UploadFile = File(...)):
    """
    Accept a PDF or TXT case document.
    Run the full agent loop.
    Return a structured strategy brief.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Read file bytes
    contents = await file.read()

    # Extract text based on file type
    text = ""
    if file.filename.endswith(".pdf"):
        try:
            pdf_reader = PyPDF2.PdfReader(BytesIO(contents))
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read PDF: {e}")
    elif file.filename.endswith(".txt"):
        text = contents.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and TXT files supported"
        )

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from document")

    # Run agent
    try:
        result = analyze_case(case_text=text, filename=file.filename)
        return {
            "success": True,
            "doc_id": result["doc_id"],
            "jurisdiction": result["jurisdiction"],
            "brief": result["brief"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Analyze raw text ─────────────────────────────────────────────
class TextInput(BaseModel):
    text: str
    filename: str = "manual_input"

@app.post("/analyze-text")
async def analyze_text(body: TextInput):
    """Accept raw text input instead of file upload."""
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text provided")
    try:
        result = analyze_case(case_text=body.text, filename=body.filename)
        return {
            "success": True,
            "doc_id": result["doc_id"],
            "jurisdiction": result["jurisdiction"],
            "brief": result["brief"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Get memory stats ─────────────────────────────────────────────
@app.get("/memory/stats")
def memory_stats():
    """Return how many strategy briefs are stored in agent memory."""
    from elastic_tools import es
    try:
        count = es.count(index="precedentiq_memory")["count"]
        doc_count = es.count(index="precedentiq_documents")["count"]
        case_count = es.count(index="precedentiq_cases")["count"]
        return {
            "strategy_briefs_in_memory": count,
            "documents_analyzed": doc_count,
            "cases_indexed": case_count
        }
    except Exception as e:
        return {"error": str(e)}