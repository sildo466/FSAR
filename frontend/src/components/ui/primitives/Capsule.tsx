import type { HTMLAttributes } from "react";
import { cn } from "../../../lib/cn";

export function Capsule({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("card-tex rounded-[24px] border border-[var(--card-border)] bg-[var(--card-bg)] p-5 backdrop-blur-[22px]", className)} {...props} />;
}
