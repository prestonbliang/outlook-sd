import HazardDetail from "./HazardDetail";

const TILES = ["water", "air", "heat", "flood", "fire"] as const;
export const dynamicParams = false;
export function generateStaticParams() { return TILES.map((tile) => ({ tile })); }

export default async function Page({ params }: { params: Promise<{ tile: string }> }) {
  const { tile } = await params;
  return <HazardDetail tile={tile as (typeof TILES)[number]} />;
}
