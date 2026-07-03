// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import {
  MessageList,
  type ChatMessage,
  type PendingRisk,
} from "../components/chat/MessageList";
import { SlashPopover } from "../components/chat/SlashPopover";
import { useWS } from "../stores/ws";
import { t } from "../lib/i18n";
import { filterCommands } from "../lib/commands";

let id = 0;
const nextId = () => `m_${++id}`;

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pendingRisks, setPendingRisks] = useState<PendingRisk[]>([]);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [popoverFilter, setPopoverFilter] = useState("");
  const [popoverSelected, setPopoverSelected] = useState(0);
  const send = useWS((s) => s.send);
  const init = useWS((s) => s.init);
  const client = useWS((s) => s.client);

  useEffect(() => {
    init();
    if (!client) return;
    return client.on((msg) => {
      if (msg.type === "chat.thinking") {
        setMessages((prev) => [
          ...prev,
          { id: msg.message_id, role: "assistant", content: "", thinking: true },
        ]);
      } else if (msg.type === "chat.delta") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msg.message_id
              ? { ...m, content: m.content + msg.content, thinking: false }
              : m
          )
        );
      } else if (msg.type === "chat.done") {
        setMessages((prev) =>
          prev.map((m) => (m.id === msg.message_id ? { ...m, thinking: false } : m))
        );
      } else if (msg.type === "chat.tool_call") {
        setPendingRisks((prev) => [
          ...prev,
          {
            callId: msg.call_id,
            tool: msg.tool,
            argsPreview:
              typeof msg.args === "string" ? msg.args : JSON.stringify(msg.args, null, 2),
            risk: msg.risk,
          },
        ]);
      } else if (msg.type === "chat.tool_result") {
        setPendingRisks((prev) => prev.filter((r) => r.callId !== msg.call_id));
      }
    });
  }, [client, init]);

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
    if (!input.trim()) return;
    const text = input.trim();
    setInput("");
    setPopoverOpen(false);
    setMessages((prev) => [...prev, { id: nextId(), role: "user", content: text }]);
    send({ type: "chat.send", content: text, mode: "agent" });
  };

  const onRiskRespond = (callId: string, response: "y" | "n" | "all" | "never") => {
    send({ type: "risk.respond", call_id: callId, response });
  };

  const onRate = (messageId: string, score: 1 | 2 | 3 | 4 | 5, reason?: string) => {
    send({ type: "chat.rate", message_id: messageId, score, reason });
  };

  const popoverCommands = popoverOpen ? filterCommands(popoverFilter) : [];

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto">
        <MessageList
          messages={messages}
          pendingRisks={pendingRisks}
          onRiskRespond={onRiskRespond}
          onRate={onRate}
        />
      </div>
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
            <input
              value={input}
              onChange={(e) => handleInputChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t.placeholderInput}
              className="flex-1 bg-transparent border-none outline-none text-text placeholder:text-text-muted"
            />
            <button
              onClick={handleSend}
              className="px-4 h-9 rounded border border-border-strong text-text hover:bg-bg"
            >
              ↵
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
