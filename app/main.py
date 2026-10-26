"""FastAPI backend for EduDesk AI."""
from __future__ import annotations

import io
import re
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from pypdf import PdfReader

from app import database
from app.agent import answer_with_agent
from app.config import GEMINI_API_KEY, KNOWLEDGE_DIR, MAX_UPLOAD_BYTES, UPLOAD_DIR
from app.knowledge_base import KnowledgeBase

KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
knowledge_base = KnowledgeBase([KNOWLEDGE_DIR, UPLOAD_DIR])

app = FastAPI(
    title="EduDesk AI API",
    description="RAG-powered student support assistant with controlled SQLite tools.",
    version="0.1.0",
)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    student_id: str = Field(default="SV001", min_length=1, max_length=20)
    message: str = Field(min_length=1, max_length=3000)
    history: list[ChatTurn] = Field(default_factory=list)


@app.on_event("startup")
def on_startup() -> None:
    database.init_db()
    knowledge_base.reload()


@app.get("/")
def root() -> dict:
    return {
        "name": "EduDesk AI API",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/api/v1/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_configured": bool(GEMINI_API_KEY),
        "mode": "gemini" if GEMINI_API_KEY else "demo_fallback",
        "retrieval_chunks": knowledge_base.chunk_count,
        "documents": knowledge_base.sources(),
    }


@app.get("/api/v1/courses")
def courses() -> dict:
    database.init_db()
    return {"courses": database.get_courses()}


@app.get("/api/v1/tickets")
def tickets(
    student_id: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    database.init_db()
    return {"tickets": database.list_tickets(student_id=student_id, limit=limit)}


@app.get("/api/v1/documents")
def documents() -> dict:
    return {"documents": knowledge_base.sources(), "chunks": knowledge_base.chunk_count}


@app.post("/api/v1/chat")
def chat(request: ChatRequest) -> dict:
    database.init_db()
    student_id = request.student_id.strip().upper()
    if not database.get_student(student_id):
        raise HTTPException(status_code=404, detail="Student ID not found. Try SV001, SV002, or SV003.")

    request_id = str(uuid.uuid4())
    retrieved = knowledge_base.search(request.message, top_k=5)
    result = answer_with_agent(
        message=request.message.strip(),
        student_id=student_id,
        history=[turn.model_dump() for turn in request.history[-6:]],
        retrieved=retrieved,
        request_id=request_id,
    )
    return {
        "request_id": request_id,
        "answer": result["answer"],
        "mode": result["mode"],
        "warning": result.get("warning"),
        "sources": retrieved,
        "tool_calls": database.list_tool_events(request_id),
    }


@app.post("/api/v1/documents/upload")
async def upload_document(file: UploadFile = File(...)) -> dict:
    filename = Path(file.filename or "document").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".md", ".txt"}:
        raise HTTPException(status_code=400, detail="Only PDF, Markdown, and TXT files are supported.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {limit_mb} MB.")

    if suffix == ".pdf":
        try:
            PdfReader(io.BytesIO(content))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="This PDF could not be read.") from exc

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._") or "document"
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    destination = UPLOAD_DIR / unique_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)

    chunk_count = knowledge_base.reload()
    return {
        "success": True,
        "filename": unique_name,
        "total_indexed_chunks": chunk_count,
        "message": "Document saved and added to the local retrieval index.",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
