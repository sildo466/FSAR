// SPDX-License-Identifier: MIT
import { useTranslation } from "react-i18next";

import type { PatchItem, PatchState } from "../../stores/group";

const STATE_KEY: Record<PatchState, string> = {
  pending: "group.patch.state.pending",
  landed: "group.patch.state.landed",
  rejected: "group.patch.state.rejected",
  superseded: "group.patch.state.superseded",
};

interface Props {
  patches: PatchItem[];
  /** Diffs by patch id. A listing never carries them, so they arrive only
   *  after someone asks to look at one. */
  texts: Record<number, string>;
  onLoad: (patchId: number) => void;
  onDecide: (patchId: number, approve: boolean) => void;
}

export function PatchPanel({ patches, texts, onLoad, onDecide }: Props) {
  const { t } = useTranslation();

  if (patches.length === 0) {
    return (
      <p
        data-testid="patch-empty"
        className="px-3 py-2 text-[11px] text-text-faint"
      >
        {t("group.patch.empty")}
      </p>
    );
  }

  return (
    <ul
      data-testid="patch-list"
      aria-label={t("group.patch.aria")}
      className="flex flex-col gap-1 px-2 py-1"
    >
      {patches.map((patch) => (
        <li
          key={patch.id}
          data-testid="patch-item"
          data-state={patch.state}
          data-member={patch.member_ref}
          className="flex flex-col gap-1 rounded px-1 py-1 text-[11px]"
        >
          <div className="flex items-baseline gap-2">
            <span className="text-text">{patch.member_ref}</span>
            {patch.item_key ? (
              <span className="text-text-muted">{patch.item_key}</span>
            ) : null}
            <span className="text-text-faint">{patch.size} B</span>
            <span className="ml-auto text-text-muted">
              {t(STATE_KEY[patch.state])}
            </span>
            <button
              type="button"
              data-testid="patch-view"
              onClick={() => onLoad(patch.id)}
              className="shrink-0 text-text-muted hover:text-text"
            >
              {t("group.patch.view")}
            </button>
            {patch.state === "pending" ? (
              <>
                <button
                  type="button"
                  data-testid="patch-approve"
                  onClick={() => onDecide(patch.id, true)}
                  className="shrink-0 text-text-muted hover:text-text"
                >
                  {t("group.patch.approve")}
                </button>
                <button
                  type="button"
                  data-testid="patch-reject"
                  onClick={() => onDecide(patch.id, false)}
                  className="shrink-0 text-text-muted hover:text-text"
                >
                  {t("group.patch.reject")}
                </button>
              </>
            ) : null}
          </div>
          {texts[patch.id] ? (
            <pre
              data-testid="patch-diff"
              className="max-h-64 overflow-auto whitespace-pre-wrap break-all bg-surface-sunken px-2 py-1 font-mono text-[10px] text-text-muted"
            >
              {texts[patch.id]}
            </pre>
          ) : null}
          {patch.verdict_reason ? (
            <p data-testid="patch-reason" className="text-text-faint">
              {patch.verdict_reason}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
