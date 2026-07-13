"""
Agentic RAG tool: retrieves relevant chunks from the vector store and builds
the grounded context block + citation list the final-answer prompt is built
from. It does NOT itself generate the answer -- the router owns generation
so that "both" (RAG + SQL) questions can be answered in one pass.
"""
from typing import List, TypedDict

from app import vector_store, config

# Below this similarity score we treat retrieval as "nothing relevant found"
# rather than force-feeding the LLM a low-relevance chunk it might paraphrase
# into a hallucinated-sounding answer.
MIN_RELEVANCE = 0.15


class Citation(TypedDict):
    source: str
    section: str
    text: str


def retrieve(question: str) -> List[Citation]:
    hits = vector_store.query(question, top_k=config.RAG_TOP_K)
    relevant = [h for h in hits if h["score"] >= MIN_RELEVANCE]
    return [
        {"source": h["source"], "section": h["section"], "text": h["text"]}
        for h in relevant
    ]


def build_context_block(citations: List[Citation]) -> str:
    if not citations:
        return "(No relevant document passages were found.)"
    parts = []
    for i, c in enumerate(citations, start=1):
        parts.append(f"[{i}] {c['source']} — {c['section']}\n{c['text']}")
    return "\n\n".join(parts)
