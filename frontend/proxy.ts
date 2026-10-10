import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Optimistic auth gate: no session cookie on a protected page → /login?next=<path>.
 * Real authorization happens in the API; pages also re-check the role via /api/auth/me.
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has("ht_session")) return NextResponse.next();
  const url = request.nextUrl.clone();
  const next = request.nextUrl.pathname + request.nextUrl.search;
  url.pathname = "/login";
  url.search = `?next=${encodeURIComponent(next)}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/app/:path*", "/doctor/:path*", "/admin/:path*", "/onboarding/:path*", "/share/:path*"],
};
