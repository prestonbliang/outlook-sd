import { Day, LEVEL_WORD, TileName, dayName, levelColor } from "@/lib/api";
import { localDate } from "@/lib/forecast";

/** Three 14 px squares in level colors with 3-letter day names; the word is in the aria-label and title. */
export default function DayStrip({ tile, days }: { tile: TileName; days: Day[] }) {
  const upcoming = days.filter(day => day.date >= localDate()).slice(0, 3);
  if (!upcoming.length) return null;
  return (
    <div className="day-strip" role="list" aria-label="Next three days">
      {upcoming.map((d) => {
        const word = d.level ? LEVEL_WORD[d.level] : "Not rated";
        return (
          <div key={d.date} role="listitem" aria-label={`${dayName(d.date, "long")}: ${word}`} title={`${dayName(d.date, "long")}: ${word}`}
               className="day-strip-item">
            <span aria-hidden className="day-strip-swatch" style={{ background: levelColor(tile, d.level) }} />
            <span aria-hidden className="small muted">{dayName(d.date)}</span>
          </div>
        );
      })}
    </div>
  );
}
