"use client";

import { ChatEvent } from "@/lib/api";

export type Message = {
  role: "user" | "assistant";
  text: string;
  tool?: "rag" | "sql" | "both" | "none";
  citations?: { source: string; section: string; text: string }[];
  sql?: { sql: string | null; columns: string[]; rows: unknown[][]; error: string | null };
  pending?: boolean;
};

const TOOL_LABEL: Record<string, string> = {
  rag: "Document search",
  sql: "Order data query",
  both: "Document search + Order data query",
  none: "No source used",
};

export default function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={`bubble-row ${isUser ? "user" : "assistant"}`}>
      <div className={`bubble ${isUser ? "user" : "assistant"}`}>
        {!isUser && msg.tool && (
          <div className="tool-badge">{TOOL_LABEL[msg.tool] ?? msg.tool}</div>
        )}

        <div className="bubble-text">
          {msg.text}
          {msg.pending && <span className="cursor">▍</span>}
        </div>

        {!isUser && msg.sql?.sql && (
          <details className="detail-block">
            <summary>Generated SQL</summary>
            <pre>{msg.sql.sql}</pre>
            {msg.sql.error && <p className="error-text">Error: {msg.sql.error}</p>}
          </details>
        )}

        {!isUser && msg.citations && msg.citations.length > 0 && (
          <details className="detail-block">
            <summary>Citations ({msg.citations.length})</summary>
            <ul>
              {msg.citations.map((c, i) => (
                <li key={i}>
                  <strong>
                    {c.source} — {c.section}
                  </strong>
                  <p>{c.text}</p>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}
