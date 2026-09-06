import * as React from "react";
import Image from "next/image";
import { cn } from "@/lib/utils";

export interface LogoProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: "xs" | "sm" | "default" | "lg" | "xl";
  withText?: boolean;
  textClassName?: string;
  priority?: boolean;
}

const SIZE_MAP = {
  xs: { px: 20, class: "h-5 w-5" },
  sm: { px: 28, class: "h-7 w-7" },
  default: { px: 32, class: "h-8 w-8" },
  lg: { px: 40, class: "h-10 w-10" },
  xl: { px: 48, class: "h-12 w-12" },
};

const TEXT_SIZE_MAP = {
  xs: "text-xs font-semibold",
  sm: "text-sm font-semibold",
  default: "text-[15px] font-bold",
  lg: "text-lg font-bold",
  xl: "text-xl font-bold",
};

export function Logo({
  size = "default",
  withText = false,
  textClassName,
  className,
  priority = false,
  ...props
}: LogoProps) {
  const currentSize = SIZE_MAP[size];

  return (
    <div className={cn("inline-flex items-center gap-2.5", className)} {...props}>
      <div
        className={cn(
          "relative overflow-hidden rounded-lg shrink-0 shadow-xs",
          currentSize.class
        )}
      >
        <Image
          src="/logo.png"
          alt="Intra AI Logo"
          width={currentSize.px * 2}
          height={currentSize.px * 2}
          className="h-full w-full object-cover"
          priority={priority}
        />
      </div>
      {withText && (
        <span
          className={cn(
            "tracking-tight text-text-primary",
            TEXT_SIZE_MAP[size],
            textClassName
          )}
        >
          Intra AI
        </span>
      )}
    </div>
  );
}
