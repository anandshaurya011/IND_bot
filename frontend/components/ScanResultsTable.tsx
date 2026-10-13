"use client";

import { useMemo, useState } from "react";
import { Tag } from "@/components/Ui";
import { fmtPrice } from "@/lib/format";
import type { ScanResultRow } from "@/lib/types";

function parseIndicatorValues(json: string): string {
  try {
    const parsed = JSON.parse(json);
    if (parsed && typeof parsed === "object") {
      const entries = Object.entries(parsed as Record<string, unknown>);
      if (entries.length === 0) return "—";
      return entries.map(([k, v]) => `${k}: ${v}`).join(", ");
    }
    return String(parsed);
  } catch {
    return "—";
  }
}

export function ScanResultsTable({ results }: { results: ScanResultRow[] }) {
  const [matchesOnly, setMatchesOnly] = useState(false);

  const sorted = useMemo(() => {
    return [...results].sort((a, b) => Number(b.satisfied) - Number(a.satisfied));
  }, [results]);

  const visible = matchesOnly ? sorted.filter((r) => r.satisfied) : sorted;

  return (
    <div>
      <div className="row" style={{ gap: "0.5rem", marginBottom: "0.5rem" }}>
        <button
          type="button"
          className={`btn ghost sm${!matchesOnly ? " on" : ""}`}
          onClick={() => setMatchesOnly(false)}
        >
          Show all
        </button>
        <button
          type="button"
          className={`btn ghost sm${matchesOnly ? " on" : ""}`}
          onClick={() => setMatchesOnly(true)}
        >
          Matches only
        </button>
      </div>
      {visible.length === 0 && <p>No results.</p>}
      {visible.length > 0 && (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Kind</th>
                <th>Satisfied</th>
                <th>Consecutive Sessions</th>
                <th>Latest Price</th>
                <th>Last Candle Date</th>
                <th>Indicator Values</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.symbol}>
                  <td style={{ textAlign: "left" }}>{r.symbol}</td>
                  <td>{r.kind}</td>
                  <td>
                    {r.satisfied ? <Tag text="Match" cls="g" /> : <Tag text="No match" cls="d" />}
                  </td>
                  <td>{r.consecutive_sessions}</td>
                  <td>
                    {fmtPrice(r.latest_price)}
                    {r.latest_price === null && (
                      <>
                        {" "}
                        <Tag text="data unavailable" cls="w" />
                      </>
                    )}
                  </td>
                  <td>{r.last_candle_date ?? "—"}</td>
                  <td style={{ textAlign: "left" }}>{parseIndicatorValues(r.indicator_values_json)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
