import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "../../../lib/cn";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn("glass glow-focus h-10 w-full rounded-full px-4 text-sm text-text outline-none placeholder:text-text-faint", className)} {...props} />;
});
