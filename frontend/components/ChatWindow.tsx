"use client";

import { useRef, useState } from "react";
import { streamChat } from "@/lib/api";
import MessageBubble, { Message } from "./MessageBubble";

const SUGGESTIONS = [
  "What is the refund window?",
  "How many orders are pending?",
  "Our policy allows 30-day returns; did order ORD-1002 qualify?",
];

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;

    setInput("");
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", text: question },
      { role: "assistant", text: "", pending: true },
    ]);

    try {
      for await (const event of streamChat(question)) {
        setMessages((prev) => {
          const updated = [...prev];
          const last = { ...updated[updated.length - 1] };

          if (event.type === "tool") {
            last.tool = event.tool;
          } else if (event.type === "citations") {
            last.citations = event.citations;
          } else if (event.type === "sql") {
            last.sql = { sql: event.sql, columns: event.columns, rows: event.rows, error: event.error };
          } else if (event.type === "token") {
            last.text = (last.text ?? "") + event.text;
          } else if (event.type === "done") {
            last.pending = false;
          }

          updated[updated.length - 1] = last;
          return updated;
        });
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          text: "Something went wrong reaching the server. Please try again.",
          pending: false,
        };
        return updated;
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chat-window">
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <p>Ask about Northwind Gadgets policies or your orders.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} msg={m} />
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        className="input-row"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question..."
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
