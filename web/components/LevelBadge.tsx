import { LEVEL_WORD, TileName, levelColor } from "@/lib/api";

/** Color swatch plus the level word — never color alone. */
export default function LevelBadge({ tile, level }: { tile: TileName; level: string | null }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span aria-hidden style={{ width: 12, height: 12, background: levelColor(tile, level), border: "1px solid var(--rule)" }} />
      <span>{level ? LEVEL_WORD[level] : "Not rated"}</span>
    </span>
  );
}
