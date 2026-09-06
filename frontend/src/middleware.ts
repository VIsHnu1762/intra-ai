/**
 * Intra AI — Next.js Edge Middleware Route Guards & RBAC
 *
 * Inspects authentication cookies and enforces role-based access control:
 * - /admin/*: requires authenticated session with role "admin" | "recruiter"
 * - /portal/*: requires authenticated candidate session
 * - /login, /signup: redirects authenticated users to their corresponding home dashboard
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AUTH_COOKIE = "intra_auth_token";
const ROLE_COOKIE = "intra_user_role";

function getSessionInfo(
  token: string | undefined,
  roleCookie: string | undefined
): { authenticated: boolean; role: string | null } {
  if (!token) return { authenticated: false, role: null };
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return { authenticated: false, role: null };
    const payload = JSON.parse(
      Buffer.from(parts[1], "base64").toString("utf-8")
    );
    if (payload.exp) {
      const now = Math.floor(Date.now() / 1000);
      if (payload.exp <= now) return { authenticated: false, role: null };
    }
    const resolvedRole = roleCookie || payload.role || null;
    return { authenticated: true, role: resolvedRole };
  } catch {
    return { authenticated: false, role: null };
  }
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const tokenCookie = request.cookies.get(AUTH_COOKIE)?.value;
  const roleCookie = request.cookies.get(ROLE_COOKIE)?.value;

  const { authenticated, role } = getSessionInfo(tokenCookie, roleCookie);
  const isHr = role === "admin" || role === "recruiter";

  // 1. Guard /admin/* routes
  if (pathname.startsWith("/admin")) {
    if (!authenticated) {
      const loginUrl = new URL("/login", request.url);
      loginUrl.searchParams.set("from", pathname + search);
      return NextResponse.redirect(loginUrl);
    }

    // Role check: non-HR candidates attempting to access admin route -> redirect to candidate portal
    if (!isHr) {
      return NextResponse.redirect(new URL("/portal", request.url));
    }

    return NextResponse.next();
  }

  // 2. Guard /portal/* routes (Candidate Portal)
  if (pathname.startsWith("/portal")) {
    if (!authenticated) {
      const loginUrl = new URL("/login", request.url);
      loginUrl.searchParams.set("from", pathname + search);
      return NextResponse.redirect(loginUrl);
    }

    // Role check: HR recruiters/admins attempting to access candidate portal -> redirect to HR dashboard
    if (isHr) {
      return NextResponse.redirect(new URL("/admin/dashboard", request.url));
    }

    return NextResponse.next();
  }

  // 3. Prevent authenticated users from accessing /login or /signup
  if (pathname === "/login" || pathname === "/signup") {
    if (authenticated) {
      if (isHr) {
        return NextResponse.redirect(new URL("/admin/dashboard", request.url));
      }
      return NextResponse.redirect(new URL("/portal", request.url));
    }
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico, sitemap.xml, robots.txt
     * - public interview assets
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
