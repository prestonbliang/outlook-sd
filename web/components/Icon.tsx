export type IconName = "water" | "air" | "heat" | "flood" | "fire" | "map" | "pin" | "arrow" | "chevron" | "community" | "chart" | "data" | "clock" | "compass" | "shield";
const paths: Record<IconName, string> = {
  water: "M3 9c3-4 6 4 9 0s6 4 9 0M3 15c3-4 6 4 9 0s6 4 9 0M3 21c3-4 6 4 9 0s6 4 9 0",
  air: "M3 8h12a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h6a3 3 0 1 1-3 3",
  heat: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5",
  flood: "M4 12V7l8-5 8 5v5M9 10V7h6v3M2 15c3-4 7 4 10 0s7 4 10 0M2 20c3-4 7 4 10 0s7 4 10 0",
  fire: "M13 2c1 6-6 6-3 11 2-1 4-3 4-6 5 4 7 8 4 12-3 4-10 4-13-1C2 13 6 9 7 7c0 4 2 5 3 5-1-5 1-7 3-10Z",
  map: "m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5Zm6-2v16m6-14v16",
  pin: "M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0ZM12 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6",
  arrow: "M4 12h16m-6-6 6 6-6 6",
  chevron: "m6 9 6 6 6-6",
  community: "M21 11a9 9 0 0 1-9 9H4l-3 3V11a10 10 0 0 1 20 0ZM7 11h.01M12 11h.01M17 11h.01",
  chart: "M4 3v17h17M8 15l4-6 4 3 5-8",
  data: "M20 5c0 2-4 3-8 3S4 7 4 5s4-3 8-3 8 1 8 3ZM4 5v7c0 2 4 3 8 3s8-1 8-3V5M4 12v7c0 2 4 3 8 3s8-1 8-3v-7",
  clock: "M21 12a9 9 0 1 0-18 0 9 9 0 0 0 18 0ZM12 6v6l4 2",
  compass: "M21 12a9 9 0 1 0-18 0 9 9 0 0 0 18 0Zm-6-3-2 4-4 2 2-4 4-2Z",
  shield: "M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6l-9-4ZM8 12l3 3 5-6",
};
export default function Icon({ name, size = 20, className = "" }: { name: IconName; size?: number; className?: string }) {
  return <svg aria-hidden="true" focusable="false" className={`icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]} /></svg>;
}
