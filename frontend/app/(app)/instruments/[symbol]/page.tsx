"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { PriceChart } from "@/components/PriceChart";
import { Tag } from "@/components/Ui";
import { fmtIST, fmtPrice } from "@/lib/format";
import { CHART_OVERLAY_INDICATORS } from "@/lib/indicators";
import type { InstrumentCandlesResponse } from "@/lib/types";

const LOOKBACK_OPTIONS = [
  { value: 30, label: "1 month" },
  { value: 90, label: "3 months" },
  { value: 180, label: "6 months" },
  { value: 365, label: "1 year" },
  { value: 730, label: "2 years" },
];

interface OverlayPick {
  indicator: string;
  length: number | undefined;
}

function overlaySpecsParam(picks: OverlayPick[]): string {
  return picks
    .map((p) => (p.length !== undefined ? `${p.indicator}:${p.length}` : p.indicator))
    .join(",");
}

export default function InstrumentDetailPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = params.symbol;

  const [lookbackDays, setLookbackDays] = useState(180);
  const [overlayPicks, setOverlayPicks] = useState<OverlayPick[]>([]);
  const [newIndicator, setNewIndicator] = useState(CHART_OVERLAY_INDICATORS[0].value);
  const [newLength, setNewLength] = useState(20);
  const [showDataTable, setShowDataTable] = useState(false);

  const specsParam = overlaySpecsParam(overlayPicks);

  const { data, isLoading, error } = useQuery({
    queryKey: ["instrumentCandles", symbol, lookbackDays, specsParam],
    queryFn: () =>
      api<InstrumentCandlesResponse>(
        "GET",
        `/instruments/${symbol}/candles?lookback_days=${lookbackDays}${specsParam ? `&indicators=${encodeURIComponent(specsParam)}` : ""}`,
      ),
    retry: false,
  });

  const isNotFound = error instanceof ApiError && error.status === 404;
  const isProviderError = error instanceof ApiError && error.status === 502;
  const isBadIndicator = error instanceof ApiError && error.status === 400;

  const latest = data?.candles[data.candles.length - 1] ?? null;

  const newIndicatorInfo = useMemo(
    () => CHART_OVERLAY_INDICATORS.find((i) => i.value === newIndicator),
    [newIndicator],
  );

  function addOverlay() {
    if (overlayPicks.some((p) => p.indicator === newIndicator && p.length === (newIndicatorInfo?.needsLength ? newLength : undefined))) {
      return; // already added, nothing to do
    }
    setOverlayPicks((prev) => [
      ...prev,
      { indicator: newIndicator, length: newIndicatorInfo?.needsLength ? newLength : undefined },
    ]);
  }

  function removeOverlay(index: number) {
    setOverlayPicks((prev) => prev.filter((_, i) => i !== index));
  }

  // Rows shown most-recent-first, for "crawl and check" browsing.
  const tableRows = useMemo(() => (data ? [...data.candles].reverse() : []), [data]);

  return (
    <section>
      <h2>{symbol}</h2>

      <div className="row" style={{ gap: "1rem", marginBottom: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
        <label>
          Period
          <select value={lookbackDays} onChange={(e) => setLookbackDays(Number(e.target.value))}>
            {LOOKBACK_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Add indicator
          <select value={newIndicator} onChange={(e) => setNewIndicator(e.target.value)}>
            {CHART_OVERLAY_INDICATORS.map((i) => (
              <option key={i.value} value={i.value}>
                {i.label}
              </option>
            ))}
          </select>
        </label>
        {newIndicatorInfo?.needsLength && (
          <label>
            Length
            <input type="number" min={1} value={newLength} onChange={(e) => setNewLength(Number(e.target.value))} style={{ width: "70px" }} />
          </label>
        )}
        <button type="button" className="btn ghost sm" onClick={addOverlay}>
          Add overlay
        </button>

        {overlayPicks.length > 0 && (
          <div className="row" style={{ gap: "0.4rem" }}>
            {overlayPicks.map((p, i) => (
              <span key={`${p.indicator}:${p.length}:${i}`} className="tag d">
                {p.indicator}
                {p.length !== undefined ? `(${p.length})` : ""}{" "}
                <button type="button" onClick={() => removeOverlay(i)} aria-label={`remove ${p.indicator} overlay`} style={{ background: "none", border: 0, color: "inherit", cursor: "pointer", padding: 0, marginLeft: "4px" }}>
                  &times;
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {isLoading && <p>Loading...</p>}
      {isNotFound && <p>Unknown instrument {symbol}.</p>}
      {isProviderError && <p>Could not fetch live data for {symbol} right now. {error?.message}</p>}
      {isBadIndicator && <p>{error?.message}</p>}
      {error && !isNotFound && !isProviderError && !isBadIndicator && <p>Failed to load chart data.</p>}

      {data && (
        <>
          <div className="row" style={{ gap: "1rem", marginBottom: "0.75rem", alignItems: "baseline" }}>
            <span>{data.instrument.name}</span>
            <Tag text={data.instrument.kind} cls={data.instrument.kind === "index" ? "w" : "d"} />
            <span className="muted">via {data.provider}</span>
            {latest && (
              <span>
                Latest: <b>{fmtPrice(latest.close)}</b> <span className="muted">({fmtIST(latest.ts, { hour: undefined, minute: undefined })})</span>
              </span>
            )}
          </div>
          <PriceChart candles={data.candles} overlays={data.overlays} />
          {overlayPicks.length === 0 && data.overlays.length === 0 && (
            <p className="muted" style={{ marginTop: "0.5rem" }}>
              No indicator overlay yet — pick one above, or this instrument hasn&apos;t matched a strategy for you before.
            </p>
          )}

          <div style={{ marginTop: "1rem" }}>
            <button type="button" className="btn ghost sm" onClick={() => setShowDataTable((v) => !v)}>
              {showDataTable ? "Hide" : "Show"} raw time series data ({data.candles.length} candles)
            </button>
          </div>

          {showDataTable && (
            <div className="tablewrap" style={{ marginTop: "0.5rem", maxHeight: "420px", overflowY: "auto" }}>
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Open</th>
                    <th>High</th>
                    <th>Low</th>
                    <th>Close</th>
                    <th>Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((c) => (
                    <tr key={c.ts}>
                      <td>{fmtIST(c.ts, { hour: undefined, minute: undefined })}</td>
                      <td>{fmtPrice(c.open)}</td>
                      <td>{fmtPrice(c.high)}</td>
                      <td>{fmtPrice(c.low)}</td>
                      <td>{fmtPrice(c.close)}</td>
                      <td>{c.volume.toLocaleString("en-IN")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
