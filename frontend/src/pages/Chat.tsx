// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { MessageList, type ChatMessage } from "../components/chat/MessageList";
import { useWS } from "../stores/ws";
import { t } from "../lib/i18n";

let id = 0;
const nextId = () => `m_${++id}`;

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
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
      }
    });
  }, [client, init]);

  const handleSend = () => {
    if (!input.trim()) return;
    const text = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { id: nextId(), role: "user", content: text }]);
    send({ type: "chat.send", content: text, mode: "agent" });
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto">
        <MessageList messages={messages} />
      </div>
      <div className="border-t border-border bg-surface">
        <div className="max-w-[720px] mx-auto px-8 py-4 flex gap-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
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
  );
}
