// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { PluggableList } from "unified";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { ChevronRight } from "lucide-react";
import { ThinkingDot } from "./ThinkingDot";
import { RiskConfirm } from "./RiskConfirm";
import { RateStars } from "./RateStars";
import { splitThinkBlocks } from "../../lib/thinking";

// `throwOnError: false` lets partial LaTeX (common during streaming) render
// as plain text instead of crashing the assistant bubble mid-sentence.
const REMARK_PLUGINS: PluggableList = [remarkGfm, remarkMath];
const REHYPE_PLUGINS: PluggableList = [[rehypeKatex, { throwOnError: false }]];

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
  character_name?: string;
  user_name?: string;
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
  onRespond: (callId: string, response: "y" | "n" | "all" | "never") => void;
  onRate: (messageId: string, score: 1 | 2 | 3 | 4 | 5, reason?: string) => Promise<void> | void;
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

function ThinkingBlock({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="my-2 rounded border border-border bg-bg/40 text-[12px] text-text-muted"
      data-testid="thinking-block"
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:text-text"
      >
        <ChevronRight
          className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`}
        />
        <span className="font-display tracking-[0.06em] uppercase">
          {open ? "Thinking" : "Thought process"}
        </span>
      </button>
      {open && (
        <div className="px-3 pb-2 pl-7 italic whitespace-pre-wrap break-words border-t border-border/60">
          {content}
        </div>
      )}
    </div>
  );
}

function AssistantBody({ content }: { content: string }) {
  const segments = useMemo(() => splitThinkBlocks(content), [content]);
  const hasThink = segments.some((s) => s.kind === "think");
  // Fast path: no closed think blocks → single ReactMarkdown pass.
  if (!hasThink) {
    return (
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS} rehypePlugins={REHYPE_PLUGINS}>
        {content}
      </ReactMarkdown>
    );
  }
  return (
    <>
      {segments.map((seg, i) =>
        seg.kind === "think" ? (
          <ThinkingBlock key={`think-${i}`} content={seg.content} />
        ) : seg.content.trim() ? (
          <ReactMarkdown
            key={`md-${i}`}
            remarkPlugins={REMARK_PLUGINS}
            rehypePlugins={REHYPE_PLUGINS}
          >
            {seg.content}
          </ReactMarkdown>
        ) : null
      )}
    </>
  );
}

export function MessageList({ messages, pendingRisks, onRespond, onRate }: Props) {
  return (
    <div className="flex flex-col gap-6 max-w-[720px] mx-auto px-8 py-6">
      {messages.map((m) => (
        <div key={m.id} className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <span className="font-display text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              {m.role === "user"
                ? (m.user_name ?? "USER")
                : (m.character_name ?? "ASSISTANT")}
            </span>
            <span className="font-mono text-xs text-text-muted">just now</span>
          </div>
          {m.tools?.map((ev) => <ToolCallRow key={ev.callId} ev={ev} />)}
          <div className="text-text leading-relaxed [&_table]:border-collapse [&_td]:border [&_td]:border-border [&_td]:px-2 [&_th]:border [&_th]:border-border [&_th]:px-2 [&_code]:font-mono [&_code]:text-[13px] [&_pre]:overflow-auto [&_pre]:bg-bg [&_pre]:p-3 [&_pre]:rounded">
            {m.thinking ? (
              <ThinkingDot />
            ) : m.role === "assistant" && !m.streaming ? (
              <AssistantBody content={m.content} />
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
        <RiskConfirm key={r.callId} {...r} onRespond={onRespond} />
      ))}
    </div>
  );
}
