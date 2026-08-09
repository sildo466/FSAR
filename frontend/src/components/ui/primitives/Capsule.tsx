import type { HTMLAttributes } from "react";
import { cn } from "../../../lib/cn";

export function Capsule({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass rounded-[24px] p-5", className)} {...props} />;
}
