"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { SendHorizonal, Bot, User, Loader2, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// ── Helpers ────────────────────────────────────────────────────────────────────

function randomId(): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch { /* non-secure context (HTTP) */ }
  const arr = new Uint8Array(8);
  if (typeof crypto !== "undefined" && crypto.getRandomValues) {
    crypto.getRandomValues(arr);
    return Array.from(arr, (b) => b.toString(16).padStart(2, "0")).join("");
  }
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

// ── Types ──────────────────────────────────────────────────────────────────────

type ToolCall = { name: string };

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  streaming?: boolean;
};

// ── Constants ──────────────────────────────────────────────────────────────────

const SUGGESTED_QUESTIONS = [
  "How is my portfolio performing?",
  "What are my current positions and P&L?",
  "What is my Sharpe ratio this year?",
  "Which stock has the best unrealized gain?",
  "How much cash do I have?",
  "Show me my recent trades",
];

const TOOL_LABELS: Record<string, string> = {
  get_portfolio_snapshot: "Portfolio Snapshot",
  get_positions: "Positions",
  get_cash_balance: "Cash Balance",
  get_recent_trades: "Trade History",
  get_lots: "Lot Details",
  get_perf_summary: "Performance Summary",
  get_risk_metrics: "Risk Metrics",
};

// ── Sub-components ─────────────────────────────────────────────────────────────

function ToolCallBadges({ toolCalls }: { toolCalls: ToolCall[] }) {
  if (!toolCalls.length) return null;
  return (
    <div className="flex flex-wrap gap-1 mb-1.5">
      {toolCalls.map((tc, i) => (
        <Badge
          key={i}
          variant="outline"
          className="text-xs gap-1 text-muted-foreground font-normal"
        >
          <Database className="h-2.5 w-2.5" />
          {TOOL_LABELS[tc.name] ?? tc.name}
        </Badge>
      ))}
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-3 items-start", isUser && "flex-row-reverse")}>
      {/* Avatar */}
      <div
        className={cn(
          "flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-0.5",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted border border-border",
        )}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5" />
        ) : (
          <Bot className="h-3.5 w-3.5" />
        )}
      </div>

      {/* Content */}
      <div className={cn("flex-1 min-w-0 max-w-[80%]", isUser && "flex flex-col items-end")}>
        {!isUser && msg.toolCalls && (
          <ToolCallBadges toolCalls={msg.toolCalls} />
        )}
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words",
            isUser
              ? "bg-primary text-primary-foreground rounded-tr-sm"
              : "bg-muted rounded-tl-sm",
          )}
        >
          {msg.content ? (
            msg.content
          ) : msg.streaming ? (
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span className="text-xs">Thinking…</span>
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function EmptyState({ onSelect }: { onSelect: (q: string) => void }) {
  return (
    <div className="text-center pt-16 space-y-8 px-4">
      <div>
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/10 mb-4">
          <Bot className="h-8 w-8 text-primary" />
        </div>
        <h2 className="text-xl font-semibold">Portfolio Assistant</h2>
        <p className="text-muted-foreground text-sm mt-2 max-w-sm mx-auto">
          Ask anything about your portfolio. I can look up positions, performance, risk metrics, and more.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-xl mx-auto text-left">
        {SUGGESTED_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            className="text-sm px-4 py-3 rounded-xl border hover:bg-muted transition-colors text-muted-foreground hover:text-foreground text-left"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || loading) return;

      const userMsg: Message = {
        id: randomId(),
        role: "user",
        content: text,
      };
      const assistantId = randomId();
      const assistantMsg: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        toolCalls: [],
        streaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInput("");
      setLoading(true);

      // Build history for the API (exclude the streaming placeholder)
      const history = [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      try {
        const res = await fetch("/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: history }),
        });

        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;

            try {
              const event = JSON.parse(raw) as Record<string, string>;

              if (event.type === "tool_call") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, toolCalls: [...(m.toolCalls ?? []), { name: event.name }] }
                      : m,
                  ),
                );
              } else if (event.type === "text") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: m.content + event.text }
                      : m,
                  ),
                );
              } else if (event.type === "done") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, streaming: false } : m,
                  ),
                );
              } else if (event.type === "error") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: `Error: ${event.text}`, streaming: false }
                      : m,
                  ),
                );
              }
            } catch {
              // ignore malformed event
            }
          }
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `Network error: ${msg}`, streaming: false }
              : m,
          ),
        );
      } finally {
        setLoading(false);
        inputRef.current?.focus();
      }
    },
    [loading, messages],
  );

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
          {messages.length === 0 ? (
            <EmptyState onSelect={(q) => sendMessage(q)} />
          ) : (
            messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input bar */}
      <div className="border-t bg-background/95 backdrop-blur px-4 py-3">
        <form
          className="max-w-3xl mx-auto flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage(input);
          }}
        >
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your portfolio…"
            disabled={loading}
            className="flex-1"
            autoFocus
          />
          <Button
            type="submit"
            disabled={loading || !input.trim()}
            size="icon"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <SendHorizonal className="h-4 w-4" />
            )}
          </Button>
        </form>
        <p className="max-w-3xl mx-auto mt-1.5 text-xs text-muted-foreground text-center">
          Powered by Claude · data fetched live from your ledger
        </p>
      </div>
    </div>
  );
}
