"use client";

import { FormEvent, useState } from "react";
import { chat, type Citation } from "../lib/api";

type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || loading) {
      return;
    }

    setMessages((current) => [...current, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    try {
      const response = await chat(text, conversationId);
      setMessages((current) => [
        ...current,
        { role: "assistant", content: response.answer, citations: response.citations },
      ]);
      setConversationId(response.conversation_id);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  function handleNewChat() {
    setMessages([]);
    setConversationId(null);
    setError(null);
    setInput("");
  }

  return (
    <section className="flex min-h-[calc(100vh-9rem)] flex-col">
      <div className="flex items-center justify-between border-b border-gray-200 pb-4">
        <h1 className="text-xl font-semibold text-gray-900">Ask the documents</h1>
        <button
          type="button"
          onClick={handleNewChat}
          disabled={loading}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          New chat
        </button>
      </div>

      <div
        aria-live="polite"
        className="flex flex-1 flex-col gap-5 overflow-y-auto py-6"
      >
        {messages.length === 0 && !loading && (
          <p className="m-auto text-sm text-gray-500">What would you like to know?</p>
        )}

        {messages.map((message, index) => (
          <article
            key={`${index}-${message.role}`}
            className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div className="max-w-[85%]">
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">
                {message.role === "user" ? "You" : "Assistant"}
              </p>
              <div
                className={`whitespace-pre-wrap rounded-lg px-4 py-3 text-sm leading-6 ${
                  message.role === "user"
                    ? "bg-gray-900 text-white"
                    : "border border-gray-200 bg-white text-gray-900"
                }`}
              >
                {message.content}
              </div>
              {message.role === "assistant" && !!message.citations?.length && (
                <p className="mt-2 text-xs text-gray-500">
                  {message.citations
                    .map((citation) => `${citation.filename} · p. ${citation.page}`)
                    .join(" · ")}
                </p>
              )}
            </div>
          </article>
        ))}

        {loading && (
          <div className="flex justify-start" role="status">
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">
                Assistant
              </p>
              <p className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-500">
                thinking…
              </p>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-gray-200 pt-4">
        {error && (
          <p role="alert" className="mb-3 text-sm text-red-700">
            {error}
          </p>
        )}
        <div className="flex items-end gap-3">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            disabled={loading}
            rows={2}
            aria-label="Your message"
            placeholder="Ask a question…"
            className="min-h-12 flex-1 resize-y rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none placeholder:text-gray-400 focus:border-gray-500 focus:ring-2 focus:ring-gray-200 disabled:bg-gray-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="rounded-md bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </section>
  );
}
