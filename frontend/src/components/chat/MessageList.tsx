// SPDX-License-Identifier: Apache-2.0
import { ThinkingDot } from "./ThinkingDot";
import { RiskConfirm } from "./RiskConfirm";
import { RateStars } from "./RateStars";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  thinking?: boolean;
}

export interface PendingRisk {
  callId: string;
  tool: string;
  argsPreview: string;
  risk: "SAFE" | "LOW" | "MEDIUM" | "HIGH";
}

interface Props {
  messages: ChatMessage[];
  pendingRisks: PendingRisk[];
  onRiskRespond: (callId: string, response: "y" | "n" | "all" | "never") => void;
  onRate: (messageId: string, score: 1 | 2 | 3 | 4 | 5, reason?: string) => void;
}

export function MessageList({ messages, pendingRisks, onRiskRespond, onRate }: Props) {
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
          {m.role === "assistant" && !m.thinking && !m.streaming && (
            <RateStars messageId={m.id} onRate={onRate} />
          )}
          <hr className="border-border" />
        </div>
      ))}
      {pendingRisks.map((r) => (
        <RiskConfirm key={r.callId} {...r} onRespond={onRiskRespond} />
      ))}
    </div>
  );
}
