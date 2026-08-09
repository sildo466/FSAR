// SPDX-License-Identifier: MIT
import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import type { SlashCommand } from "../../lib/commands";

interface Props {
  filter: string;
  commands: SlashCommand[];
  selected: number;
  onSelect: (cmd: SlashCommand) => void;
  onClose: () => void;
}

export function SlashPopover({ filter, commands, selected, onSelect, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  if (commands.length === 0) {
    return (
      <motion.div
        ref={ref}
        initial={{ opacity: 0, y: 8, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.16, ease: "easeOut" }}
        className="absolute bottom-full mb-2 w-[480px] max-h-[280px] bg-surface border border-border rounded p-3 text-text-muted font-mono text-xs"
      >
        No commands match "{filter}"
      </motion.div>
    );
  }

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.16, ease: "easeOut" }}
      className="absolute bottom-full mb-2 w-[480px] max-h-[280px] bg-surface border border-border rounded overflow-auto"
    >
      {commands.map((c, i) => (
        <button
          key={c.name}
          onClick={() => onSelect(c)}
          className={`w-full text-left px-4 py-2 flex items-center gap-4 ${
            i === selected ? "bg-bg" : ""
          }`}
        >
          <span className="font-mono text-[13px] font-medium w-24 shrink-0">/{c.name}</span>
          <span className="text-[13px] flex-1">{c.description}</span>
          <span className="font-mono text-[11px] text-text-muted">{c.usage}</span>
        </button>
      ))}
    </motion.div>
  );
}
