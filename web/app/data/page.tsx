"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { get, updatedText } from "@/lib/api";
import { usePlace } from "@/lib/usePlace";

type Health = { sources: Record<string, { last_success: string | null; newest_data: string | null; stale: boolean }> };

const SOURCES: { key?: string; name: string; url: string; license: string; use: string }[] = [
  { key: "ibwc", name: "IBWC gauge 11-0133.00, Tijuana River at International Boundary", url: "https://waterdata.ibwc.gov/",
    license: "U.S. government data (public domain)", use: "Water: border flow, live every 15 minutes and history" },
  { name: "HydroShare: Tijuana River discharge (IBWC gage), 2000–2021", url: "https://www.hydroshare.org/resource/d2f319994a0e4a07ac0b09dcdff4bb61/",
    license: "CC BY 4.0", use: "Water: border-flow history for training" },
  { key: "beachwatch", name: "State Water Board Beach Watch: bacteria results, stations, advisories", url: "https://data.ca.gov/dataset/beach-water-quality-postings-and-closures",
    license: "Open Data Commons Attribution (ODC-BY)", use: "Water: outcome labels (enterococcus above the state standard)" },
  { key: "cdip", name: "CDIP wave buoy 191 Point Loma South (CeNCOOS ERDDAP)", url: "https://cdip.ucsd.edu/",
    license: "Freely available; acknowledgement requested by CDIP/Scripps", use: "Water and Flood: waves and ocean temperature" },
  { key: "noaa_tides", name: "NOAA tide gauge 9410170 San Diego (CO-OPS API)", url: "https://tidesandcurrents.noaa.gov/stationhome.html?id=9410170",
    license: "U.S. government data (public domain)", use: "Flood: observed water level, tide predictions, flood thresholds" },
  { key: "openmeteo", name: "Open-Meteo: ERA5 reanalysis, forecasts, archived forecasts", url: "https://open-meteo.com/",
    license: "CC BY 4.0 (weather data by Open-Meteo.com)", use: "All tiles: weather for training and forecasts" },
  { key: "sd_fire_ems", name: "City of San Diego Fire-Rescue calls for service", url: "https://data.sandiego.gov/datasets/fire-ems-incidents/",
    license: "Open Data Commons Public Domain (ODC-PDDL)", use: "Heat: daily calls by ZIP (outcome labels)" },
  { key: "calheatscore", name: "CalHeatScore (CalEPA / OEHHA)", url: "https://calheatscore.calepa.ca.gov/",
    license: "State of California open data (no license listed)", use: "Heat: comparison, and the rating outside the City Fire-Rescue area" },
  { key: "nws", name: "National Weather Service alerts (San Diego office)", url: "https://www.weather.gov/sgx/",
    license: "U.S. government data (public domain)", use: "Flood and Fire: official warnings shown with forecasts" },
  { name: "Iowa Environmental Mesonet archive of NWS warnings", url: "https://mesonet.agron.iastate.edu/",
    license: "Freely available (Iowa State University)", use: "Baselines: past Coastal Flood and Red Flag warnings" },
  { name: "EPA AirData daily PM2.5 and ozone", url: "https://aqs.epa.gov/aqsweb/airdata/download_files.html",
    license: "U.S. government data (public domain)", use: "Air: daily AQI history for training" },
  { key: "airnow", name: "AirNow API (EPA)", url: "https://www.airnow.gov/",
    license: "U.S. government data (public domain)", use: "Air: live hourly readings" },
  { key: "calfire", name: "CAL FIRE incidents and historic fire perimeters", url: "https://www.fire.ca.gov/incidents",
    license: "State of California public information", use: "Fire: active fires; large-fire starts since 2021; fire history" },
  { name: "FPA FOD wildfire records 1992–2020, 6th ed. (USDA Forest Service)", url: "https://www.fs.usda.gov/rds/archive/catalog/RDS-2013-0009.6",
    license: "U.S. government data (public domain)", use: "Fire: large-fire starts 2014–2020 for training" },
  { key: "firms", name: "NASA FIRMS active-fire detections (VIIRS)", url: "https://firms.modaps.eosdis.nasa.gov/",
    license: "Freely available; acknowledgement requested by NASA", use: "Fire: satellite fire detections" },
  { name: "U.S. Census Bureau: ZIP (ZCTA), places, roads, water, ACS 5-year population", url: "https://www.census.gov/",
    license: "U.S. government data (public domain)", use: "Neighborhoods, ZIP outlines, shoreline; Heat levels per 10,000 residents" },
  { name: "CAL FIRE Fire Hazard Severity Zones (State Responsibility Area)", url: "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/FHSZ_in_SRA_for_FHSZ_in_LRA/FeatureServer",
    license: "State of California public information", use: "Fire: share of each 2 km area in High or Very High hazard zones" },
  { name: "City of San Diego community planning areas", url: "https://data.sandiego.gov/datasets/community-planning-district-boundaries/",
    license: "Open Data Commons Public Domain (ODC-PDDL)", use: "Named neighborhoods" },
  { key: "reports", name: "Community reports from Outlook SD users", url: "#community",
    license: "Collected by this app; published only as daily counts", use: "Shown next to forecasts and compared with them; never used to train models" },
  { name: "Protomaps basemap (OpenStreetMap data)", url: "https://protomaps.com/",
    license: "© OpenStreetMap contributors, ODbL", use: "Map background" },
];

export default function DataPage() {
  const { placeId } = usePlace();
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => { get<Health>("health.json").then(setHealth).catch(() => setHealth(null)); }, []);
  return (
    <main className="wrap">
      <p className="small"><Link href={`/?place=${placeId ?? ""}`}>← Today</Link></p>
      <h1>Data</h1>
      <p>Every forecast in Outlook SD comes from a model trained on these public datasets. The app checks the live sources every hour.</p>
      <table>
        <thead><tr><th>Source</th><th>Used for</th><th>License</th><th>Last update</th></tr></thead>
        <tbody>
          {SOURCES.map((s) => {
            const h = s.key ? health?.sources[s.key] : undefined;
            return (
              <tr key={s.name}>
                <td><a href={s.url}>{s.name}</a></td><td>{s.use}</td><td>{s.license}</td>
                <td className="small">{!s.key ? "Historical file" : !h ? "—" :
                  `${updatedText(h.last_success)}${h.newest_data ? `; data through ${h.newest_data.slice(0, 10)}` : ""}${h.stale ? " (not current)" : ""}`}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <h2 id="community" style={{ marginTop: 24 }}>Community reports</h2>
      <p>Anyone can report conditions on a hazard page or from the map. We store the neighborhood, hazard, report type, time, and a random browser code to limit repeat reports. We do not store names, emails, exact locations or free text. Only aggregate counts, reporting-browser counts, and the latest report time are published; raw reports and browser codes are not readable by public users. Reports are unverified, never change the forecasts, and are compared with them on the Track record page.</p>
      <p>The map can highlight reporting blind spots: neighborhoods with observations from fewer than three browsers for a hazard over the past 24 hours or 7 days. This is a participation goal, not a measure of safety or model confidence. A browser code does not establish a unique person. Missing reports never mean missing hazards. Observations about water appearance cannot establish bacteria levels.</p>
      <h2 style={{ marginTop: 24 }}>How AI was used</h2>
      <p>The code for this app was written with help from Claude Code (Anthropic) and Codex (OpenAI), under the direction of the student developer. The full list of what these tools were used for is in CREDITS.md in the source code.</p>
      <p>The forecasts themselves come from this project's LightGBM models trained on the data above. No chatbot generates forecasts or advice at runtime: verdicts and advice come from fixed tables.</p>
      <h2 style={{ marginTop: 24 }}>Libraries</h2>
      <p className="small">Python: pandas, NumPy, PyArrow, requests, LightGBM, scikit-learn, GeoPandas, Shapely, FastAPI. Web: Next.js, React, U.S. Web Design System (Public Sans font), MapLibre GL JS, react-map-gl, PMTiles, Protomaps basemaps, Observable Plot.</p>
    </main>
  );
}
