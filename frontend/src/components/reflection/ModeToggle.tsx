// SPDX-License-Identifier: MIT
import type { ReactNode } from "react";

interface Props {
  label: string;
  description: string;
  enabled: boolean;
  onToggle: (v: boolean) => void;
  children?: ReactNode;
}

export function ModeToggle({ label, description, enabled, onToggle, children }: Props) {
  return (
    <div className="flex flex-col gap-2 py-2">
      <button onClick={() => onToggle(!enabled)} className="flex items-center gap-3 text-left">
        <span
          className={`inline-block w-4 h-4 border border-border-strong ${
            enabled ? "bg-text" : ""
          }`}
        />
        <span className="text-[14px] font-medium">{label}</span>
        <span className="text-[13px] text-text-muted">— {description}</span>
      </button>
      {enabled && children && <div className="ml-7">{children}</div>}
    </div>
  );
}
