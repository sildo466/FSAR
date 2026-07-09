// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import {
  MessageList,
  type ChatMessage,
  type PendingRisk,
} from "../components/chat/MessageList";
import { HistoryPanel } from "../components/chat/HistoryPanel";
import { SlashPopover } from "../components/chat/SlashPopover";
import { BlackHole } from "../components/ui/BlackHole";
import { Greeting } from "../components/ui/Greeting";
import { useWS } from "../stores/ws";
import { useSessions } from "../stores/sessions";
import { useCardsStore } from "../stores/cards";
import { CharacterSelector } from "../components/chat/CharacterSelector";
import type { StoredMessage } from "../lib/ws-client";
import { t } from "../lib/i18n";
import { filterCommands } from "../lib/commands";

let id = 0;
const nextId = () => `m_${++id}`;

function storedToMessage(m: StoredMessage): ChatMessage {
  return {
    id: `hist_${m.id}`,
    role: m.role === "user" ? "user" : "assistant",
    content: m.content,
  };
}

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"agent" | "companion">("agent");
  const [busy, setBusy] = useState(false);
  const [pendingRisks, setPendingRisks] = useState<PendingRisk[]>([]);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [popoverFilter, setPopoverFilter] = useState("");
  const [popoverSelected, setPopoverSelected] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(true);
  const lastSwitchedConv = useRef<string | null>(null);

  const initWS = useWS((s) => s.init);
  const client = useWS((s) => s.client);

  const currentId = useSessions((s) => s.currentId);
  const get = () => {
    const { characters, defaultUserCard } = useCardsStore.getState();
    return {
      defaultCharacterName: characters.find((c) => c.is_default === 1)?.name ?? "FSAR",
      defaultUserName: defaultUserCard?.name ?? "USER",
    };
  };
  const history = useSessions((s) => s.history);
  const initSessions = useSessions((s) => s.init);

  // Init WS + sessions subscriptions
  useEffect(() => {
    initWS();
  }, [initWS]);

  useEffect(() => {
    if (!client) return;
    const detach = initSessions(client);
    return () => detach();
  }, [client, initSessions]);

  // When conversation switches, replace messages from history cache
  useEffect(() => {
    if (!currentId || currentId === lastSwitchedConv.current) return;
    lastSwitchedConv.current = currentId;
    const cached = history[currentId];
    if (cached) {
      setMessages(cached.map(storedToMessage));
    } else {
      setMessages([]);
    }
    setPendingRisks([]);
  }, [currentId, history]);

  // Wire chat.* events
  useEffect(() => {
    if (!client) return;
    return client.on((msg) => {
      if (msg.type === "chat.thinking") {
        setBusy(true);
        setMessages((prev) => [
          ...prev,
          { id: msg.message_id, role: "assistant", content: "", thinking: true },
        ]);
      } else if (msg.type === "chat.delta") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msg.message_id
              ? { ...m, content: m.content + msg.content, thinking: false, streaming: true,
                  character_name: get().defaultCharacterName }
              : m
          )
        );
      } else if (msg.type === "chat.done") {
        setBusy(false);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msg.message_id
              ? { ...m, thinking: false, streaming: false,
                  character_name: get().defaultCharacterName,
                  user_name: get().defaultUserName }
              : m
          )
        );
      } else if (msg.type === "chat.tool_call") {
        const argsPreview =
          typeof msg.args === "string" ? msg.args : JSON.stringify(msg.args, null, 2);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msg.message_id
              ? {
                  ...m,
                  tools: [
                    ...(m.tools ?? []),
                    { callId: msg.call_id, tool: msg.tool, argsPreview },
                  ],
                }
              : m
          )
        );
        if (msg.risk !== "SAFE") {
          setPendingRisks((prev) => [
            ...prev,
            { callId: msg.call_id, tool: msg.tool, argsPreview, risk: msg.risk },
          ]);
        }
      } else if (msg.type === "chat.tool_result") {
        setPendingRisks((prev) => prev.filter((r) => r.callId !== msg.call_id));
        setMessages((prev) =>
          prev.map((m) =>
            m.tools?.some((t) => t.callId === msg.call_id)
              ? {
                  ...m,
                  tools: m.tools!.map((t) =>
                    t.callId === msg.call_id
                      ? {
                          ...t,
                          result:
                            typeof msg.result === "string"
                              ? msg.result
                              : JSON.stringify(msg.result),
                          latencyMs: msg.latency_ms,
                        }
                      : t
                  ),
                }
              : m
          )
        );
      } else if (msg.type === "error") {
        setBusy(false);
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "assistant",
            content: `⚠ ${msg.code}: ${msg.message}`,
          },
        ]);
      }
    });
  }, [client]);

  const handleInputChange = (v: string) => {
    setInput(v);
    const m = v.match(/(^|\s)(\/(\w*))$/);
    if (m) {
      setPopoverOpen(true);
      setPopoverFilter(m[3]);
      setPopoverSelected(0);
    } else {
      setPopoverOpen(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (popoverOpen) {
      const cmds = filterCommands(popoverFilter);
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setPopoverSelected((s) => Math.min(s + 1, cmds.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setPopoverSelected((s) => Math.max(s - 1, 0));
        return;
      }
      if (e.key === "Enter" && cmds[popoverSelected]) {
        e.preventDefault();
        const c = cmds[popoverSelected];
        const replaced = input.replace(/\/\w*$/, `/${c.name} `);
        setInput(replaced);
        setPopoverOpen(false);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setPopoverOpen(false);
        return;
      }
    }
    if (e.key === "Enter") handleSend();
  };

  const handleSend = () => {
    if (!input.trim() || busy) return;
    const text = input.trim();
    setInput("");
    setPopoverOpen(false);
    setMessages((prev) => [...prev, { id: nextId(), role: "user", content: text }]);
    client?.send({
      type: "chat.send",
      conversation_id: currentId ?? undefined,
      content: text,
      mode,
    });
  };

  const handleCancel = () => {
    client?.send({ type: "chat.cancel" });
  };

  const onRespond = (callId: string, response: "y" | "n" | "all" | "never") => {
    client?.send({ type: "risk.respond", call_id: callId, response });
  };

  const onRate = async (
    messageId: string,
    score: 1 | 2 | 3 | 4 | 5,
    reason?: string
  ) => {
    if (!client) throw new Error("ws not connected");
    await new Promise<void>((resolve, reject) => {
      const off = client.on((msg) => {
        if (msg.type === "chat.rate.ack" && msg.message_id === messageId) {
          off();
          if (msg.status === "ok") resolve();
          else reject(new Error(msg.error || msg.status));
        }
      });
      client.send({ type: "chat.rate", message_id: messageId, score, reason });
      setTimeout(() => {
        off();
        resolve();
      }, 1500);
    });
  };

  const popoverCommands = popoverOpen ? filterCommands(popoverFilter) : [];
  const isIdle = messages.length === 0 && pendingRisks.length === 0;

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col min-w-0">
        {isIdle ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-8 px-8">
            <BlackHole width={64} />
            <Greeting />
          </div>
        ) : (
          <div className="flex-1 overflow-auto">
            <MessageList
              messages={messages}
              pendingRisks={pendingRisks}
              onRespond={onRespond}
              onRate={onRate}
            />
          </div>
        )}
        <div className="border-t border-border bg-surface">
          <div className="relative max-w-[720px] mx-auto px-8 py-4">
            {popoverOpen && (
              <SlashPopover
                filter={popoverFilter}
                commands={popoverCommands}
                selected={popoverSelected}
                onSelect={(c) => {
                  const replaced = input.replace(/\/\w*$/, `/${c.name} `);
                  setInput(replaced);
                  setPopoverOpen(false);
                }}
                onClose={() => setPopoverOpen(false)}
              />
            )}
            <div className="flex gap-3 items-center">
              <CharacterSelector sessionId={currentId ?? ""} />
              <div className="flex rounded border border-border overflow-hidden shrink-0">
                {(["agent", "companion"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`px-3 h-9 text-[11px] font-display font-semibold uppercase tracking-[0.08em] ${
                      mode === m ? "bg-text text-surface" : "text-text-muted hover:text-text"
                    }`}
                  >
                    {m === "agent" ? t.modeAgent : t.modeCompanion}
                  </button>
                ))}
              </div>
              <input
                value={input}
                onChange={(e) => handleInputChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t.placeholderInput}
                className="flex-1 bg-transparent border-none outline-none text-text placeholder:text-text-muted"
              />
              {busy ? (
                <button
                  onClick={handleCancel}
                  className="px-4 h-9 rounded border border-border text-text-muted hover:text-text hover:bg-bg"
                >
                  {t.chatStop}
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  className="px-4 h-9 rounded border border-border-strong text-text hover:bg-bg"
                >
                  ↵
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
      <HistoryPanel open={historyOpen} onToggle={() => setHistoryOpen((v) => !v)} />
    </div>
  );
}