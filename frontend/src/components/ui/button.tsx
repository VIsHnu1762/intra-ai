"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 font-semibold rounded-full transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 select-none",
  {
    variants: {
      variant: {
        default:
          "bg-brand text-text-inverse hover:bg-brand-hover active:bg-brand-hover shadow-sm",
        secondary:
          "bg-transparent border border-brand text-brand hover:bg-brand-light active:bg-brand-light",
        ghost:
          "bg-transparent text-text-muted hover:bg-border hover:text-text-primary",
        danger:
          "bg-error text-text-inverse hover:bg-red-800 active:bg-red-900 shadow-sm",
        alex:
          "bg-agent-alex-primary text-gray-950 hover:bg-agent-alex-hover active:opacity-90 shadow-md shadow-cyan-500/25",
        jordan:
          "bg-agent-jordan-primary text-white hover:bg-agent-jordan-hover active:opacity-90 shadow-md shadow-purple-500/25",
        obsidian:
          "bg-obsidian-800 border border-obsidian-border text-obsidian-text hover:bg-obsidian-750 hover:border-obsidian-border-subtle",
        media:
          "bg-white/10 hover:bg-white/20 text-white border border-white/15 backdrop-blur-md active:scale-95",
        mediaActive:
          "bg-error hover:bg-error/90 text-white border border-error/50 shadow-lg shadow-red-500/25 active:scale-95",
      },
      size: {
        sm: "h-8 px-4 text-xs",
        default: "h-10 px-5 text-sm",
        lg: "h-12 px-7 text-base",
        icon: "h-10 w-10 p-0 rounded-full",
        iconLg: "h-12 w-12 p-0 rounded-full",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      asChild = false,
      loading = false,
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    const Comp = asChild ? Slot : "button";

    return (
      <Comp
        ref={ref}
        disabled={disabled || loading}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      >
        {asChild ? (
          children
        ) : (
          <>
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {children}
          </>
        )}
      </Comp>
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
