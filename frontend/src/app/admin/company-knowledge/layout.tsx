import Link from "next/link";
import type { ReactNode } from "react";

export default function CompanyKnowledgeLayout({ children }: { children: ReactNode }) {
  return <><nav className="flex flex-wrap gap-4 border-b px-4 py-3 text-sm sm:px-8" aria-label="Company knowledge"><Link className="underline underline-offset-4" href="/admin/company-knowledge">Documents and versions</Link><Link className="underline underline-offset-4" href="/admin/company-knowledge/ask">Grounded policy answers</Link></nav>{children}</>;
}
