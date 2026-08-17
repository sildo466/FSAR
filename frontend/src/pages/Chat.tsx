// SPDX-License-Identifier: MIT
import { useEffect, useMemo, useRef, useState } from "react";
import { Paperclip } from "lucide-react";
import {
  MessageList,
  type ChatMessage,
  type PendingRisk,
} from "../components/chat/MessageList";
import { HistoryPanel } from "../components/chat/HistoryPanel";
import { SlashPopover } from "../components/chat/SlashPopover";
import { AgentActivity, type AgentStatus } from "../components/chat/AgentActivity";
import { BlackHole } from "../components/ui/BlackHole";
import { Greeting } from "../components/ui/Greeting";
import { useWS } from "../stores/ws";
import { fetchWSToken } from "../stores/ws";
import { useSessions } from "../stores/sessions";
import { useWorkspace } from "../stores/workspace";
import { useCardsStore } from "../stores/cards";
import { useChatUI } from "../stores/chat-ui";
import type { StoredMessage } from "../lib/ws-client";
import { filterCommands } from "../lib/commands";
import { MicButton } from "../components/chat/MicButton";
import { useSpeechStore } from "../stores/speech";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const mode = useChatUI((s) => s.mode);
  const [busy, setBusy] = useState(false);
  const [pendingRisks, setPendingRisks] = useState<PendingRisk[]>([]);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [popoverFilter, setPopoverFilter] = useState("");
  const [popoverSelected, setPopoverSelected] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(() => window.innerWidth >= 640);
  const [agentStatuses, setAgentStatuses] = useState<AgentStatus[]>([]);
  const [attachments, setAttachments] = useState<Array<{ name: string; path: string; size: number }>>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(false);
  const [experiences, setExperiences] = useState<Array<{ name: string; description: string }>>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeAgentTask = useRef<string | null>(null);
  const lastSwitchedConv = useRef<string | null>(null);
  const pendingAssistantId = useRef<string | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const prevCountRef = useRef(0);

  const initWS = useWS((s) => s.init);
  const client = useWS((s) => s.client);
  const config = useWS((s) => s.config);

  const currentId = useSessions((s) => s.currentId);
  const pendingWorkspaceId = useWorkspace((s) => s.pendingWorkspaceId);
  const setPendingWorkspace = useWorkspace((s) => s.setPendingWorkspace);
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
  const fetchHistory = useSessions((s) => s.fetchHistory);
  const liveHistory = useSessions((s) => s.liveHistory);
  const syncLive = useSessions((s) => s.syncLive);

  // The sessions subscription is owned by App so it outlives this route.
  useEffect(() => {
    initWS();
  }, [initWS]);

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
    if (switched) {
      // On a genuine conversation switch, restore the full live stream
      // (agent tool calls, statuses, replies) captured before navigation
      // instead of the older backend snapshot.
      const live = currentId ? liveHistory[currentId] : undefined;
      if (live !== undefined && live.length > 0) {
        setMessages(live);
        return;
      }
    }
    if (currentHistory !== undefined) {
      // A conversation created by our own first message arrives with an
      // empty history while the optimistic bubbles are still in flight;
      // that empty history is stale, so keep the on-screen messages.
      const keepOptimistic = currentHistory.length === 0 && pendingAssistantId.current != null;
      if (!keepOptimistic) setMessages(currentHistory.map(storedToMessage));
    } else if (loadingHistory) {
      setMessages([]);
    } else {
      fetchHistory(currentId);
    }
    if (switched) setPendingRisks([]);
  }, [currentId, currentHistory, loadingHistory, fetchHistory]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // Keep the store's live cache in sync so navigating away and back to this
  // conversation restores the full stream (agent tool calls, statuses, etc.)
  // that the backend only persists as a plain-text summary.
  useEffect(() => {
    if (currentId) syncLive(currentId, messages);
  }, [messages, currentId, syncLive]);

  // Experiences feed the "/" popover so learned skills can be invoked.
  useEffect(() => {
    if (!client) return;
    client.send({ type: "library.list" });
    return client.on((msg) => {
      if (msg.type === "library.list_result") {
        setExperiences(
          (msg.experiences as Array<Record<string, unknown>>)
            .filter((e) => typeof e.name === "string")
            .map((e) => ({ name: String(e.name), description: String(e.description ?? "") }))
        );
      } else if (msg.type === "library.changed") {
        client.send({ type: "library.list" });
      }
    });
  }, [client]);

  // Keep the viewport pinned to the newest content while the user is
  // already near the bottom (or the message list was just replaced).
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const replaced = messages.length < prevCountRef.current;
    prevCountRef.current = messages.length;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
    if (replaced || nearBottom) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const MAX_INPUT_LINES = 4;
  const resizeInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 22 * MAX_INPUT_LINES)}px`;
  };

  // Wire chat.* events
  useEffect(() => {
    if (!client) return;
    return client.on((msg) => {
      if (msg.type === "chat.thinking") {
        setBusy(true);
        activeAgentTask.current = null;
        setAgentStatuses([]);
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
            character_name: msg.character_name ?? identity.character?.name ?? t("chat.assistant"),
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
      } else if (msg.type === "tts.synthesize_queued") {
        const message = messagesRef.current.find((item) => item.id === msg.message_id);
        if (!message?.content) return;
        const character = useCardsStore.getState().characters.find((item) => item.id === message.character_id);
        void useSpeechStore.getState().playText(message.content, message.id, {
          voiceOverride: String(character?.tts_voice ?? ""),
          instructionsOverride: String(character?.tts_instructions ?? ""),
        });
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
      } else if (msg.type === "agent.run.started") {
        activeAgentTask.current = msg.task_id;
        setAgentStatuses([]);
      } else if (msg.type === "agent.status") {
        if (activeAgentTask.current && msg.task_id !== activeAgentTask.current) return;
        activeAgentTask.current = msg.task_id;
        const incoming: AgentStatus = msg;
        setAgentStatuses((previous) => {
          const index = previous.findIndex((agent) => agent.agent_id === incoming.agent_id);
          if (index === -1) return [...previous, incoming];
          return previous.map((agent, current) => current === index ? incoming : agent);
        });
      } else if (msg.type === "error") {
        setBusy(false);
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "assistant",
            content: t("chat.error", { code: msg.code, message: msg.message }),
          },
        ]);
      }
    });
  }, [client]);

  const handleInputChange = (v: string) => {
    setInput(v);
    resizeInput();
    const m = v.match(/(^|\s)(\/(\S*))$/);
    if (m) {
      setPopoverOpen(true);
      setPopoverFilter(m[3]);
      setPopoverSelected(0);
    } else {
      setPopoverOpen(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (popoverOpen) {
      const cmds = popoverCommands;
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
        const replaced = input.replace(/\/\S*$/, `/${c.name} `);
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
    if (e.key === "Enter") {
      if (e.shiftKey) return;
      e.preventDefault();
      handleSend();
    }
  };

  const handlePickFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setUploadError(false);
    try {
      const form = new FormData();
      for (const file of Array.from(files).slice(0, 8)) form.append("files", file);
      const token = await fetchWSToken();
      const response = await fetch("/api/chat/upload", {
        method: "POST",
        credentials: "same-origin",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const payload = (await response.json().catch(() => ({}))) as {
        files?: Array<{ name: string; path: string; size: number }>;
      };
      if (!response.ok || !payload.files) throw new Error(`HTTP ${response.status}`);
      setAttachments((prev) => [...prev, ...payload.files!].slice(0, 8));
    } catch {
      setUploadError(true);
    } finally {
      setUploading(false);
    }
  };

  const handleSend = () => {
    if (!client || !input.trim() || busy) return;
    const text = input.trim();
    const attached = attachments;
    const identity = getIdentity(currentId);
    const userMessageId = nextId();
    const assistantMessageId = nextId();
    pendingAssistantId.current = assistantMessageId;
    setInput("");
    setAttachments([]);
    setUploadError(false);
    resizeInput();
    setPopoverOpen(false);
    setBusy(true);
    const display = attached.length
      ? `${text}\n\ud83d\udcce ${attached.map((a) => a.name).join(", ")}`
      : text;
    setMessages((prev) => [
      ...prev,
      {
        id: userMessageId,
        role: "user",
        content: display,
        user_name: identity.userName,
      },
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        thinking: true,
        character_id: identity.character?.id,
        character_name: identity.character?.name ?? t("chat.assistant"),
      },
    ]);
    client.send({
      type: "chat.send",
      conversation_id: currentId ?? undefined,
      character_id: identity.requestedCharacterId,
      content: text,
      mode,
      attached_files: attached.length ? attached.map((a) => a.path) : undefined,
      workspace_id: currentId ? undefined : (pendingWorkspaceId ?? undefined),
      selected_chat_model: (((config?.chat ?? {}) as Record<string, unknown>).default_model as Record<string, unknown> | undefined),
    });
    if (!currentId && pendingWorkspaceId != null) {
      setPendingWorkspace(null);
    }
  };

  const handleCancel = () => {
    client?.send({ type: "chat.cancel", conversation_id: currentId ?? undefined });
  };

  const handleRegenerate = () => {
    if (!client || busy || !currentId) return;
    const msgs = messagesRef.current;
    let lastAssistant = -1;
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === "assistant") {
        lastAssistant = i;
        break;
      }
    }
    if (lastAssistant === -1) return;
    const convId = currentId;
    setMessages(msgs.filter((_, i) => i !== lastAssistant));
    useSessions.setState((s) => {
      const cached = s.history[convId];
      if (!cached) return {};
      let end = cached.length;
      while (end > 0 && cached[end - 1].role !== "user") end--;
      if (end === cached.length) return {};
      return { history: { ...s.history, [convId]: cached.slice(0, end) } };
    });
    pendingAssistantId.current = null;
    setBusy(true);
    client.send({
      type: "chat.regenerate",
      conversation_id: convId,
      mode,
      selected_chat_model: (((config?.chat ?? {}) as Record<string, unknown>).default_model as Record<string, unknown> | undefined),
    });
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
    const rateId = messageId.startsWith("hist_") ? messageId.slice(5) : messageId;
    await new Promise<void>((resolve, reject) => {
      const off = client.on((msg) => {
        if (msg.type === "chat.rate.ack" && msg.message_id === rateId) {
          off();
          if (msg.status === "ok") resolve();
          else reject(new Error(msg.error || msg.status));
        }
      });
      client.send({ type: "chat.rate", message_id: rateId, score, reason });
      setTimeout(() => {
        off();
        resolve();
      }, 1500);
    });
  };

  const popoverCommands = useMemo(() => {
    if (!popoverOpen) return [];
    const q = popoverFilter.toLowerCase();
    const expCommands = q
      ? experiences
          .filter((e) => `use ${e.name}`.toLowerCase().startsWith(q))
          .slice(0, 8)
          .map((e) => ({
            name: `use ${e.name}`,
            description: e.description || e.name,
            usage: `/use ${e.name}`,
          }))
      : [];
    return [...filterCommands(popoverFilter), ...expCommands];
  }, [popoverOpen, popoverFilter, experiences]);
  const isIdle = messages.length === 0 && pendingRisks.length === 0;

  return (
    <div className="chat-root-bg relative flex h-full">
      <div className="relative flex min-w-0 flex-1 flex-col rounded-[28px] bg-[color:var(--glass)]/20">
        <AgentActivity agents={agentStatuses} />
        {isIdle ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-8 px-8">
            <BlackHole width={64} />
            <Greeting />
          </div>
        ) : (
          <div ref={scrollRef} className="flex-1 overflow-auto">
            <MessageList
              messages={messages}
              pendingRisks={pendingRisks}
              onRespond={onRespond}
              onRate={onRate}
              onRegenerate={handleRegenerate}
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
                  const replaced = input.replace(/\/\S*$/, `/${c.name} `);
                  setInput(replaced);
                  setPopoverOpen(false);
                }}
                onClose={() => setPopoverOpen(false)}
              />
            )}
            {(attachments.length > 0 || uploadError) && (
              <div className="mb-2 flex flex-wrap items-center gap-2">
                {attachments.map((a, i) => (
                  <span
                    key={a.path}
                    className="flex items-center gap-1.5 rounded-full border border-[var(--chip-border)] px-3 py-1 text-[11px] text-text-muted"
                  >
                    📎 {a.name}
                    <button
                      onClick={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
                      className="hover:text-text"
                    >
                      ✕
                    </button>
                  </span>
                ))}
                {uploadError && (
                  <span className="text-[11px] text-red-500">{t("chat.uploadFailed")}</span>
                )}
              </div>
            )}
            <div className="glass-strong glow-focus flex items-end gap-2 rounded-[26px] px-3 py-2 shadow-[0_12px_48px_var(--glow-faint)]">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => {
                  void handlePickFiles(e.target.files);
                  e.target.value = "";
                }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                title={t("chat.attach")}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-text-muted transition hover:bg-glass hover:text-text disabled:opacity-50"
              >
                <Paperclip size={15} strokeWidth={1.5} />
              </button>
              <textarea
                ref={textareaRef}
                rows={1}
                value={input}
                onChange={(e) => handleInputChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t("chat.placeholderInput")}
                className="max-h-[88px] min-w-0 flex-1 resize-none overflow-y-auto bg-transparent px-2 py-1 text-sm leading-[22px] text-text outline-none placeholder:text-text-muted"
              />
              <MicButton onTranscript={(text) => setInput((current) => `${current}${current.trim() ? " " : ""}${text}`)} />
              {busy ? (
                <button
                  onClick={handleCancel}
                  className="rounded-full px-4 py-2 text-xs text-text-muted transition hover:bg-glass hover:text-text"
                >
                  {t("chat.stop")}
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-bg shadow-[0_0_20px_var(--glow-soft)] transition hover:scale-105"
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
