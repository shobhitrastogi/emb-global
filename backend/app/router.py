"""
The agent's routing brain.

Per the assignment, one chatbot must decide per-question whether to use
vector RAG over documents, text-to-SQL over the orders table, both, or
neither (safe fallback). This module makes that decision, calls the
relevant tool(s), and then streams a final answer that is grounded only in
what the tools returned.
"""
from typing import AsyncGenerator, Literal

from app import llm_client, rag_tool, sql_tool, config

Tool = Literal["rag", "sql", "both", "none"]

ROUTER_SYSTEM_PROMPT = """You are the routing component of a customer-support chatbot for \
"Northwind Gadgets". You do not answer the question yourself -- you only decide which \
data source(s) are needed to answer it.

Available sources:
- "rag": company policy documents (HR leave policy, product FAQ, returns & refunds policy, \
warranty policy, pricing & discounts policy). Use for questions about policy, rules, windows, \
eligibility, definitions, how-things-work.
- "sql": a structured `orders` table (order_id, customer, product, amount, status, order_date). \
Use for questions about specific orders, counts, sums, revenue, statuses, dates of orders.
- "both": the question requires combining a policy rule with specific order data \
(e.g. "did order X qualify for a return under our policy?").
- "none": the question is out of scope for Northwind Gadgets entirely (small talk, unrelated \
topics, or asks for information neither source could ever contain).

Respond with ONLY a JSON object: {"tool": "rag" | "sql" | "both" | "none", "reasoning": "<one short sentence>"}
"""

ANSWER_SYSTEM_PROMPT = f"""You are the customer-support assistant for "Northwind Gadgets".
Treat {config.CURRENT_DATE} as today's date for any relative-time reasoning.

Answer the user's question using ONLY the CONTEXT provided below. Do not use outside knowledge \
about warranties, returns, or orders -- if the context doesn't contain the answer, say so plainly \
rather than guessing.

Rules:
- If DOCUMENT CONTEXT is present, ground policy claims in it and reference which document/section \
  you drew from in plain language (e.g. "According to the Returns Policy...").
- If SQL RESULT is present, use those exact rows/values -- do not recompute or estimate differently.
- If both are present, combine them into one coherent answer.
- If the context is empty or says no relevant information was found, respond exactly with: \
"I don't have that information."
- Never invent policy text, numbers, order IDs, or column names that are not in the context.
- Be concise and direct.
"""


async def decide_tool(question: str) -> dict:
    try:
        return await llm_client.complete_json(ROUTER_SYSTEM_PROMPT, question, max_tokens=200)
    except Exception:  # noqa: BLE001
        return {"tool": "none", "reasoning": "routing failed, falling back to safe response"}


async def handle(question: str) -> AsyncGenerator[dict, None]:
    """Orchestrates one full turn. Yields dict events consumed by the API
    layer and serialised to the client as newline-delimited JSON:
      {"type": "tool", ...}       -- which tool(s) were selected
      {"type": "citations", ...}  -- RAG citations, if any
      {"type": "sql", ...}        -- generated SQL + result, if any
      {"type": "token", "text": ...} -- streamed answer tokens
      {"type": "done"}
    """
    decision = await decide_tool(question)
    tool: Tool = decision.get("tool", "none")
    if tool not in ("rag", "sql", "both", "none"):
        tool = "none"

    yield {"type": "tool", "tool": tool, "reasoning": decision.get("reasoning", "")}

    context_blocks = []

    if tool in ("rag", "both"):
        citations = rag_tool.retrieve(question)
        yield {"type": "citations", "citations": citations}
        context_blocks.append("DOCUMENT CONTEXT:\n" + rag_tool.build_context_block(citations))

    if tool in ("sql", "both"):
        sql_result = await sql_tool.run(question)
        yield {"type": "sql", **sql_result}
        if sql_result["sql"] is None:
            context_blocks.append("SQL RESULT: (no query could be formed for this question)")
        elif sql_result["error"]:
            context_blocks.append(f"SQL RESULT: query failed ({sql_result['error']})")
        else:
            context_blocks.append(
                "SQL RESULT:\n"
                f"Query: {sql_result['sql']}\n"
                f"Columns: {sql_result['columns']}\n"
                f"Rows: {sql_result['rows']}"
            )

    if tool == "none":
        context_blocks.append(
            "No document or order-data source is applicable to this question."
        )

    context = "\n\n".join(context_blocks)
    user_prompt = f"QUESTION: {question}\n\nCONTEXT:\n{context}"

    async for token in llm_client.stream(ANSWER_SYSTEM_PROMPT, user_prompt, max_tokens=600):
        yield {"type": "token", "text": token}

    yield {"type": "done"}
