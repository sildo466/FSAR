// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { t } from "../../lib/i18n";

interface GreetingLine {
  text: string;
  hours?: number[];
}

const LINES: GreetingLine[] = [
  { text: "Good morning. FSAR is here.", hours: [6, 7, 8, 9, 10, 11] },
  { text: "Lunch hour. Need anything quick?", hours: [12, 13] },
  { text: "Good afternoon. FSAR is here.", hours: [14, 15, 16, 17] },
  { text: "Good evening. Wrapping up or starting fresh?", hours: [18, 19, 20, 21] },
  { text: "Late night. Let's get this done.", hours: [22, 23, 0, 1, 2, 3, 4, 5] },
  { text: "FSAR is here. What's on your mind?" },
  { text: "Ready when you are." },
  { text: "What are we doing today?" },
  { text: "How can I help?" },
  { text: "Tell me what you need." },
];

function pickLine(): GreetingLine {
  const hour = new Date().getHours();
  const eligible = LINES.filter((g) => !g.hours || g.hours.includes(hour));
  return eligible[Math.floor(Math.random() * eligible.length)];
}

export function Greeting() {
  const [line] = useState(pickLine);
  return (
    <div className="text-center text-text-muted">
      <p className="font-display text-[18px] font-semibold tracking-[-0.005em] text-text">
        {line.text}
      </p>
      <p className="mt-2 text-sm">{t.greetingAsk}</p>
    </div>
  );
}
