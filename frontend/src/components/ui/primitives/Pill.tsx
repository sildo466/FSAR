import { motion } from "framer-motion";
import type { ReactNode } from "react";
import type { HTMLMotionProps } from "framer-motion";
import { cn } from "../../../lib/cn";
import { springs } from "../../../lib/motion/springs";

interface PillProps extends HTMLMotionProps<"button"> {
  variant?: "primary" | "ghost" | "glass";
  size?: "sm" | "md" | "lg";
  icon?: ReactNode;
  loading?: boolean;
}

export function Pill({ variant = "glass", size = "md", icon, loading, children, className, disabled, ...props }: PillProps) {
  return (
    <motion.button
      whileHover={{ scale: disabled ? 1 : 1.04 }}
      whileTap={{ scale: disabled ? 1 : 0.94 }}
      transition={springs.bouncy}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-full font-medium transition disabled:cursor-not-allowed disabled:opacity-40",
        variant === "primary" && "bg-accent text-bg shadow-[0_0_24px_var(--glow-soft)]",
        variant === "ghost" && "text-text-muted hover:bg-glass hover:text-text",
        variant === "glass" && "glass text-text",
        size === "sm" && "h-8 px-3 text-xs",
        size === "md" && "h-10 px-5 text-sm",
        size === "lg" && "h-12 px-7 text-sm",
        className,
      )}
      {...props}
    >
      {loading ? <span className="thinking-dots" aria-label="Loading"><i /><i /><i /></span> : <>{icon}{children}</>}
    </motion.button>
  );
}
