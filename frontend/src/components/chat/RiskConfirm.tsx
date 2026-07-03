// SPDX-License-Identifier: Apache-2.0
interface Props {
  callId: string;
  tool: string;
  argsPreview: string;
  risk: "SAFE" | "LOW" | "MEDIUM" | "HIGH";
  onRespond: (callId: string, response: "y" | "n" | "all" | "never") => void;
}

export function RiskConfirm({ callId, tool, argsPreview, risk, onRespond }: Props) {
  if (risk === "SAFE") return null;
  return (
    <div className="border border-border rounded p-3 my-2 max-w-[720px]">
      <div className="flex items-center justify-between mb-2">
        <span className="font-display text-[11px] font-semibold uppercase tracking-[0.08em]">
          {tool}
        </span>
        <span className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted">
          {risk}
        </span>
      </div>
      <div className="font-mono text-xs text-text-muted mb-3 whitespace-pre-wrap break-all">
        {argsPreview}
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => onRespond(callId, "n")}
          className="px-3 h-8 rounded border border-border hover:bg-bg"
        >
          Cancel
        </button>
        <button
          onClick={() => onRespond(callId, "all")}
          className="px-3 h-8 rounded border border-border hover:bg-bg"
        >
          Trust this session
        </button>
        <button
          onClick={() => onRespond(callId, "y")}
          className="px-3 h-8 rounded border border-border-strong bg-text text-surface hover:opacity-90"
        >
          Send anyway
        </button>
      </div>
    </div>
  );
}
