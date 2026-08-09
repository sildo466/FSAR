import type { HTMLAttributes } from "react";
import { cn } from "../../../lib/cn";

export function Squircle({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("squircle", className)} {...props} />;
}
