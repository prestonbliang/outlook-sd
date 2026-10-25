import { LEVEL_WORD, TileName, levelColor } from "@/lib/api";

/** Color swatch plus the level word — never color alone. */
export default function LevelBadge({ tile, level }: { tile: TileName; level: string | null }) {
  return (
    <span className="level-badge">
      <span aria-hidden className="level-swatch" style={{ background: levelColor(tile, level) }} />
      <span>{level ? LEVEL_WORD[level] : "Not rated"}</span>
    </span>
  );
}
