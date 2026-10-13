"use client";

import { useMemo, useRef, useState } from "react";
import type { Candle, IndicatorOverlay } from "@/lib/types";
import { fmtIST, fmtPrice } from "@/lib/format";

const WIDTH = 920;
const HEIGHT = 420;
const PADDING = { top: 16, right: 16, bottom: 28, left: 64 };

// Distinct colors for up to this many simultaneous overlay lines, cycling
// if there are more. Index 0 reuses --warn to match the single-overlay
// legacy behavior's color.
const OVERLAY_COLORS = ["var(--warn)", "var(--green)", "var(--red)", "#9b8cf2", "#2dd4bf", "#f472b6"];

function buildPath(points: { x: number; y: number }[]): string {
  if (points.length === 0) return "";
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

function overlayLabel(o: IndicatorOverlay): string {
  const lengthPart = o.params.length ? `(${o.params.length})` : o.params.days ? `(${o.params.days})` : "";
  const sourcePart = o.strategy_name ? ` — from "${o.strategy_name}"` : "";
  return `${o.indicator}${lengthPart}${sourcePart}`;
}

/**
 * A minimal, dependency-free line chart: close price plus any number of
 * indicator overlay lines, all scaled to the same price axis, with a
 * TradingView-style hover crosshair + tooltip (date, OHLC, volume, and
 * every overlay's value at the hovered candle). Not a full candlestick
 * chart (no OHLC wicks) - a reasonable MVP scope that avoids pulling in a
 * charting library.
 */
export function PriceChart({
  candles,
  overlays,
}: {
  candles: Candle[];
  overlays: IndicatorOverlay[];
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

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
    function idxForX(x: number): number {
      if (candles.length <= 1) return 0;
      const frac = (x - PADDING.left) / innerWidth;
      const idx = Math.round(frac * (candles.length - 1));
      return Math.min(candles.length - 1, Math.max(0, idx));
    }

    const pricePoints = candles.map((c, i) => ({ x: xFor(i), y: yFor(c.close) }));
    const overlayLines = overlayMaps.map((byTs) =>
      candles
        .map((c, i) => (byTs.has(c.ts) ? { x: xFor(i), y: yFor(byTs.get(c.ts)!) } : null))
        .filter((p): p is { x: number; y: number } => p !== null),
    );

    const yTicks = [minV, minV + span / 2, maxV];
    const xTickIdx = [0, Math.floor((candles.length - 1) / 2), candles.length - 1];

    return { pricePoints, overlayLines, overlayMaps, yTicks, xTickIdx, xFor, yFor, idxForX, innerHeight };
  }, [candles, overlays]);

  if (!chart) return <p className="muted">No candle data.</p>;

  function handleMove(e: React.MouseEvent<SVGSVGElement>) {
    const svg = svgRef.current;
    if (!svg || !chart) return;
    const rect = svg.getBoundingClientRect();
    const scaleX = WIDTH / rect.width;
    const x = (e.clientX - rect.left) * scaleX;
    setHoverIdx(chart.idxForX(x));
  }

  const hoverCandle = hoverIdx !== null ? candles[hoverIdx] : null;
  const hoverX = hoverIdx !== null ? chart.xFor(hoverIdx) : null;

  return (
    <div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        style={{ width: "100%", height: "auto", maxWidth: `${WIDTH}px`, display: "block", cursor: "crosshair" }}
        role="img"
        aria-label="Price chart"
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIdx(null)}
      >
        {chart.yTicks.map((v, i) => (
          <g key={i}>
            <line
              x1={PADDING.left}
              x2={WIDTH - PADDING.right}
              y1={chart.yFor(v)}
              y2={chart.yFor(v)}
              stroke="var(--line)"
              strokeWidth={1}
            />
            <text x={4} y={chart.yFor(v) + 4} fontSize={11} fill="var(--dim)">
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
        {chart.xTickIdx.map((i, tickIdx) => (
          <text key={tickIdx} x={chart.xFor(i)} y={HEIGHT - 8} fontSize={11} fill="var(--dim)" textAnchor="middle">
            {fmtIST(candles[i].ts, { month: "short", day: "numeric", hour: undefined, minute: undefined, year: undefined })}
          </text>
        ))}

        {/* Hover crosshair + markers + tooltip - all drawn last so they sit on top. */}
        {hoverCandle && hoverX !== null && (
          <g>
            <line
              x1={hoverX}
              x2={hoverX}
              y1={PADDING.top}
              y2={PADDING.top + chart.innerHeight}
              stroke="var(--dim)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <circle cx={hoverX} cy={chart.yFor(hoverCandle.close)} r={3.5} fill="var(--accent)" />
            {overlays.map((o, i) => {
              const v = chart.overlayMaps[i].get(hoverCandle.ts);
              return v !== undefined ? (
                <circle key={o.indicator + i} cx={hoverX} cy={chart.yFor(v)} r={3.5} fill={OVERLAY_COLORS[i % OVERLAY_COLORS.length]} />
              ) : null;
            })}
            <HoverTooltip x={hoverX} candle={hoverCandle} overlays={overlays} overlayMaps={chart.overlayMaps} />
          </g>
        )}
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

function HoverTooltip({
  x,
  candle,
  overlays,
  overlayMaps,
}: {
  x: number;
  candle: Candle;
  overlays: IndicatorOverlay[];
  overlayMaps: Map<number, number>[];
}) {
  const lines: string[] = [
    fmtIST(candle.ts, { hour: undefined, minute: undefined }),
    `O ${fmtPrice(candle.open)}  H ${fmtPrice(candle.high)}  L ${fmtPrice(candle.low)}  C ${fmtPrice(candle.close)}`,
    `Vol ${candle.volume.toLocaleString("en-IN")}`,
  ];
  overlays.forEach((o, i) => {
    const v = overlayMaps[i].get(candle.ts);
    if (v !== undefined) lines.push(`${o.indicator}: ${fmtPrice(v)}`);
  });

  const boxWidth = 190;
  const boxHeight = 16 + lines.length * 14;
  // Flip to the left side of the crosshair when too close to the right edge.
  const boxX = x + boxWidth + 16 > WIDTH ? x - boxWidth - 10 : x + 10;
  const boxY = PADDING.top;

  return (
    <g>
      <rect x={boxX} y={boxY} width={boxWidth} height={boxHeight} rx={6} fill="var(--panel)" stroke="var(--line)" />
      {lines.map((line, i) => (
        <text key={i} x={boxX + 10} y={boxY + 18 + i * 14} fontSize={11} fill="var(--text)">
          {line}
        </text>
      ))}
    </g>
  );
}
