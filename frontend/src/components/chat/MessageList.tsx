// SPDX-License-Identifier: Apache-2.0
import ReactMarkdown from "react-markdown";
import { ThinkingDot } from "./ThinkingDot";
import { RiskConfirm } from "./RiskConfirm";
import { RateStars } from "./RateStars";

export interface ToolEvent {
  callId: string;
  tool: string;
  argsPreview: string;
  result?: string;
  latencyMs?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  thinking?: boolean;
  tools?: ToolEvent[];
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

function ToolCallRow({ ev }: { ev: ToolEvent }) {
  return (
    <details className="border border-border rounded px-3 py-2 my-1 text-sm">
      <summary className="cursor-pointer select-none">
        <span className="font-mono text-[12px] font-medium">{ev.tool}</span>
        <span className="ml-2 font-mono text-[11px] text-text-muted">
          {ev.result === undefined
            ? "running…"
            : `done${ev.latencyMs ? ` · ${ev.latencyMs}ms` : ""}`}
        </span>
      </summary>
      <div className="mt-2 font-mono text-[11px] text-text-muted whitespace-pre-wrap break-all">
        {ev.argsPreview}
      </div>
      {ev.result !== undefined && (
        <div className="mt-2 font-mono text-[11px] whitespace-pre-wrap break-all max-h-48 overflow-auto">
          {ev.result}
        </div>
      )}
    </details>
  );
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
          {m.tools?.map((ev) => <ToolCallRow key={ev.callId} ev={ev} />)}
          <div className="text-text leading-relaxed [&_table]:border-collapse [&_td]:border [&_td]:border-border [&_td]:px-2 [&_th]:border [&_th]:border-border [&_th]:px-2 [&_code]:font-mono [&_code]:text-[13px] [&_pre]:overflow-auto [&_pre]:bg-bg [&_pre]:p-3 [&_pre]:rounded">
            {m.thinking ? (
              <ThinkingDot />
            ) : m.role === "assistant" ? (
              <ReactMarkdown>{m.content}</ReactMarkdown>
            ) : (
              <span className="whitespace-pre-wrap">{m.content}</span>
            )}
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
