// SPDX-License-Identifier: MIT
import { useTranslation } from "react-i18next";
import { Sun, Moon, Monitor } from "lucide-react";
import { motion } from "framer-motion";
import { useWS } from "../../stores/ws";
import { useUI, type Theme } from "../../stores/ui";
import { CharacterSelector } from "../chat/CharacterSelector";
import { UserSelector } from "../chat/UserSelector";
import { useSessions } from "../../stores/sessions";
import { useChatUI } from "../../stores/chat-ui";
import { WorkspacePill } from "../workspace/WorkspacePill";
import { ModelEffortSwitcher } from "../chat/ModelEffortSwitcher";
import { TierSwitcher } from "../chat/TierSwitcher";
import { TtsAutoplayToggle } from "../chat/TtsAutoplayToggle";
import { ChatModelPicker } from "../ChatModelPicker";
import { TokenMeter } from "./TokenMeter";

export function Topbar() {
  const { t } = useTranslation();
  const send = useWS((s) => s.send);
  const theme = useUI((s) => s.theme);
  const setTheme = useUI((s) => s.setTheme);
  const currentId = useSessions((s) => s.currentId);
  const mode = useChatUI((s) => s.mode);
  const setMode = useChatUI((s) => s.setMode);

  function cycle(event: React.MouseEvent<HTMLButtonElement>) {
    const next: Theme = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
    const apply = () => { setTheme(next); send({ type: "style.set_theme", theme: next }); };
    const root = document.documentElement;
    const radius = Math.hypot(Math.max(event.clientX, innerWidth - event.clientX), Math.max(event.clientY, innerHeight - event.clientY));
    root.style.setProperty("--clip-x", `${event.clientX}px`);
    root.style.setProperty("--clip-y", `${event.clientY}px`);
    root.style.setProperty("--clip-size", `${radius}px`);
    const documentWithTransition = document as Document & { startViewTransition?: (update: () => void) => void };
    if (documentWithTransition.startViewTransition) documentWithTransition.startViewTransition(apply);
    else apply();
  }

  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;

  return (
    <motion.header initial={{ y: -16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="glass fixed left-[5.5rem] right-3 top-3 z-30 flex h-12 items-center justify-between rounded-full px-2 shadow-[0_12px_36px_var(--glow-faint)] sm:px-4">
      <div className="flex items-center gap-2">
        <div className="hidden text-[13px] text-text-muted font-mono md:block">FSAR · local-first agent</div>
        <TokenMeter />
        <button
          onClick={cycle}
          title={t("settings.style.theme") + `: ${theme}`}
          className="flex h-8 w-8 items-center justify-center rounded-full text-text-muted transition hover:bg-glass hover:text-text"
        >
          <ThemeIcon size={12} strokeWidth={1.5} />
        </button>
      </div>
      <div className="glass absolute left-1/2 hidden -translate-x-1/2 items-center gap-1 rounded-full p-1 lg:flex">
        <CharacterSelector sessionId={currentId ?? ""} />
        <div className="flex rounded-full bg-[var(--chip-bg)] p-0.5">
          {(["agent", "companion"] as const).map((item) => <button key={item} onClick={() => setMode(item)} className={`rounded-full px-3 py-1.5 text-[9px] font-semibold uppercase tracking-wider transition ${mode === item ? "bg-[var(--button-bg)] text-[var(--button-text)] button-tex" : "text-text-muted"}`}>{item === "agent" ? t("mode.agent") : t("mode.companion")}</button>)}
        </div>
        <UserSelector />
      </div>
      <div className="flex items-center gap-2">
        <ChatModelPicker />
        <TierSwitcher />
        <ModelEffortSwitcher />
        <TtsAutoplayToggle />
        <div className="hidden sm:block"><WorkspacePill /></div>
      </div>
    </motion.header>
  );
}
