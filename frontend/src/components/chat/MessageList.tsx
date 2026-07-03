// SPDX-License-Identifier: Apache-2.0
import { ThinkingDot } from "./ThinkingDot";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  thinking?: boolean;
}

interface Props {
  messages: ChatMessage[];
}

export function MessageList({ messages }: Props) {
  return (
    <div className="flex flex-col gap-6 max-w-[720px] mx-auto px-8 py-6">
      {messages.map((m) => (
        <div key={m.id} className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <span className="font-display text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              {m.role === "user" ? "USER" : "ASSISTANT"}
            </span>
            <span className="font-mono text-xs text-text-muted">just now</span>
          </div>
          <div className="text-text leading-relaxed whitespace-pre-wrap">
            {m.thinking ? <ThinkingDot /> : m.content}
          </div>
          <hr className="border-border" />
        </div>
      ))}
    </div>
  );
}
