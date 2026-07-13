"""
Central configuration for the Northwind chatbot backend.
Everything that varies between environments is read from env vars here,
so the rest of the app never touches os.environ directly.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = DATA_DIR / "docs"
ORDERS_CSV = DATA_DIR / "orders.csv"

# --- LLM ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")
ROUTER_MODEL = os.environ.get("ROUTER_MODEL", LLM_MODEL)

# --- Vector store (Chroma, local persistent, bundled MiniLM embeddings) ---
CHROMA_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", str(BASE_DIR / "chroma_db"))
CHROMA_COLLECTION = "northwind_docs"
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "4"))

# --- SQL ---
SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", str(BASE_DIR / "orders.db"))
ORDERS_TABLE = "orders"

# --- Domain fact required by the assignment brief ---
# The whole system is graded against a fixed "current date" rather than the
# real clock, so every relative-date question ("last month", "this year")
# resolves consistently regardless of when the grader actually runs it.
CURRENT_DATE = os.environ.get("CURRENT_DATE", "2026-06-15")

# --- CORS ---
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
