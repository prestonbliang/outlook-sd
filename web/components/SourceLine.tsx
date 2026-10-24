import { updatedText } from "@/lib/api";

export default function SourceLine({ sources, updated, stale }: { sources: string[]; updated?: string | null; stale?: string[] }) {
  return (
    <p className="small muted" style={{ margin: "8px 0 0" }}>
      Data: {sources.join(", ")}. {updated ? `${updatedText(updated)}.` : ""}
      {stale && stale.length > 0 && <> Not current: {stale.join(", ")}.</>}
    </p>
  );
}
