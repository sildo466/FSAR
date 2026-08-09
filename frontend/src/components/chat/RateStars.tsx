// SPDX-License-Identifier: MIT
import { useState } from "react";
import { useTranslation } from "react-i18next";

interface Props {
  messageId: string;
  onRate: (messageId: string, score: 1 | 2 | 3 | 4 | 5, reason?: string) => Promise<void> | void;
}

export function RateStars({ messageId, onRate }: Props) {
  const { t } = useTranslation();
  const [score, setScore] = useState<0 | 1 | 2 | 3 | 4 | 5>(0);
  const [expanded, setExpanded] = useState(false);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "fail"; text: string } | null>(null);

  if (feedback) {
    return (
      <span
        className={`text-xs ${feedback.kind === "ok" ? "text-green-500" : "text-red-400"}`}
      >
        {feedback.text}
      </span>
    );
  }

  if (score > 0 && !expanded) {
    return <span className="text-text-muted text-xs">{t("rateStars.rated", { score })}</span>;
  }

  const handleSubmit = async () => {
    if (submitting || score === 0) return;
    setSubmitting(true);
    try {
      await onRate(messageId, score as 1 | 2 | 3 | 4 | 5, reason || undefined);
      setExpanded(false);
      setFeedback({ kind: "ok", text: t("rateStars.ratedSuccess", { score }) });
      setTimeout(() => setFeedback(null), 1500);
    } catch (e) {
      setFeedback({ kind: "fail", text: t("rateStars.failed", { error: (e as Error).message ?? t("rateStars.failedUnknown") }) });
      setTimeout(() => setFeedback(null), 1500);
    } finally {
      setSubmitting(false);
    }
  };

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
          aria-label={t("rateStars.rateLabel", { n })}
        />
      ))}
      {expanded && (
        <>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={t("rateStars.reasonPlaceholder")}
            className="ml-2 px-2 h-7 bg-bg border border-border rounded text-xs"
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSubmit();
            }}
          />
          <button
            onClick={() => void handleSubmit()}
            disabled={submitting}
            className="px-2 h-7 rounded border border-border-strong text-xs disabled:opacity-50"
          >
            {submitting ? t("common.loading") : t("rateStars.submit")}
          </button>
        </>
      )}
    </div>
  );
}
