"use client";

import { useMemo } from "react";
import type { Candle, IndicatorOverlay } from "@/lib/types";
import { fmtIST } from "@/lib/format";

const WIDTH = 760;
const HEIGHT = 260;
const PADDING = { top: 12, right: 12, bottom: 24, left: 56 };

function buildPath(
  points: { x: number; y: number }[],
): string {
  if (points.length === 0) return "";
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

/**
 * A minimal, dependency-free line chart: close price plus an optional
 * indicator overlay line, both scaled to the same price axis. Not a full
 * candlestick chart (no OHLC wicks) - a reasonable MVP scope that avoids
 * pulling in a charting library for one line + one overlay line.
 */
export function PriceChart({
  candles,
  overlay,
}: {
  candles: Candle[];
  overlay: IndicatorOverlay | null;
}) {
  const chart = useMemo(() => {
    if (candles.length === 0) return null;

    const overlayByTs = new Map<number, number>();
    if (overlay) {
      for (const v of overlay.values) {
        if (v.value !== null) overlayByTs.set(v.ts, v.value);
      }
    }

    const closes = candles.map((c) => c.close);
    const overlayVals = Array.from(overlayByTs.values());
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
    const overlayPoints = overlay
      ? candles
          .map((c, i) => (overlayByTs.has(c.ts) ? { x: xFor(i), y: yFor(overlayByTs.get(c.ts)!) } : null))
          .filter((p): p is { x: number; y: number } => p !== null)
      : [];

    const yTicks = [minV, minV + span / 2, maxV];
    const xTickIdx = [0, Math.floor((candles.length - 1) / 2), candles.length - 1];

    return { pricePoints, overlayPoints, yTicks, xTickIdx, xFor, yFor };
  }, [candles, overlay]);

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
        {overlay && chart.overlayPoints.length > 0 && (
          <path d={buildPath(chart.overlayPoints)} fill="none" stroke="var(--warn)" strokeWidth={1.5} strokeDasharray="4 3" />
        )}
        {chart.xTickIdx.map((i) => (
          <text key={i} x={chart.xFor(i)} y={HEIGHT - 6} fontSize={10} fill="var(--dim)" textAnchor="middle">
            {fmtIST(candles[i].ts, { month: "short", day: "numeric", hour: undefined, minute: undefined, year: undefined })}
          </text>
        ))}
      </svg>
      <div className="row" style={{ gap: "1rem", fontSize: "12px", marginTop: "4px" }}>
        <span>
          <span style={{ color: "var(--accent)" }}>&#9644;</span> Close price
        </span>
        {overlay && (
          <span>
            <span style={{ color: "var(--warn)" }}>&#9644;</span> {overlay.indicator}
            {overlay.params.length ? `(${overlay.params.length})` : ""} — from &quot;{overlay.strategy_name}&quot;
          </span>
        )}
      </div>
    </div>
  );
}
