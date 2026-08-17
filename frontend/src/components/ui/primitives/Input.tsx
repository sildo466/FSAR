import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "../../../lib/cn";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn("glow-focus h-10 w-full rounded-full border border-[var(--input-border)] bg-[var(--input-bg)] px-4 text-sm text-[var(--input-text)] outline-none backdrop-blur-[22px] placeholder:text-text-faint", className)} {...props} />;
});
