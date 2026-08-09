import type { HTMLMotionProps } from "framer-motion";
import { motion } from "framer-motion";
import { cn } from "../../../lib/cn";
import { springs } from "../../../lib/motion/springs";

export function IconButton({ className, children, ...props }: HTMLMotionProps<"button">) {
  return <motion.button whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.9 }} transition={springs.bouncy} className={cn("glass inline-flex h-9 w-9 items-center justify-center rounded-full text-text-muted hover:text-text", className)} {...props}>{children}</motion.button>;
}
