"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Tag } from "@/components/Ui";
import { api } from "@/lib/api";
import { fmtPrice } from "@/lib/format";
import type { ScanResultRow, WatchlistEntry } from "@/lib/types";

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
  const queryClient = useQueryClient();

  const watchlistQuery = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api<WatchlistEntry[]>("GET", "/watchlist"),
  });
  const watchlistSymbols = useMemo(() => {
    const set = new Set<string>();
    for (const entry of watchlistQuery.data ?? []) set.add(entry.symbol);
    return set;
  }, [watchlistQuery.data]);

  const addMutation = useMutation({
    mutationFn: (symbol: string) => api("POST", "/watchlist", { symbol }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  });

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
                <th>Watchlist</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => {
                const added = watchlistSymbols.has(r.symbol);
                return (
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
                  <td>
                    <button
                      type="button"
                      className="btn ghost sm"
                      disabled={added || addMutation.isPending}
                      onClick={() => addMutation.mutate(r.symbol)}
                    >
                      {added ? "Added ✓" : "Add"}
                    </button>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
