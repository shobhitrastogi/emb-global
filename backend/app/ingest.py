"""
Run once (or on every container start -- both are idempotent) to build the
vector index and the SQLite orders table from the files in data/.

    python -m app.ingest
"""
from app import sql_tool, vector_store


def main() -> None:
    n_chunks = vector_store.ingest_all()
    print(f"[ingest] indexed {n_chunks} document chunks into Chroma")
    sql_tool.init_db()
    print("[ingest] loaded orders.csv into SQLite")


if __name__ == "__main__":
    main()
