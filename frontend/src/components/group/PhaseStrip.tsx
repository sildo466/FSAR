// SPDX-License-Identifier: MIT
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { RoomPhase } from "../../stores/group";

interface Props {
  phase: RoomPhase;
  /** Why the phase last moved. Shown verbatim from the server's own value, so
   *  a new reason is visible rather than silently dropped. */
  reason: string;
  onSetGoal: (goal: string) => void;
  onConfirmDone: () => void;
}

export function PhaseStrip({ phase, reason, onSetGoal, onConfirmDone }: Props) {
  const { t } = useTranslation();
  const [goal, setGoal] = useState("");

  return (
    <div
      data-testid="phase-strip"
      data-phase={phase}
      data-reason={reason}
      role="region"
      aria-label={t("group.phase.aria")}
      className="flex items-center gap-3 border-b border-border px-4 py-1.5 text-[11px] sm:px-8"
    >
      <span className="shrink-0 font-mono uppercase tracking-wide text-text-muted">
        {t(`group.phase.${phase}`)}
      </span>
      {reason ? (
        <span data-testid="phase-reason" className="shrink-0 text-text-faint">
          {t(`group.phase.reason.${reason}`, { defaultValue: reason })}
        </span>
      ) : null}

      {phase === "chat" ? (
        <form
          data-testid="goal-form"
          className="flex flex-1 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const trimmed = goal.trim();
            if (trimmed) onSetGoal(trimmed);
          }}
        >
          <input
            data-testid="goal-input"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder={t("group.phase.goalPlaceholder")}
            className="min-w-0 flex-1 rounded border border-border bg-transparent px-2 py-1 text-text placeholder:text-text-faint focus:outline-none"
          />
        </form>
      ) : (
        <span className="flex-1" />
      )}

      {phase === "review" ? (
        <button
          type="button"
          data-testid="confirm-done"
          onClick={onConfirmDone}
          className="shrink-0 rounded border border-border px-2 py-1 text-text-muted transition-colors hover:text-text"
        >
          {t("group.phase.confirm")}
        </button>
      ) : null}
    </div>
  );
}
