// SPDX-License-Identifier: MIT
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useCardsStore } from "../../stores/cards";
import { Avatar } from "../ui/Avatar";
import { useState } from "react";
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
import { motion } from "framer-motion";
import { MessageReplayButton } from "./MessageReplayButton";

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
  character_id?: number;
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
  onRegenerate?: () => void;
}

function ToolCallRow({ ev }: { ev: ToolEvent }) {
  return (
    <details className="glass rounded-xl px-3 py-2 text-sm">
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
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <div
      className="my-2 rounded-xl bg-bg/40 text-[12px] text-text-muted ring-1 ring-border"
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
          {open ? t("messageList.thinkingOpen") : t("messageList.thoughtProcess")}
        </span>
      </button>
      {open && (
        <div className="border-t border-border/60 px-3 pb-2 pl-7 italic whitespace-pre-wrap break-words">
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

export function MessageList({ messages, pendingRisks, onRespond, onRate, onRegenerate }: Props) {
  const { t } = useTranslation();
  const characters = useCardsStore((s) => s.characters);
  const charactersById = useMemo(() => {
    const byId = new Map<number, (typeof characters)[number]>();
    for (const character of characters) byId.set(character.id, character);
    return byId;
  }, [characters]);
  const lastAssistantId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "assistant" && !m.thinking && !m.streaming) return m.id;
    }
    return null;
  }, [messages]);

  return (
    <div className="mx-auto flex max-w-[900px] flex-col gap-5 px-4 py-8 sm:px-8">
      {messages.map((m) => {
        const character = m.character_id != null ? charactersById.get(m.character_id) : undefined;
        return (
        <motion.div key={m.id} initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} className={`flex items-end gap-2 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
          {m.role === "assistant" && (
            <Avatar
              name={m.character_name ?? character?.name ?? t("messageList.assistant")}
              avatarPath={character?.avatar_path}
              cardId={character?.id}
              size={32}
            />
          )}
          <div className={`flex max-w-[min(78%,680px)] flex-col gap-1 ${m.role === "user" ? "items-end" : "items-start"}`}>
          <span className="px-2 text-[10px] font-medium uppercase tracking-[0.14em] text-text-faint">
            {m.role === "user" ? (m.user_name ?? t("messageList.you")) : (m.character_name ?? character?.name ?? t("messageList.assistant"))}
          </span>
          {m.tools?.map((ev) => <ToolCallRow key={ev.callId} ev={ev} />)}
          <div className={`leading-relaxed [&_table]:border-collapse [&_td]:border [&_td]:border-border [&_td]:px-2 [&_th]:border [&_th]:border-border [&_th]:px-2 [&_code]:font-mono [&_code]:text-[13px] [&_pre]:overflow-auto [&_pre]:bg-bg [&_pre]:p-3 [&_pre]:rounded-xl ${m.role === "user" ? "rounded-[24px] rounded-br-md bg-text px-4 py-3 text-bg shadow-[0_8px_24px_var(--glow-faint)]" : "glass rounded-[24px] rounded-bl-md px-4 py-3 text-text"}`}>
            {m.thinking ? (
              <ThinkingDot />
            ) : m.role === "assistant" && !m.streaming ? (
              <AssistantBody content={m.content} />
            ) : (
              <span className="whitespace-pre-wrap">{m.content}</span>
            )}
          </div>
          {m.role === "assistant" && !m.thinking && !m.streaming && (
            <div className="flex w-full items-center justify-between gap-3 px-1">
              <RateStars messageId={m.id} onRate={onRate} />
              <MessageReplayButton messageId={m.id} text={m.content} voiceOverride={String(character?.tts_voice ?? "")} instructionsOverride={String(character?.tts_instructions ?? "")} onRegenerate={m.id === lastAssistantId ? onRegenerate : undefined} />
            </div>
          )}
          </div>
        </motion.div>
        );
      })}
      {pendingRisks.map((r) => (
        <RiskConfirm key={r.callId} {...r} onRespond={onRespond} />
      ))}
    </div>
  );
}
