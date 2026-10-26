"""A small local RAG retriever using TF-IDF and cosine similarity.

This keeps the MVP fast to install and run without a vector-database server.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}


def split_into_chunks(text: str, max_chars: int = 1000, overlap: int = 140) -> list[str]:
    """Split text into overlapping chunks while preferring word boundaries."""
    text = re.sub(r"\r\n?", "\n", text).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + max_chars, text_length)
        if end < text_length:
            preferred = text.rfind("\n", start + int(max_chars * 0.6), end)
            if preferred < start + int(max_chars * 0.5):
                preferred = text.rfind(" ", start + int(max_chars * 0.6), end)
            if preferred > start:
                end = preferred
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= text_length:
            break
        start = max(end - overlap, start + 1)
    return chunks


class KnowledgeBase:
    """In-memory lexical retriever over local Markdown, TXT, and PDF files."""

    def __init__(self, roots: Iterable[Path] | None = None) -> None:
        self.roots = [Path(root) for root in (roots or [])]
        self.chunks: list[dict] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None
        self.reload()

    def _source_name(self, path: Path) -> str:
        for root in self.roots:
            try:
                relative = path.resolve().relative_to(root.resolve())
                if root.name == "uploads":
                    return f"uploads/{relative.as_posix()}"
                return relative.as_posix()
            except ValueError:
                continue
        return path.name

    def _append_text(self, text: str, source: str, page: int | None = None) -> None:
        for index, chunk in enumerate(split_into_chunks(text)):
            self.chunks.append(
                {
                    "text": chunk,
                    "source": source,
                    "page": page,
                    "chunk_index": index,
                }
            )

    def reload(self) -> int:
        """Re-read files and rebuild the retrieval matrix."""
        self.chunks = []
        for root in self.roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                source = self._source_name(path)
                try:
                    if path.suffix.lower() == ".pdf":
                        reader = PdfReader(str(path))
                        for page_number, page in enumerate(reader.pages, start=1):
                            self._append_text(page.extract_text() or "", source, page_number)
                    else:
                        self._append_text(path.read_text(encoding="utf-8", errors="ignore"), source)
                except Exception:
                    # A single malformed upload should not prevent the rest of the corpus loading.
                    continue

        if self.chunks:
            self.vectorizer = TfidfVectorizer(
                lowercase=True,
                ngram_range=(1, 2),
                max_features=50000,
                token_pattern=r"(?u)\b\w+\b",
                sublinear_tf=True,
            )
            self.matrix = self.vectorizer.fit_transform([chunk["text"] for chunk in self.chunks])
        else:
            self.vectorizer = None
            self.matrix = None
        return len(self.chunks)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    def sources(self) -> list[str]:
        return sorted({chunk["source"] for chunk in self.chunks})

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Return relevant chunks with source metadata and a similarity score."""
        if not query.strip() or self.vectorizer is None or self.matrix is None:
            return []
        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self.matrix).ravel()
        ranked_indices = scores.argsort()[::-1]
        results = []
        for index in ranked_indices:
            score = float(scores[index])
            if score <= 0:
                continue
            chunk = self.chunks[int(index)]
            results.append(
                {
                    **chunk,
                    "score": round(score, 4),
                    "citation": (
                        f'{chunk["source"]}, p. {chunk["page"]}'
                        if chunk["page"] is not None
                        else chunk["source"]
                    ),
                }
            )
            if len(results) >= max(1, top_k):
                break
        return results
