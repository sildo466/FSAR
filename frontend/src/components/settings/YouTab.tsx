// SPDX-License-Identifier: MIT
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { splitBirthday, joinBirthday } from "../../lib/birthday";
import { useWS } from "../../stores/ws";
import { Capsule } from "../ui/primitives";

const FIELD = "rounded-lg border border-border bg-bg/30 px-3 py-1.5 text-[12px]";

export function YouTab() {
  const { t } = useTranslation();
  const send = useWS((s) => s.send);
  const config = useWS((s) => s.config) as Record<string, unknown> | null;
  const stored = splitBirthday((config?.user as Record<string, unknown> | undefined)?.birthday);
  const [month, setMonth] = useState(stored.month);
  const [day, setDay] = useState(stored.day);
  const [error, setError] = useState("");

  const save = () => {
    const birthday = joinBirthday(month, day);
    if (birthday === null) {
      setError(t("settings.you.errRange"));
      return;
    }
    setError("");
    send({ type: "settings.patch", patch: { "user.birthday": birthday } });
  };

  const clear = () => {
    setMonth("");
    setDay("");
    setError("");
    send({ type: "settings.patch", patch: { "user.birthday": null } });
  };

  return (
    <Capsule className="flex flex-col gap-3">
      <h2 className="font-display text-sm font-semibold">{t("settings.you.title")}</h2>
      <p className="text-[12px] text-text-muted">{t("settings.you.hint")}</p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-[12px] text-text-muted">
          {t("settings.you.monthLabel")}
          <input
            inputMode="numeric"
            className={FIELD}
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            placeholder="03"
            data-testid="you-birthday-month"
          />
        </label>
        <label className="flex flex-col gap-1 text-[12px] text-text-muted">
          {t("settings.you.dayLabel")}
          <input
            inputMode="numeric"
            className={FIELD}
            value={day}
            onChange={(e) => setDay(e.target.value)}
            placeholder="14"
            data-testid="you-birthday-day"
          />
        </label>
        <button onClick={save} className="rounded-full bg-[var(--button-bg)] text-[var(--button-text)] button-tex px-4 py-1.5 text-[12px]">{t("settings.you.save")}</button>
        <button onClick={clear} className="rounded-full border border-border px-4 py-1.5 text-[12px] text-text-muted hover:text-text">{t("settings.you.clear")}</button>
        {error && <span role="alert" className="text-[12px] text-red-500">{error}</span>}
      </div>
    </Capsule>
  );
}
