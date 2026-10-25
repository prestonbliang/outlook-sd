import { OdorRecord } from "@/lib/api";
import { dateLabel } from "@/lib/forecast";

/** South Bay only: the APCD odor-complaint record. A record, not a forecast (weather did not beat recent reports). */
export default function OdorCard({ odor, place }: { odor: OdorRecord; place: string }) {
  return <aside className="odor-card" aria-labelledby="odor-title">
    <h2 id="odor-title">Sewage smell reports</h2>
    {odor.here ? <p><strong>{odor.here}</strong> odor complaint{odor.here === 1 ? "" : "s"} from {place} ({odor.south_bay} across South Bay) in the {odor.days} days
      through {dateLabel(odor.through)}{odor.last_here ? `; the latest on ${dateLabel(odor.last_here)}` : ""}.</p> :
      <p><strong>{odor.south_bay}</strong> odor complaint{odor.south_bay === 1 ? "" : "s"} across South Bay in the {odor.days} days through {dateLabel(odor.through)}, none from {place}.</p>}
    <p className="small muted">From the San Diego Air Pollution Control District complaint log. This is a record, not a forecast:
      we tested whether weather could predict smell days, and it did no better than recent complaints. <a href={odor.url}>APCD complaint data</a></p>
  </aside>;
}
