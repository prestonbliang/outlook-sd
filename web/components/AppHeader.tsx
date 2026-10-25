"use client";
import Link from "next/link";
import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { usePlace } from "@/lib/usePlace";
import Icon, { type IconName } from "./Icon";

const LINKS = [["/", "Today"], ["/map/", "Map"], ["/what-if/", "What if"], ["/track-record/", "Track record"], ["/data/", "Data"]];
const NAV_ICONS: IconName[] = ["compass", "map", "water", "chart", "data"];
export default function AppHeader() {
  const pathname = usePathname();
  const { placeId, place } = usePlace();
  useEffect(() => {
    const page = LINKS.find(([href]) => pathname === href || pathname === href.slice(0, -1))?.[1]
      ?? (pathname?.startsWith("/hazard/") ? "Hazard forecast" : "Neighborhood outlook");
    document.title = `${page}${place ? ` · ${place.name}` : ""} | Outlook SD`;
  }, [pathname, place?.name]);
  return <header className="app-header">
    <Link className="brand" href={`/?place=${placeId ?? "downtown"}`}>
      <svg aria-hidden="true" width="36" height="36" viewBox="0 0 36 36" fill="none"><rect width="36" height="36" rx="11" fill="currentColor" />
        <path d="M6 23c4-6 8 6 12 0s8 6 12 0M6 28c4-6 8 6 12 0s8 6 12 0" stroke="white" strokeWidth="2" />
        <circle cx="23" cy="12" r="5" fill="var(--sand)" /></svg>
      <span>Outlook <strong>SD</strong><small>A clearer view of San Diego</small></span>
    </Link>
    <nav aria-label="Primary navigation">{LINKS.map(([href, title], index) => <Link key={href}
      href={`${href}?place=${placeId ?? "downtown"}`} aria-current={pathname === href || pathname === href.slice(0, -1) ? "page" : undefined}><Icon name={NAV_ICONS[index]} size={17} /><span>{title}</span></Link>)}</nav>
  </header>;
}
