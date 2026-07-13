"""
Text-to-SQL tool for the structured knowledge source (orders table).

The orders data is deliberately NOT embedded for vector search -- the agent
writes and executes a real SQL query against it, per the assignment brief.
"""
import csv
import re
import sqlite3
from pathlib import Path
from typing import List, Tuple

from app import config, llm_client

SCHEMA_DESCRIPTION = """\
Table: orders
Columns:
  order_id    TEXT    -- e.g. 'ORD-1001', primary key
  customer    TEXT    -- customer full name
  product     TEXT    -- product name, e.g. 'Mechanical Keyboard', 'USB-C Hub'
  amount      REAL    -- order amount in INR
  status      TEXT    -- one of: pending, processing, shipped, delivered, returned, cancelled
  order_date  TEXT    -- ISO date 'YYYY-MM-DD'
"""

# Only SELECT statements against the whitelisted table are ever executed.
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|PRAGMA|REPLACE|TRUNCATE|VACUUM)\b",
    re.IGNORECASE,
)


def init_db(csv_path: Path = config.ORDERS_CSV, db_path: str = config.SQLITE_DB_PATH) -> None:
    """Load orders.csv into a local SQLite file. Idempotent: drops and
    recreates the table so re-running (e.g. on container start) is safe."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {config.ORDERS_TABLE}")
    cur.execute(
        f"""CREATE TABLE {config.ORDERS_TABLE} (
            order_id TEXT PRIMARY KEY,
            customer TEXT,
            product TEXT,
            amount REAL,
            status TEXT,
            order_date TEXT
        )"""
    )
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            (r["order_id"], r["customer"], r["product"], float(r["amount"]), r["status"], r["order_date"])
            for r in reader
        ]
    cur.executemany(
        f"INSERT INTO {config.ORDERS_TABLE} VALUES (?, ?, ?, ?, ?, ?)", rows
    )
    conn.commit()
    conn.close()


def _validate(sql: str) -> None:
    stripped = sql.strip().rstrip(";")
    if not re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        raise ValueError("Only SELECT statements are permitted.")
    if _FORBIDDEN.search(stripped):
        raise ValueError("Query contains a disallowed keyword.")
    if config.ORDERS_TABLE not in stripped.lower():
        raise ValueError(f"Query must reference the '{config.ORDERS_TABLE}' table.")
    if ";" in stripped:
        raise ValueError("Multiple statements are not permitted.")


SQL_SYSTEM_PROMPT = f"""You are a SQL generation assistant for a SQLite database.
Today's date (treat as "now" for any relative date question) is {config.CURRENT_DATE}.

{SCHEMA_DESCRIPTION}

Rules:
- Output ONLY a single SQLite SELECT statement. No prose, no markdown fences, no explanation.
- Use ONLY the columns listed above. Never invent columns or tables.
- If the question cannot be answered with this schema, output exactly: NO_QUERY
- Use standard SQLite date functions (date(), strftime()) for date logic, anchored on '{config.CURRENT_DATE}' rather than SQLite's own current date.
"""


async def generate_sql(question: str) -> str:
    raw = await llm_client.complete(SQL_SYSTEM_PROMPT, question, max_tokens=300)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(sql)?", "", cleaned).strip()
        cleaned = cleaned.rstrip("`").strip()
    return cleaned


def execute_sql(sql: str, db_path: str = config.SQLITE_DB_PATH) -> Tuple[List[str], List[tuple]]:
    _validate(sql)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(sql)
    columns = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    conn.close()
    return columns, rows


async def run(question: str) -> dict:
    """Full text-to-SQL pipeline: generate -> validate -> execute.
    Returns a dict the router can drop straight into the answer-generation
    context and the frontend can render as-is."""
    sql = await generate_sql(question)
    if sql.strip().upper() == "NO_QUERY":
        return {"sql": None, "columns": [], "rows": [], "error": None}
    try:
        columns, rows = execute_sql(sql)
        return {"sql": sql, "columns": columns, "rows": rows, "error": None}
    except Exception as exc:  # noqa: BLE001 - surfaced to the LLM, not the user
        return {"sql": sql, "columns": [], "rows": [], "error": str(exc)}
