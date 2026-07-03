// SPDX-License-Identifier: Apache-2.0
import { t } from "../../lib/i18n";

interface Props {
  displayName?: string;
}

function pickGreeting(hour: number): string {
  if (hour < 6) return t.greetingNight;
  if (hour < 12) return t.greetingMorning;
  if (hour < 18) return t.greetingAfternoon;
  if (hour < 22) return t.greetingEvening;
  return t.greetingNight;
}

export function Greeting({ displayName = "" }: Props) {
  const hour = new Date().getHours();
  const greeting = pickGreeting(hour);
  const headline = displayName ? `${greeting}, ${displayName}.` : `${greeting}.`;
  return (
    <div className="text-center text-text-muted">
      <p className="font-display text-[18px] font-semibold tracking-[-0.005em] text-text">
        {headline}
      </p>
      <p className="mt-2 text-sm">{t.greetingAsk}</p>
    </div>
  );
}
