import type { HTMLAttributes } from "react";
import { cn } from "../../../lib/cn";

export function BreathGlow({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("breath-glow", className)} {...props} />;
}
