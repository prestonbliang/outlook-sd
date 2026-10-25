import type { Metadata, Viewport } from "next";
import "./globals.css";
import AppHeader from "@/components/AppHeader";

export const metadata: Metadata = {
  title: "Outlook SD",
  description: "Today and the next three days: neighborhood forecasts for beach water, air, heat, coastal flooding and fire in San Diego County, with community observations.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body><a className="skip-link" href="#main-content">Skip to main content</a><AppHeader />
        <div id="main-content" tabIndex={-1}>{children}</div>
        <footer className="app-footer"><strong>Outlook SD</strong><span>Built by San Diego students for the 2026 Congressional App Challenge. Not a government website.</span>
          <span>Forecasts are not official advisories. Follow official alerts and posted signs.</span></footer>
      </body>
    </html>
  );
}
