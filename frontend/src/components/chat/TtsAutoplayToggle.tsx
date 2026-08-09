// SPDX-License-Identifier: MIT
import { useTranslation } from "react-i18next";
import { Volume2, VolumeX } from "lucide-react";
import { useSpeechStore } from "../../stores/speech";

export function TtsAutoplayToggle() {
  const { t } = useTranslation();
  const configured = useSpeechStore((state) => state.isTtsConfigured);
  const autoplay = useSpeechStore((state) => state.autoplay);
  const toggle = useSpeechStore((state) => state.toggleAutoplay);
  if (!configured) return null;
  return <button type="button" onClick={toggle} aria-label={t("ttsAutoplay.aria", { state: autoplay ? t("common.on") : t("common.off") })} title={autoplay ? t("ttsAutoplay.onTitle") : t("ttsAutoplay.offTitle")} className={`flex h-8 w-8 items-center justify-center rounded-full transition hover:bg-glass ${autoplay ? "text-text" : "text-text-muted"}`}>{autoplay ? <Volume2 size={14} /> : <VolumeX size={14} />}</button>;
}
