"use client";

import { useMemo } from "react";
import type { Candle, IndicatorOverlay } from "@/lib/types";
import { fmtIST } from "@/lib/format";

const WIDTH = 760;
const HEIGHT = 280;
const PADDING = { top: 12, right: 12, bottom: 24, left: 56 };

// Distinct colors for up to this many simultaneous overlay lines, cycling
// if there are more. Index 0 reuses --warn to match the single-overlay
// legacy behavior's color.
const OVERLAY_COLORS = ["var(--warn)", "var(--green)", "var(--red)", "#9b8cf2", "#2dd4bf", "#f472b6"];

function buildPath(points: { x: number; y: number }[]): string {
  if (points.length === 0) return "";
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

function overlayLabel(o: IndicatorOverlay): string {
  const lengthPart = o.params.length ? `(${o.params.length})` : "";
  const sourcePart = o.strategy_name ? ` — from "${o.strategy_name}"` : "";
  return `${o.indicator}${lengthPart}${sourcePart}`;
}

/**
 * A minimal, dependency-free line chart: close price plus any number of
 * indicator overlay lines, all scaled to the same price axis. Not a full
 * candlestick chart (no OHLC wicks) - a reasonable MVP scope that avoids
 * pulling in a charting library.
 */
export function PriceChart({
  candles,
  overlays,
}: {
  candles: Candle[];
  overlays: IndicatorOverlay[];
}) {
  const chart = useMemo(() => {
    if (candles.length === 0) return null;

    const overlayMaps = overlays.map((o) => {
      const byTs = new Map<number, number>();
      for (const v of o.values) {
        if (v.value !== null) byTs.set(v.ts, v.value);
      }
      return byTs;
    });

    const closes = candles.map((c) => c.close);
    const overlayVals = overlayMaps.flatMap((m) => Array.from(m.values()));
    const allVals = [...closes, ...overlayVals];
    const minV = Math.min(...allVals);
    const maxV = Math.max(...allVals);
    const span = maxV - minV || 1;

    const innerWidth = WIDTH - PADDING.left - PADDING.right;
    const innerHeight = HEIGHT - PADDING.top - PADDING.bottom;

    function xFor(i: number): number {
      return PADDING.left + (candles.length <= 1 ? 0 : (i / (candles.length - 1)) * innerWidth);
    }
    function yFor(value: number): number {
      return PADDING.top + innerHeight - ((value - minV) / span) * innerHeight;
    }

    const pricePoints = candles.map((c, i) => ({ x: xFor(i), y: yFor(c.close) }));
    const overlayLines = overlayMaps.map((byTs) =>
      candles
        .map((c, i) => (byTs.has(c.ts) ? { x: xFor(i), y: yFor(byTs.get(c.ts)!) } : null))
        .filter((p): p is { x: number; y: number } => p !== null),
    );

    const yTicks = [minV, minV + span / 2, maxV];
    const xTickIdx = [0, Math.floor((candles.length - 1) / 2), candles.length - 1];

    return { pricePoints, overlayLines, yTicks, xTickIdx, xFor, yFor };
  }, [candles, overlays]);

  if (!chart) return <p className="muted">No candle data.</p>;

  return (
    <div>
      <svg width={WIDTH} height={HEIGHT} role="img" aria-label="Price chart">
        {chart.yTicks.map((v) => (
          <g key={v}>
            <line
              x1={PADDING.left}
              x2={WIDTH - PADDING.right}
              y1={chart.yFor(v)}
              y2={chart.yFor(v)}
              stroke="var(--line)"
              strokeWidth={1}
            />
            <text x={4} y={chart.yFor(v) + 4} fontSize={10} fill="var(--dim)">
              {v.toFixed(1)}
            </text>
          </g>
        ))}
        <path d={buildPath(chart.pricePoints)} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
        {chart.overlayLines.map((points, i) =>
          points.length > 0 ? (
            <path
              key={overlays[i].indicator + i}
              d={buildPath(points)}
              fill="none"
              stroke={OVERLAY_COLORS[i % OVERLAY_COLORS.length]}
              strokeWidth={1.5}
              strokeDasharray="4 3"
            />
          ) : null,
        )}
        {chart.xTickIdx.map((i) => (
          <text key={i} x={chart.xFor(i)} y={HEIGHT - 6} fontSize={10} fill="var(--dim)" textAnchor="middle">
            {fmtIST(candles[i].ts, { month: "short", day: "numeric", hour: undefined, minute: undefined, year: undefined })}
          </text>
        ))}
      </svg>
      <div className="row" style={{ gap: "1rem", fontSize: "12px", marginTop: "4px", flexWrap: "wrap" }}>
        <span>
          <span style={{ color: "var(--accent)" }}>&#9644;</span> Close price
        </span>
        {overlays.map((o, i) => (
          <span key={o.indicator + i}>
            <span style={{ color: OVERLAY_COLORS[i % OVERLAY_COLORS.length] }}>&#9644;</span> {overlayLabel(o)}
          </span>
        ))}
      </div>
    </div>
  );
}
