// SPDX-License-Identifier: Apache-2.0
import { NavLink } from "react-router-dom";
import { MessageSquare, Activity, Brain, BookOpen, BarChart3, Settings, Gauge, UserCircle2 } from "lucide-react";
import { motion } from "framer-motion";
import { t } from "../../lib/i18n";
import { cn } from "../../lib/cn";

const items = [
  { to: "/", label: t.navChat, icon: MessageSquare },
  { to: "/reflection", label: t.navReflection, icon: Activity },
  { to: "/memory", label: t.navMemory, icon: Brain },
  { to: "/library", label: t.navLibrary, icon: BookOpen },
  { to: "/cards", label: "Cards", icon: UserCircle2 },
  { to: "/insights", label: t.navInsights, icon: BarChart3 },
  { to: "/settings", label: t.navSettings, icon: Settings },
  { to: "/usage", label: t.navUsage, icon: Gauge },
];

export function Sidebar() {
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
              title={it.label}
            >
              <it.icon size={16} strokeWidth={1.5} />
            </NavLink>
          </li>
        ))}
      </ul>
      <span className="font-mono text-[9px] tracking-[0.18em] text-text-faint">0.1</span>
    </motion.nav>
  );
}
