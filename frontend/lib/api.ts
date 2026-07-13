export type ChatEvent =
  | { type: "tool"; tool: "rag" | "sql" | "both" | "none"; reasoning: string }
  | { type: "citations"; citations: { source: string; section: string; text: string }[] }
  | {
      type: "sql";
      sql: string | null;
      columns: string[];
      rows: unknown[][];
      error: string | null;
    }
  | { type: "token"; text: string }
  | { type: "done" };

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function* streamChat(message: string): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });

  if (!res.ok || !res.body) {
    throw new Error(`Chat request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newlineIndex;
    while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);
      if (line) {
        yield JSON.parse(line) as ChatEvent;
      }
    }
  }
  if (buffer.trim()) {
    yield JSON.parse(buffer.trim()) as ChatEvent;
  }
}
