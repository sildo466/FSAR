// SPDX-License-Identifier: MIT
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { BreathGlow } from "./primitives";

interface GreetingLine {
  key: string;
  hours?: number[];
}

const LINES: GreetingLine[] = [
  { key: "chat.greeting.morning", hours: [6, 7, 8, 9, 10, 11] },
  { key: "chat.greeting.lunch", hours: [12, 13] },
  { key: "chat.greeting.afternoon", hours: [14, 15, 16, 17] },
  { key: "chat.greeting.evening", hours: [18, 19, 20, 21] },
  { key: "chat.greeting.lateNight", hours: [22, 23, 0, 1, 2, 3, 4, 5] },
  { key: "chat.greeting.default1" },
  { key: "chat.greeting.default2" },
  { key: "chat.greeting.default3" },
  { key: "chat.greeting.default4" },
  { key: "chat.greeting.default5" },
];

function pickLine(): GreetingLine {
  const hour = new Date().getHours();
  const eligible = LINES.filter((g) => !g.hours || g.hours.includes(hour));
  return eligible[Math.floor(Math.random() * eligible.length)];
}

export function Greeting() {
  const { t } = useTranslation();
  const [line] = useState(pickLine);
  return (
    <BreathGlow className="text-center text-text-muted">
      <p className="font-display text-2xl italic tracking-[-0.015em] text-text">
        {t(line.key)}
      </p>
      <p className="mt-2 text-sm">{t("chat.greeting.ask")}</p>
    </BreathGlow>
  );
}