"use client";
import Link from "next/link";
import { usePlace } from "@/lib/usePlace";

export default function AppFooter() {
  const { placeId } = usePlace();
  return <footer className="app-footer">
    <div className="footer-identity"><strong>Outlook SD<span>San Diego, California</span></strong><p>A local perspective. A little more foresight.</p></div>
    <div className="footer-details"><p>Built by San Diego students for the 2026 Congressional App Challenge. Not a government website.</p>
      <p>Forecasts are not official advisories. Follow official alerts and posted signs.</p>
      <Link href={`/data/?place=${placeId ?? "downtown"}`}>Sources &amp; methods ↗</Link></div>
  </footer>;
}
