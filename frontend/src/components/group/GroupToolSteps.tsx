// SPDX-License-Identifier: MIT
import { useTranslation } from "react-i18next";
import { ToolCallRow } from "../chat/MessageList";
import type { ToolEvent } from "../../lib/toolEvents";

interface Props {
  steps: ToolEvent[];
  /** The chat page keeps every step open. A room folds them, because several
   *  characters can be working through their own at the same time. */
  defaultOpen?: boolean;
}

/**
 * One character's tool steps: the newest on screen, the rest folded away.
 *
 * A concurrent round puts several of these up together, so only the newest line
 * has to be visible — expanding is for reading back what happened, not for
 * following it. `n` rather than `count` in the label because i18next reads
 * `count` as a plural selector, and this text is one string for every number.
 */
export function GroupToolSteps({ steps, defaultOpen = false }: Props) {
  const { t } = useTranslation();
  if (steps.length === 0) return null;
  const newest = steps[steps.length - 1];
  const earlier = steps.slice(0, -1);
  return (
    <div className="mt-1 flex flex-col gap-1">
      {earlier.length > 0 && (
        <details
          open={defaultOpen}
          data-testid="folded-tool-steps"
          className="text-[10px] text-text-faint"
        >
          <summary className="cursor-pointer select-none">
            {t("group.earlierToolSteps", { n: earlier.length })}
          </summary>
          <div className="mt-1 flex flex-col gap-1">
            {earlier.map((ev) => (
              <ToolCallRow key={ev.callId} ev={ev} />
            ))}
          </div>
        </details>
      )}
      <ToolCallRow ev={newest} />
    </div>
  );
}
