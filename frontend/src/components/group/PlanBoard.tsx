// SPDX-License-Identifier: MIT
import { useTranslation } from "react-i18next";

import type { PlanItem } from "../../stores/group";

const MARK: Record<PlanItem["status"], string> = {
  todo: "[ ]",
  doing: "[~]",
  blocked: "[!]",
  done: "[x]",
};

interface Props {
  items: PlanItem[];
  /** Character names by card id. The board carries the ref only, and the page
   *  already holds this room's roster. */
  names: Record<string, string>;
}

export function PlanBoard({ items, names }: Props) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return (
      <p
        data-testid="plan-empty"
        className="px-3 py-2 text-[11px] text-text-faint"
      >
        {t("group.plan.empty")}
      </p>
    );
  }

  return (
    <ul
      data-testid="plan-board"
      aria-label={t("group.plan.aria")}
      className="flex flex-col gap-0.5 px-2 py-1"
    >
      {items.map((item) => (
        <li
          key={item.item_key}
          data-testid="plan-item"
          data-status={item.status}
          data-owner={item.owner_ref ?? ""}
          className="flex items-baseline gap-2 rounded px-1 py-1 text-[11px] transition-colors"
        >
          <span aria-hidden className="shrink-0 font-mono text-text-faint">
            {MARK[item.status]}
          </span>
          <span className="flex-1 text-text">{item.text}</span>
          <span className="shrink-0 text-text-muted">
            {item.owner_ref
              ? (names[item.owner_ref] ?? item.owner_ref)
              : t("group.plan.unassigned")}
          </span>
          {item.commit_ref ? (
            <code
              data-testid="plan-commit"
              title={item.commit_ref}
              className="shrink-0 font-mono text-text-faint"
            >
              {item.commit_ref.slice(0, 7)}
            </code>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
