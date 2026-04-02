"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Bot, X, SendHorizonal, Loader2, Database, Trash2, PenLine } from "lucide-react";
import { cn } from "@/lib/utils";

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

const TOOL_LABELS: Record<string, string> = {
  get_portfolio_snapshot:   "Snapshot",
  get_positions:            "Positions",
  get_cash_balance:         "Cash",
  get_recent_trades:        "Trades",
  get_lots:                 "Lot Details",
  get_perf_summary:         "Performance",
  get_risk_metrics:         "Risk Metrics",
  add_trade:                "Recording Trade",
  add_cash:                 "Recording Cash",
  get_quote:                "Real-time Quote",
  get_technical_indicators: "Technical Analysis",
  get_news:                 "News",
};

const WRITE_TOOLS = new Set(["add_trade", "add_cash"]);
const LS_KEY = "jarvis_messages";
const SESSION_KEY = "jarvis_session_id";
const JARVIS_KEY_LS = "jarvis_access_key";

function getStoredKey(): string {
  try { return localStorage.getItem(JARVIS_KEY_LS) ?? ""; } catch { return ""; }
}
function storeKey(k: string): void {
  try { localStorage.setItem(JARVIS_KEY_LS, k); } catch { /* ignore */ }
}
function clearKey(): void {
  try { localStorage.removeItem(JARVIS_KEY_LS); } catch { /* ignore */ }
}

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

function getOrCreateSessionId(): string {
  try {
    const existing = localStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const id = randomId();
    localStorage.setItem(SESSION_KEY, id);
    return id;
  } catch {
    return "";
  }
}


const PAGE_LABELS: Record<string, string> = {
  "/overview":   "Overview Dashboard",
  "/portfolio":  "Portfolio Dashboard",
  "/positions":  "Positions Page",
  "/trades":     "Trades Page",
  "/cash":       "Cash Page",
  "/watchlist":  "Watchlist Page",
  "/catalyst":   "Catalyst Page",
  "/universe":   "Universe / Watchlist Page",
  "/offsetting": "Offsetting Page",
  "/settings":   "Settings Page",
  "/import":     "Import Page",
  "/digest":     "Digest Page",
};

const SUGGESTIONS = [
  "How is my portfolio performing?",
  "What are my open positions and P&L?",
  "Show me my risk metrics",
  "Which stock has the best unrealized gain?",
  "How much cash do I have?",
  "Show my recent trades",
];

// ── Message bubble ─────────────────────────────────────────────────────────────

function JarvisMessage({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-2.5 items-start", isUser && "flex-row-reverse")}>
      {/* Avatar */}
      <div
        className={cn(
          "flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold mt-0.5 select-none",
          isUser
            ? "bg-blue-600 text-white"
            : "bg-gradient-to-br from-blue-600 to-cyan-500 text-white",
        )}
      >
        {isUser ? "U" : "J"}
      </div>

      {/* Content */}
      <div className={cn("flex-1 min-w-0 max-w-[88%]", isUser && "flex flex-col items-end")}>
        {/* Tool badges */}
        {!isUser && !!msg.toolCalls?.length && (
          <div className="flex flex-wrap gap-1 mb-1.5">
            {msg.toolCalls.map((tc, i) => {
              const isWrite = WRITE_TOOLS.has(tc.name);
              return (
                <span
                  key={i}
                  className={cn(
                    "inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border",
                    isWrite
                      ? "bg-emerald-950 border-emerald-900 text-emerald-400"
                      : "bg-cyan-950 border-cyan-900 text-cyan-400",
                  )}
                >
                  {isWrite
                    ? <PenLine className="h-2 w-2" />
                    : <Database className="h-2 w-2" />}
                  {TOOL_LABELS[tc.name] ?? tc.name}
                </span>
              );
            })}
          </div>
        )}

        {/* Bubble */}
        <div
          className={cn(
            "rounded-xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words",
            isUser
              ? "bg-blue-600 text-white rounded-tr-sm"
              : "bg-zinc-800 text-zinc-100 rounded-tl-sm",
          )}
        >
          {msg.content ? (
            msg.content
          ) : msg.streaming ? (
            <span className="flex items-center gap-1.5 text-zinc-500">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span className="text-xs">Processing…</span>
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────────

export function JarvisPanel() {
  const [open, setOpen]       = useState(false);
  const [accessKey, setAccessKey] = useState<string>(() => getStoredKey());
  const [keyInput, setKeyInput]   = useState("");
  const [keyError, setKeyError]   = useState(false);
  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const saved = localStorage.getItem(LS_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch { return []; }
  });
  const [input, setInput]     = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLInputElement>(null);
  const pathname  = usePathname();
  const qc        = useQueryClient();

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) { setOpen(false); return; }
      if ((e.ctrlKey || e.metaKey) && e.key === "j") {
        e.preventDefault();
        setOpen(v => !v);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // Focus input when panel opens
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 320);
  }, [open]);

  // Persist messages to localStorage
  useEffect(() => {
    try { localStorage.setItem(LS_KEY, JSON.stringify(messages)); } catch { /* quota */ }
  }, [messages]);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const resolvePageLabel = () => {
    const match = Object.entries(PAGE_LABELS).find(([path]) =>
      pathname === path || pathname.startsWith(path + "/"),
    );
    return match?.[1] ?? pathname;
  };

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: Message     = { id: randomId(), role: "user", content: text };
    const assistantId          = randomId();
    const assistantMsg: Message = {
      id: assistantId, role: "assistant", content: "", toolCalls: [], streaming: true,
    };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setInput("");
    setLoading(true);

    const history = [...messages, userMsg].map(m => ({ role: m.role, content: m.content }));
    let wroteData = false;

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(accessKey ? { "X-Jarvis-Key": accessKey } : {}),
        },
        body: JSON.stringify({
          messages: history,
          page_context: resolvePageLabel(),
          session_id: getOrCreateSessionId(),
        }),
      });

      if (res.status === 401) {
        clearKey();
        setAccessKey("");
        setMessages(prev => prev.map(m =>
          m.id === assistantId
            ? { ...m, content: "⚠ Access denied. Please enter your J.A.R.V.I.S. key.", streaming: false }
            : m,
        ));
        setLoading(false);
        return;
      }
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer    = "";

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
            const ev = JSON.parse(raw) as Record<string, string>;
            if (ev.type === "tool_call") {
              if (WRITE_TOOLS.has(ev.name)) wroteData = true;
              setMessages(prev => prev.map(m =>
                m.id === assistantId
                  ? { ...m, toolCalls: [...(m.toolCalls ?? []), { name: ev.name }] }
                  : m,
              ));
            } else if (ev.type === "text") {
              setMessages(prev => prev.map(m =>
                m.id === assistantId ? { ...m, content: m.content + ev.text } : m,
              ));
            } else if (ev.type === "done") {
              setMessages(prev => prev.map(m =>
                m.id === assistantId ? { ...m, streaming: false } : m,
              ));
              if (wroteData) {
                qc.invalidateQueries({ queryKey: ["trades"] });
                qc.invalidateQueries({ queryKey: ["cashTx"] });
                qc.invalidateQueries({ queryKey: ["cashBalance"] });
                qc.invalidateQueries({ queryKey: ["positions"] });
                qc.invalidateQueries({ queryKey: ["equitySnapshot"] });
              }
            } else if (ev.type === "error") {
              setMessages(prev => prev.map(m =>
                m.id === assistantId
                  ? { ...m, content: `⚠ ${ev.text}`, streaming: false }
                  : m,
              ));
            }
          } catch { /* ignore malformed event */ }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setMessages(prev => prev.map(m =>
        m.id === assistantId
          ? { ...m, content: `⚠ Network error: ${msg}`, streaming: false }
          : m,
      ));
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, messages, pathname]);

  return (
    <>
      {/* ── Floating trigger button ── */}
      <button
        onClick={() => setOpen(v => !v)}
        title={open ? "Close J.A.R.V.I.S." : "J.A.R.V.I.S.  (Ctrl+J)"}
        className={cn(
          "fixed bottom-6 left-6 z-[60] w-14 h-14 rounded-full",
          "flex items-center justify-center",
          "bg-gradient-to-br from-blue-600 to-cyan-500 text-white",
          "shadow-lg shadow-blue-900/40",
          "transition-all duration-300 hover:scale-110 hover:shadow-cyan-500/40 hover:shadow-xl",
          open && "rotate-[360deg]",
        )}
      >
        {open ? <X className="h-5 w-5" /> : <Bot className="h-6 w-6" />}
      </button>

      {/* ── Backdrop ── */}
      <div
        onClick={() => setOpen(false)}
        className={cn(
          "fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity duration-300",
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none",
        )}
      />

      {/* ── Slide-in panel ── */}
      <div
        className={cn(
          "fixed top-0 right-0 h-full w-[420px] z-50 flex flex-col",
          "bg-zinc-950 border-l border-zinc-800/80 shadow-2xl shadow-black/60",
          "transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        {/* Header */}
        <div className="flex-shrink-0 px-5 py-4 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-cyan-500 flex items-center justify-center shadow-md shadow-blue-900/40">
              <Bot className="h-4 w-4 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold tracking-widest text-zinc-100">J.A.R.V.I.S.</span>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              </div>
              <p className="text-[10px] text-zinc-500 tracking-wide">PORTFOLIO INTELLIGENCE SYSTEM</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {accessKey && (
              <button
                onClick={() => { clearKey(); setAccessKey(""); setMessages([]); }}
                title="Lock J.A.R.V.I.S."
                className="text-zinc-600 hover:text-zinc-400 transition-colors text-[10px] px-1.5 py-0.5 border border-zinc-700 rounded"
              >
                Lock
              </button>
            )}
            {messages.length > 0 && (
              <button
                onClick={() => {
                  setMessages([]);
                  try {
                    localStorage.removeItem(LS_KEY);
                    localStorage.removeItem(SESSION_KEY);
                  } catch { /* ignore */ }
                }}
                title="Clear conversation"
                className="text-zinc-600 hover:text-zinc-400 transition-colors"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
            <button
              onClick={() => setOpen(false)}
              className="text-zinc-600 hover:text-zinc-300 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Key lock screen */}
        {!accessKey && (
          <div className="flex-1 flex flex-col items-center justify-center px-6 gap-4">
            <div className="text-center space-y-1">
              <p className="text-sm font-semibold text-zinc-200">Access Required</p>
              <p className="text-xs text-zinc-500">Enter your J.A.R.V.I.S. access key to continue.</p>
            </div>
            <form
              className="w-full flex flex-col gap-2"
              onSubmit={e => {
                e.preventDefault();
                if (!keyInput.trim()) return;
                storeKey(keyInput.trim());
                setAccessKey(keyInput.trim());
                setKeyInput("");
                setKeyError(false);
              }}
            >
              <input
                type="password"
                value={keyInput}
                onChange={e => { setKeyInput(e.target.value); setKeyError(false); }}
                placeholder="Enter access key…"
                className={cn(
                  "w-full bg-zinc-900 border rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600",
                  "focus:outline-none focus:border-cyan-700 transition-colors",
                  keyError ? "border-red-600" : "border-zinc-800",
                )}
              />
              {keyError && <p className="text-xs text-red-400">Incorrect key. Try again.</p>}
              <button
                type="submit"
                className="w-full py-2 rounded-lg bg-gradient-to-br from-blue-600 to-cyan-500 text-white text-sm font-medium hover:opacity-90 transition-opacity"
              >
                Unlock
              </button>
            </form>
          </div>
        )}

        {/* Messages */}
        <div className={cn("flex-1 overflow-y-auto px-4 py-4", !accessKey && "hidden")}>
          {messages.length === 0 ? (
            <div className="space-y-5 pt-2">
              <div className="text-center space-y-1">
                <p className="text-xs text-zinc-500">All systems online.</p>
                <p className="text-xs text-zinc-600">How can I assist you?</p>
              </div>
              <div className="space-y-1.5">
                {SUGGESTIONS.map(q => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    className={cn(
                      "w-full text-left text-xs px-3 py-2.5 rounded-lg",
                      "border border-zinc-800 text-zinc-500",
                      "hover:border-cyan-800 hover:text-cyan-300 hover:bg-cyan-950/20",
                      "transition-all duration-150",
                    )}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map(msg => (
                <JarvisMessage key={msg.id} msg={msg} />
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className={cn("flex-shrink-0 border-t border-zinc-800 px-4 py-3 space-y-2", !accessKey && "hidden")}>
          <form
            className="flex gap-2"
            onSubmit={e => { e.preventDefault(); sendMessage(input); }}
          >
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              disabled={loading}
              placeholder="Query J.A.R.V.I.S…"
              className={cn(
                "flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2",
                "text-sm text-zinc-100 placeholder:text-zinc-600",
                "focus:outline-none focus:border-cyan-700",
                "transition-colors duration-150",
                "disabled:opacity-50",
              )}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className={cn(
                "flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center",
                "bg-gradient-to-br from-blue-600 to-cyan-500 text-white",
                "disabled:opacity-40 hover:opacity-90 active:scale-95",
                "transition-all duration-150",
              )}
            >
              {loading
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <SendHorizonal className="h-4 w-4" />}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
