"use client";

import * as React from "react";
import * as AvatarPrimitive from "@radix-ui/react-avatar";
import { cva, type VariantProps } from "class-variance-authority";
import { cn, getInitials } from "@/lib/utils";

const avatarVariants = cva(
  "relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full transition-all duration-300",
  {
    variants: {
      size: {
        sm: "h-8 w-8 text-xs",
        default: "h-10 w-10 text-sm",
        lg: "h-14 w-14 text-lg",
        xl: "h-20 w-20 text-2xl",
        "2xl": "h-28 w-28 text-3xl",
      },
      agent: {
        none: "bg-brand-light",
        alex: "bg-gradient-to-br from-cyan-900 to-sky-950 border-2 border-agent-alex-primary text-agent-alex-primary",
        jordan: "bg-gradient-to-br from-purple-900 to-violet-950 border-2 border-agent-jordan-primary text-agent-jordan-primary",
      },
    },
    defaultVariants: {
      size: "default",
      agent: "none",
    },
  }
);

export interface AvatarProps
  extends React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Root>,
    VariantProps<typeof avatarVariants> {
  src?: string;
  alt?: string;
  name?: string;
  isSpeaking?: boolean;
}

const Avatar = React.forwardRef<
  React.ElementRef<typeof AvatarPrimitive.Root>,
  AvatarProps
>(({ className, size, agent, src, alt, name, isSpeaking = false, ...props }, ref) => (
  <div className="relative inline-flex items-center justify-center">
    {isSpeaking && (
      <span
        className={cn(
          "absolute -inset-1.5 rounded-full animate-ping opacity-40 pointer-events-none",
          agent === "alex"
            ? "bg-cyan-500"
            : agent === "jordan"
            ? "bg-purple-500"
            : "bg-brand"
        )}
      />
    )}
    <AvatarPrimitive.Root
      ref={ref}
      className={cn(
        avatarVariants({ size, agent }),
        isSpeaking && (agent === "alex" ? "glow-alex" : agent === "jordan" ? "glow-jordan" : "ring-4 ring-brand/30"),
        className
      )}
      {...props}
    >
      {src && (
        <AvatarPrimitive.Image
          src={src}
          alt={alt ?? name ?? "Avatar"}
          className="h-full w-full object-cover"
        />
      )}
      <AvatarPrimitive.Fallback
        className={cn(
          "flex h-full w-full items-center justify-center font-semibold",
          agent === "alex"
            ? "text-cyan-300 font-bold"
            : agent === "jordan"
            ? "text-purple-300 font-bold"
            : "text-brand"
        )}
        delayMs={src ? 300 : 0}
      >
        {name ? getInitials(name) : "?"}
      </AvatarPrimitive.Fallback>
    </AvatarPrimitive.Root>
  </div>
));

Avatar.displayName = "Avatar";

export { Avatar };
