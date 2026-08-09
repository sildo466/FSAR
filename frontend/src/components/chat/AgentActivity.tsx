// SPDX-License-Identifier: MIT
import { useTranslation } from "react-i18next";
import {
  CheckCircle2,
  CircleDot,
  LoaderCircle,
  XCircle,
} from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "../../lib/cn";

export interface AgentStatus {
  task_id: string;
  agent_id: string;
  parent_id: string | null;
  depth: number;
  kind: "main" | "subagent";
  label: string;
  status: string;
  detail: string;
}

const ACTIVE = new Set([
  "queued",
  "running",
  "planning",
  "thinking",
  "delegating",
  "working",
  "reflecting",
  "verifying",
  "executing",
]);

function StatusIcon({ status }: { status: string }) {
  if (status === "completed") {
    return <CheckCircle2 size={14} className="text-success" strokeWidth={1.8} />;
  }
  if (status === "failed" || status === "cancelled") {
    return <XCircle size={14} className="text-danger" strokeWidth={1.8} />;
  }
  if (ACTIVE.has(status)) {
    return <LoaderCircle size={14} className="animate-spin text-warning" strokeWidth={1.8} />;
  }
  return <CircleDot size={14} className="text-text-muted" strokeWidth={1.8} />;
}

export function AgentActivity({ agents }: { agents: AgentStatus[] }) {
  const { t } = useTranslation();
  if (agents.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      role="region"
      aria-label={t("agentActivity.aria")}
      className="border-b border-border bg-[color:var(--glass)]/35 px-4 py-2 sm:px-8"
    >
      <div className="mx-auto flex max-w-[900px] items-center gap-2 overflow-x-auto">
        <div className="mr-1 flex shrink-0 items-center gap-2 font-mono text-[10px] uppercase text-text-faint">
          <span className="relative flex h-2 w-2">
            {agents.some((agent) => ACTIVE.has(agent.status)) && (
              <span className="absolute inset-0 animate-ping rounded-full bg-warning/50" />
            )}
            <span className="relative h-2 w-2 rounded-full bg-warning" />
          </span>
          Agents
        </div>
        {agents.map((agent) => (
          <div
            key={agent.agent_id}
            title={agent.detail}
            className={cn(
              "flex h-8 shrink-0 items-center gap-2 border-l border-border px-3",
              agent.kind === "main" && "border-l-0 pl-1",
            )}
          >
            <StatusIcon status={agent.status} />
            <span className="max-w-32 truncate text-[11px] font-medium text-text">
              {agent.label}
            </span>
            <span className="max-w-40 truncate font-mono text-[10px] text-text-muted">
              {agent.detail}
            </span>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
