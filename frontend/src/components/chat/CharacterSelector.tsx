// SPDX-License-Identifier: MIT
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";
import { useCardsStore } from "../../stores/cards";

export function CharacterSelector({ sessionId }: { sessionId: string }) {
  const characters = useCardsStore((s) => s.characters);
  const refresh = useCardsStore((s) => s.refresh);
  const sessionCharacters = useCardsStore((s) => s.sessionCharacters);
  const draftCharacterId = useCardsStore((s) => s.draftCharacterId);
  const loadSessionCharacter = useCardsStore((s) => s.loadSessionCharacter);
  const setSessionCharacter = useCardsStore((s) => s.setSessionCharacter);
  const setDraftCharacter = useCardsStore((s) => s.setDraftCharacter);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (characters.length === 0) refresh();
  }, [characters.length, refresh]);

  useEffect(() => {
    if (sessionId) loadSessionCharacter(sessionId);
  }, [sessionId, loadSessionCharacter]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const pick = (cid: number) => {
    if (sessionId) setSessionCharacter(sessionId, cid);
    else setDraftCharacter(cid);
    setOpen(false);
  };

  const currentId =
    (sessionId ? sessionCharacters[sessionId] : draftCharacterId) ??
    characters.find((c) => c.is_default === 1)?.id ??
    characters[0]?.id ??
    "";
  const current = characters.find((c) => c.id === currentId);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label="character"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="glass flex h-9 max-w-[170px] items-center gap-1.5 rounded-full px-3 font-mono text-[11px] text-text transition hover:bg-glass-strong"
      >
        <span className="truncate">
          {current ? `${current.name}${current.is_default === 1 ? " (default)" : ""}` : ""}
        </span>
        <ChevronDown size={11} className={`shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            role="listbox"
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="glass-strong absolute left-0 top-11 z-50 max-h-72 w-60 overflow-auto rounded-2xl p-1 shadow-[0_16px_44px_var(--glow-faint)]"
          >
            {characters.map((c) => (
              <button
                type="button"
                key={c.id}
                role="option"
                aria-selected={c.id === currentId}
                onClick={() => pick(c.id)}
                className={`flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left text-[12px] transition hover:bg-glass ${
                  c.id === currentId ? "bg-glass text-text" : "text-text-muted hover:text-text"
                }`}
              >
                <span className="truncate">
                  {c.name}{c.is_default === 1 ? " (default)" : ""}
                </span>
                {c.id === currentId && <Check size={12} className="shrink-0" />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
