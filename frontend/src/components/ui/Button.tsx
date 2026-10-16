import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-emerald-300 disabled:cursor-not-allowed disabled:opacity-45",
        {
          "bg-emerald-400 text-slate-950 hover:bg-emerald-300": variant === "primary",
          "border border-slate-600 bg-slate-800 text-slate-100 hover:bg-slate-700": variant === "secondary",
          "bg-rose-500 text-white hover:bg-rose-400": variant === "danger",
          "text-slate-300 hover:bg-slate-800": variant === "ghost",
        },
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
