import Link from "next/link";
import { Logo } from "@/components/ui/logo";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-bg flex flex-col items-center justify-center px-4 py-12">
      {/* Logo */}
      <Link href="/" className="flex items-center mb-8">
        <Logo size="lg" withText />
      </Link>

      {/* Card slot */}
      <div className="w-full max-w-md">{children}</div>

      {/* Footer */}
      <p className="mt-8 text-xs text-text-muted text-center">
        &copy; {new Date().getFullYear()} Intra AI. All rights reserved.
      </p>
    </div>
  );
}
