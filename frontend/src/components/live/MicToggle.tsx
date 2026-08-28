// SPDX-License-Identifier: MIT
import { Mic, MicOff } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

interface MicToggleProps {
  muted: boolean;
  listening: boolean;
  userSpeaking: boolean;
  onToggle: () => void;
}

export function MicToggle({ muted, listening, userSpeaking, onToggle }: MicToggleProps) {
  const { t } = useTranslation();
  const label = muted ? t("live.micToggle.unmute") : t("live.micToggle.mute");
  return (
    <button
      aria-label={label}
      className={clsx(
        "rounded-full border p-2 transition-colors",
        muted
          ? "border-border text-text-faint"
          : userSpeaking
            ? "border-accent bg-accent/20 text-text"
            : listening
              ? "border-border text-text-muted"
              : "border-border text-text-faint"
      )}
      onClick={onToggle}
    >
      {muted ? <MicOff size={16} strokeWidth={1.5} /> : <Mic size={16} strokeWidth={1.5} />}
    </button>
  );
}
