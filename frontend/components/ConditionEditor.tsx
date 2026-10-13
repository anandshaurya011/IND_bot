"use client";

import { KNOWN_INDICATORS, buildCompareToSpec, buildIndicatorParams } from "@/lib/indicators";
import type { Condition } from "@/lib/types";

const COMPARISONS: { value: Condition["comparison"]; label: string }[] = [
  { value: "above", label: "Above" },
  { value: "below", label: "Below" },
  { value: "crosses_above", label: "Crosses above" },
  { value: "crosses_below", label: "Crosses below" },
  { value: "not_equal", label: "Not equal (above or below)" },
];

function indicatorInfo(value: string) {
  return KNOWN_INDICATORS.find((i) => i.value === value);
}

/** Parses a compare_to spec string ("ema:200" or "price" or "close") back into {indicator, length}. */
function parseCompareTo(spec: string): { indicator: string; length: number | undefined } {
  if (spec === "price") return { indicator: "price", length: undefined };
  const [indicator, lengthStr] = spec.split(":");
  return { indicator, length: lengthStr ? Number(lengthStr) : undefined };
}

export function ConditionEditor({
  condition,
  onChange,
  onRemove,
  canRemove,
}: {
  condition: Condition;
  onChange: (next: Condition) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  const leftInfo = indicatorInfo(condition.indicator);
  const leftParamKey = condition.indicator === "vwap_rolling" ? "days" : "length";
  const leftLength = typeof condition.params[leftParamKey] === "number" ? condition.params[leftParamKey] : undefined;

  const compareTo = parseCompareTo(condition.compare_to);
  const isPrice = compareTo.indicator === "price";
  const rightInfo = indicatorInfo(compareTo.indicator);

  function setLeftIndicator(indicator: string) {
    const info = indicatorInfo(indicator);
    const params = info?.needsLength ? buildIndicatorParams(indicator, leftLength ?? 20) : {};
    onChange({ ...condition, indicator, params });
  }

  function setLeftLength(length: number) {
    onChange({ ...condition, params: buildIndicatorParams(condition.indicator, length) });
  }

  function setComparison(comparison: Condition["comparison"]) {
    onChange({ ...condition, comparison });
  }

  function setCompareToPrice() {
    onChange({ ...condition, compare_to: buildCompareToSpec("price", undefined) });
  }

  function setCompareToIndicator(indicator: string) {
    const info = indicatorInfo(indicator);
    const length = info?.needsLength ? 20 : undefined;
    onChange({ ...condition, compare_to: buildCompareToSpec(indicator, length) });
  }

  function setCompareToLength(length: number) {
    onChange({ ...condition, compare_to: buildCompareToSpec(compareTo.indicator, length) });
  }

  return (
    <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
      <label>
        Indicator
        <select value={condition.indicator} onChange={(e) => setLeftIndicator(e.target.value)}>
          {KNOWN_INDICATORS.map((i) => (
            <option key={i.value} value={i.value}>
              {i.label}
            </option>
          ))}
        </select>
      </label>
      {leftInfo?.needsLength && (
        <label>
          Length
          <input
            type="number"
            min={1}
            value={leftLength ?? ""}
            onChange={(e) => setLeftLength(Number(e.target.value))}
          />
        </label>
      )}
      <label>
        Comparison
        <select value={condition.comparison} onChange={(e) => setComparison(e.target.value as Condition["comparison"])}>
          {COMPARISONS.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Compare to
        <select value={isPrice ? "price" : "indicator"} onChange={(e) => (e.target.value === "price" ? setCompareToPrice() : setCompareToIndicator("ema"))}>
          <option value="price">Price</option>
          <option value="indicator">Another indicator</option>
        </select>
      </label>
      {!isPrice && (
        <>
          <label>
            vs. indicator
            <select value={compareTo.indicator} onChange={(e) => setCompareToIndicator(e.target.value)}>
              {KNOWN_INDICATORS.map((i) => (
                <option key={i.value} value={i.value}>
                  {i.label}
                </option>
              ))}
            </select>
          </label>
          {rightInfo?.needsLength && (
            <label>
              Length
              <input
                type="number"
                min={1}
                value={compareTo.length ?? ""}
                onChange={(e) => setCompareToLength(Number(e.target.value))}
              />
            </label>
          )}
        </>
      )}
      {canRemove && (
        <button type="button" className="btn ghost sm" onClick={onRemove}>
          Remove
        </button>
      )}
    </div>
  );
}
