// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";

interface Props {
  messageId: string;
  onRate: (messageId: string, score: 1 | 2 | 3 | 4 | 5, reason?: string) => void;
}

export function RateStars({ messageId, onRate }: Props) {
  const [score, setScore] = useState<0 | 1 | 2 | 3 | 4 | 5>(0);
  const [expanded, setExpanded] = useState(false);
  const [reason, setReason] = useState("");

  if (score > 0 && !expanded) {
    return <span className="text-text-muted text-xs">rated {score}/5</span>;
  }

  return (
    <div className="flex items-center gap-2 mt-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          onClick={() => {
            setScore(n as 1 | 2 | 3 | 4 | 5);
            setExpanded(true);
          }}
          className={`w-4 h-4 border border-border-strong rounded-sm ${
            n <= score ? "bg-text" : ""
          }`}
          aria-label={`Rate ${n}`}
        />
      ))}
      {expanded && (
        <>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why? (optional)"
            className="ml-2 px-2 h-7 bg-bg border border-border rounded text-xs"
          />
          <button
            onClick={() => onRate(messageId, score as 1 | 2 | 3 | 4 | 5, reason || undefined)}
            className="px-2 h-7 rounded border border-border-strong text-xs"
          >
            Submit
          </button>
        </>
      )}
    </div>
  );
}
