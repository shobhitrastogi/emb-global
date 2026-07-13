import json
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app import config, router, schemas, sql_tool, vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("northwind")

app = FastAPI(title="Northwind Gadgets Support Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    """Build the vector index and SQLite table if they don't exist yet, so a
    fresh container (or a fresh Chroma volume) is immediately queryable."""
    try:
        if vector_store._collection.count() == 0:
            n = vector_store.ingest_all()
            logger.info("Ingested %d document chunks", n)
    except Exception:  # noqa: BLE001
        logger.exception("Vector store ingestion failed")
    try:
        sql_tool.init_db()
        logger.info("Orders table loaded")
    except Exception:  # noqa: BLE001
        logger.exception("SQLite ingestion failed")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(req: schemas.ChatRequest):
    """Streams newline-delimited JSON events: tool selection, citations/SQL,
    then the answer token by token, then a final 'done' event."""

    async def event_stream():
        async for event in router.handle(req.message):
            yield json.dumps(event) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
