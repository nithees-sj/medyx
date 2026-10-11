"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { homeFor, useAuthConfig, useMe } from "@/lib/hooks/auth";

export function LandingCta() {
  const { data: me } = useMe();
  const { data: config } = useAuthConfig();
  if (me) {
    return (
      <Link href={homeFor(me)} className={buttonVariants({ size: "lg" })}>
        Open HealthThread <ArrowRight />
      </Link>
    );
  }
  return (
    <div className="flex flex-wrap gap-3">
      <Link href="/login" className={buttonVariants({ size: "lg" })}>
        Continue with Google <ArrowRight />
      </Link>
      {config?.demo_mode && (
        <Link href="/login" className={buttonVariants({ size: "lg", variant: "outline" })}>
          Try the demo accounts
        </Link>
      )}
    </div>
  );
}
