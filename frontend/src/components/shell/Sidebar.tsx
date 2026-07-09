// SPDX-License-Identifier: Apache-2.0
import { NavLink } from "react-router-dom";
import { MessageSquare, Activity, Brain, BookOpen, BarChart3, Settings, Gauge, UserCircle2 } from "lucide-react";
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
    <nav className="w-[240px] shrink-0 border-r border-border h-full flex flex-col bg-bg">
      <div className="px-6 py-5 font-display font-semibold text-display">
        {t.appName}
      </div>
      <ul className="flex-1 px-2">
        {items.map((it) => (
          <li key={it.to}>
            <NavLink
              to={it.to}
              end={it.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3 h-9 rounded text-text-muted hover:text-text hover:bg-surface",
                  isActive && "text-text bg-surface font-medium border-l-2 border-border-strong pl-[10px]"
                )
              }
            >
              <it.icon size={16} strokeWidth={1.5} />
              <span>{it.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
