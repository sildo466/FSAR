// SPDX-License-Identifier: MIT
import { useState } from "react";
import { CalendarDays } from "lucide-react";
import { useTranslation } from "react-i18next";
import { splitBirthday, joinBirthday } from "../../lib/birthday";
import { useWS } from "../../stores/ws";
import { Capsule, Input } from "../ui/primitives";

export function StepBirthday({ onNext, onSkip }: { onNext: () => void; onSkip: () => void }) {
  const { t } = useTranslation();
  const config = useWS((state) => state.config) as Record<string, unknown> | null;
  const send = useWS((state) => state.send);
  const stored = splitBirthday((config?.user as Record<string, unknown> | undefined)?.birthday);
  const [month, setMonth] = useState(stored.month);
  const [day, setDay] = useState(stored.day);
  const [error, setError] = useState("");

  const save = () => {
    const birthday = joinBirthday(month, day);
    if (birthday === null) {
      setError(t("onboarding.birthday.errRange"));
      return;
    }
    setError("");
    send({ type: "settings.patch", patch: { "user.birthday": birthday } });
    send({ type: "onboarding.complete_step", step: "birthday", data: { birthday } });
    onNext();
  };

  const skip = () => {
    send({ type: "onboarding.skip_step", step: "birthday" });
    onSkip();
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="flex items-start gap-4">
        <div className="rounded-2xl bg-text p-3 text-bg"><CalendarDays size={21} /></div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-faint">{t("onboarding.optional")}</p>
          <h2 className="font-display text-3xl italic">{t("onboarding.birthday.title")}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-muted">{t("onboarding.birthday.description")}</p>
        </div>
      </div>
      <Capsule className="mt-7 flex gap-4">
        <label className="flex flex-1 flex-col gap-1 text-caption text-text-muted">
          {t("onboarding.birthday.monthLabel")}
          <Input
            inputMode="numeric"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            placeholder="03"
            data-testid="birthday-month-input"
          />
        </label>
        <label className="flex flex-1 flex-col gap-1 text-caption text-text-muted">
          {t("onboarding.birthday.dayLabel")}
          <Input
            inputMode="numeric"
            value={day}
            onChange={(e) => setDay(e.target.value)}
            placeholder="14"
            data-testid="birthday-day-input"
          />
        </label>
      </Capsule>
      {error && <p role="alert" className="mt-4 text-caption text-red-400">{error}</p>}
      <div className="mt-7 flex gap-3">
        <button type="button" onClick={save} className="rounded-full bg-text px-5 py-2.5 text-sm text-bg">{t("onboarding.saveAndNext")}</button>
        <button type="button" onClick={skip} className="rounded-full border border-border px-5 py-2.5 text-sm text-text-muted hover:text-text">{t("onboarding.skip")}</button>
      </div>
    </div>
  );
}
