import { motion } from "framer-motion";
import type { ReactNode } from "react";
import type { HTMLMotionProps } from "framer-motion";
import { cn } from "../../../lib/cn";
import { springs } from "../../../lib/motion/springs";

interface GlassProps extends HTMLMotionProps<"div"> {
  intensity?: "low" | "med" | "high";
  children: ReactNode;
}

export function Glass({ intensity = "med", className, children, ...props }: GlassProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.985 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={springs.default}
      className={cn(intensity === "high" ? "glass-strong" : "glass", intensity === "low" && "backdrop-blur-lg", className)}
      {...props}
    >
      {children}
    </motion.div>
  );
}
