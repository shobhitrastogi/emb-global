"""
Vector store for the unstructured knowledge base (HR leave policy, product
FAQ, returns policy, warranty policy, pricing policy).

Choice: Chroma, running embedded/local with its bundled ONNX MiniLM
embedding function. Rationale is in the README, but in short: this is a
five-document, fixed, offline dataset -- there is no need for a managed
service like Pinecone, and Chroma's default embedder means the system works
out of the box with only an LLM key (no separate embeddings API key/cost).
"""
import re
from pathlib import Path
from typing import List, TypedDict

import chromadb

from app import config


class Chunk(TypedDict):
    id: str
    text: str
    source: str
    section: str


_client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
_collection = _client.get_or_create_collection(name=config.CHROMA_COLLECTION)


def _chunk_markdown(path: Path) -> List[Chunk]:
    """Split a markdown doc into chunks along '## ' section headings.
    Small, heading-bounded chunks keep citations precise (policy docs are
    short enough that whole-section chunks work better than fixed windows)."""
    text = path.read_text(encoding="utf-8")
    title_match = re.match(r"#\s+(.*)", text)
    doc_title = title_match.group(1).strip() if title_match else path.stem

    sections = re.split(r"\n(?=## )", text)
    chunks: List[Chunk] = []
    for i, section in enumerate(sections):
        section = section.strip()
        if not section or section.startswith("# "):
            # drop the bare H1 title-only fragment, keep everything else
            if section.startswith("# ") and "\n" not in section:
                continue
        heading_match = re.match(r"##\s+(.*)", section)
        section_title = heading_match.group(1).strip() if heading_match else doc_title
        chunks.append(
            {
                "id": f"{path.stem}-{i}",
                "text": section,
                "source": doc_title,
                "section": section_title,
            }
        )
    return chunks


def ingest_all(docs_dir: Path = config.DOCS_DIR) -> int:
    """(Re)ingest every markdown doc in docs_dir into the collection.
    Idempotent: clears and rebuilds so re-running is safe."""
    existing = _collection.get()
    if existing["ids"]:
        _collection.delete(ids=existing["ids"])

    all_chunks: List[Chunk] = []
    for path in sorted(docs_dir.glob("*.md")):
        all_chunks.extend(_chunk_markdown(path))

    if not all_chunks:
        return 0

    _collection.add(
        ids=[c["id"] for c in all_chunks],
        documents=[c["text"] for c in all_chunks],
        metadatas=[{"source": c["source"], "section": c["section"]} for c in all_chunks],
    )
    return len(all_chunks)


def query(text: str, top_k: int = config.RAG_TOP_K) -> List[dict]:
    """Return top_k chunks most relevant to `text`, each with its citation
    metadata (source document + section)."""
    if _collection.count() == 0:
        ingest_all()
    results = _collection.query(query_texts=[text], n_results=top_k)
    out = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        out.append(
            {
                "text": doc,
                "source": meta["source"],
                "section": meta["section"],
                "score": 1 - dist,  # cosine distance -> similarity
            }
        )
    return out
