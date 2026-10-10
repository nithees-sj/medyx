import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Providers } from "@/components/providers";

import "./globals.css";

const sans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "HealthThread", template: "%s · HealthThread" },
  description: "One patient, one record, every hospital.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f6e6e",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <Providers>
          <div className="flex flex-1 flex-col">{children}</div>
          <footer className="border-t bg-card/60 px-4 py-3 text-center text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-warning/40 bg-warning-soft px-2.5 py-0.5 font-medium text-foreground/80">
              Demo — synthetic data only
            </span>
            <span className="ml-2 hidden sm:inline">
              Decision support only. HealthThread never tells patients to change their medicines.
            </span>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
