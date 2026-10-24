import { Day, LEVEL_WORD, TileName, dayName, levelColor } from "@/lib/api";

/** Three 14 px squares in level colors with 3-letter day names; the word is in the aria-label and title. */
export default function DayStrip({ tile, days }: { tile: TileName; days: Day[] }) {
  if (!days.length) return null;
  return (
    <div style={{ display: "flex", gap: 8 }} role="list" aria-label="Next three days">
      {days.slice(0, 3).map((d) => {
        const word = d.level ? LEVEL_WORD[d.level] : "Not rated";
        return (
          <div key={d.date} role="listitem" aria-label={`${dayName(d.date, "long")}: ${word}`} title={`${dayName(d.date, "long")}: ${word}`}
               style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 28 }}>
            <span aria-hidden style={{ width: 14, height: 14, background: levelColor(tile, d.level), border: "1px solid var(--rule)" }} />
            <span aria-hidden className="small muted">{dayName(d.date)}</span>
          </div>
        );
      })}
    </div>
  );
}
