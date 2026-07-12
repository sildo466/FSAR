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
import { useChatUI } from "../stores/chat-ui";
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
    character_id: m.character_id,
    character_name: m.character_name,
  };
}

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const mode = useChatUI((s) => s.mode);
  const [busy, setBusy] = useState(false);
  const [pendingRisks, setPendingRisks] = useState<PendingRisk[]>([]);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [popoverFilter, setPopoverFilter] = useState("");
  const [popoverSelected, setPopoverSelected] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(true);
  const lastSwitchedConv = useRef<string | null>(null);
  const pendingAssistantId = useRef<string | null>(null);

  const initWS = useWS((s) => s.init);
  const client = useWS((s) => s.client);

  const currentId = useSessions((s) => s.currentId);
  const getIdentity = (conversationId?: string | null) => {
    const {
      characters,
      defaultUserCard,
      sessionCharacters,
      draftCharacterId,
    } = useCardsStore.getState();
    const explicitCharacterId = conversationId
      ? sessionCharacters[conversationId]
      : draftCharacterId;
    const character =
      characters.find((card) => card.id === explicitCharacterId) ??
      characters.find((card) => card.is_default === 1) ??
      characters[0];
    return {
      character,
      requestedCharacterId: explicitCharacterId ?? (conversationId ? undefined : character?.id),
      userName: defaultUserCard?.name ?? "USER",
    };
  };
  const history = useSessions((s) => s.history);
  const currentHistory = currentId ? history[currentId] : undefined;
  const loadingHistory = useSessions((s) => s.loadingHistory);
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
    if (!currentId) {
      lastSwitchedConv.current = null;
      setMessages([]);
      setPendingRisks([]);
      return;
    }
    const switched = currentId !== lastSwitchedConv.current;
    if (!switched && currentHistory === undefined) return;
    lastSwitchedConv.current = currentId;
    if (currentHistory !== undefined) {
      setMessages(currentHistory.map(storedToMessage));
    } else if (loadingHistory) {
      setMessages([]);
    }
    if (switched) setPendingRisks([]);
  }, [currentId, currentHistory, loadingHistory]);

  // Wire chat.* events
  useEffect(() => {
    if (!client) return;
    return client.on((msg) => {
      if (msg.type === "chat.thinking") {
        setBusy(true);
        const pendingId = pendingAssistantId.current;
        pendingAssistantId.current = null;
        setMessages((prev) => {
          const identity = getIdentity(msg.conversation_id);
          const incoming: ChatMessage = {
            id: msg.message_id,
            role: "assistant",
            content: "",
            thinking: true,
            character_id: msg.character_id ?? identity.character?.id,
            character_name: msg.character_name ?? identity.character?.name ?? "Assistant",
          };
          if (pendingId && prev.some((message) => message.id === pendingId)) {
            return prev.map((message) => message.id === pendingId ? incoming : message);
          }
          if (prev.some((message) => message.id === msg.message_id)) return prev;
          return [...prev, incoming];
        });
      } else if (msg.type === "chat.delta") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msg.message_id
              ? {
                  ...m,
                  content: m.content + msg.content,
                  thinking: false,
                  streaming: true,
                  character_id: msg.character_id ?? m.character_id,
                  character_name: msg.character_name ?? m.character_name,
                }
              : m
          )
        );
      } else if (msg.type === "chat.done") {
        setBusy(false);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msg.message_id
              ? { ...m, thinking: false, streaming: false,
                  character_id: msg.character_id ?? m.character_id,
                  character_name: msg.character_name ?? m.character_name,
                  user_name: getIdentity().userName }
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
    if (!client || !input.trim() || busy) return;
    const text = input.trim();
    const identity = getIdentity(currentId);
    const userMessageId = nextId();
    const assistantMessageId = nextId();
    pendingAssistantId.current = assistantMessageId;
    setInput("");
    setPopoverOpen(false);
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      {
        id: userMessageId,
        role: "user",
        content: text,
        user_name: identity.userName,
      },
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        thinking: true,
        character_id: identity.character?.id,
        character_name: identity.character?.name ?? "Assistant",
      },
    ]);
    client.send({
      type: "chat.send",
      conversation_id: currentId ?? undefined,
      character_id: identity.requestedCharacterId,
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
      <div className="flex min-w-0 flex-1 flex-col rounded-[28px] bg-[color:var(--glass)]/20">
        {isIdle ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-8 px-8">
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
        <div className="px-4 pb-4 pt-3 sm:px-8">
          <div className="relative mx-auto max-w-[900px]">
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
            <div className="glass-strong glow-focus flex items-center gap-2 rounded-full px-3 py-2 shadow-[0_12px_48px_var(--glow-faint)]">
              <input
                value={input}
                onChange={(e) => handleInputChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t.placeholderInput}
                className="min-w-0 flex-1 bg-transparent px-2 text-sm text-text outline-none placeholder:text-text-muted"
              />
              {busy ? (
                <button
                  onClick={handleCancel}
                  className="rounded-full px-4 py-2 text-xs text-text-muted transition hover:bg-glass hover:text-text"
                >
                  {t.chatStop}
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-text text-bg shadow-[0_0_20px_var(--glow-soft)] transition hover:scale-105"
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
