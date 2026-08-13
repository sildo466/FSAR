// SPDX-License-Identifier: MIT
import { NavLink } from "react-router-dom";
import { MessageSquare, Activity, Brain, BookOpen, BarChart3, Settings, Gauge, UserCircle2, Layers3, Clock } from "lucide-react";
import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { cn } from "../../lib/cn";

const items = [
  { to: "/", labelKey: "nav.chat", icon: MessageSquare },
  { to: "/reflection", labelKey: "nav.reflection", icon: Activity },
  { to: "/memory", labelKey: "nav.memory", icon: Brain },
  { to: "/library", labelKey: "nav.library", icon: BookOpen },
  { to: "/cards", labelKey: "nav.cards", icon: UserCircle2 },
  { to: "/insights", labelKey: "nav.insights", icon: BarChart3 },
  { to: "/settings", labelKey: "nav.settings", icon: Settings },
  { to: "/usage", labelKey: "nav.usage", icon: Gauge },
  { to: "/intergration", labelKey: "nav.integration", icon: Layers3 },
  { to: "/scheduler", labelKey: "nav.scheduler", icon: Clock },
];

export function Sidebar() {
  const { t } = useTranslation();
  return (
    <motion.nav
      initial={{ x: -24, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      className="glass relative z-20 m-3 flex w-[68px] shrink-0 flex-col items-center rounded-[28px] py-4 shadow-[0_16px_48px_var(--glow-faint)]"
      aria-label="Primary navigation"
    >
      <div className="mb-5 flex h-9 w-9 items-center justify-center rounded-full bg-text font-display text-sm font-semibold text-bg shadow-[0_0_22px_var(--glow-soft)]">
        F
      </div>
      <ul className="flex flex-1 flex-col items-center gap-1">
        {items.map((it) => (
          <li key={it.to}>
            <NavLink
              to={it.to}
              end={it.to === "/"}
              className={({ isActive }) =>
                cn(
                  "group relative flex h-10 w-10 items-center justify-center rounded-full text-text-muted transition-all duration-300 hover:scale-105 hover:bg-glass hover:text-text",
                  isActive && "bg-text text-bg shadow-[0_0_22px_var(--glow-soft)]"
                )
              }
              title={t(it.labelKey)}
            >
              <it.icon size={16} strokeWidth={1.5} />
            </NavLink>
          </li>
        ))}
      </ul>
      <span className="font-mono text-[9px] tracking-[0.18em] text-text-faint">0.2.3</span>
    </motion.nav>
  );
}