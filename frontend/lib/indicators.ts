// Mirrors backend/scanner/engine.py's _INDICATOR_FUNCS dispatch table.
export const KNOWN_INDICATORS: { value: string; label: string; needsLength: boolean }[] = [
  { value: "close", label: "Close price", needsLength: false },
  { value: "ema", label: "EMA", needsLength: true },
  { value: "sma", label: "SMA", needsLength: true },
  { value: "vwma", label: "VWMA", needsLength: true },
  { value: "rsi", label: "RSI", needsLength: true },
  { value: "macd", label: "MACD", needsLength: false },
  { value: "bollinger", label: "Bollinger Bands", needsLength: true },
  { value: "supertrend", label: "Supertrend", needsLength: true },
  { value: "adx", label: "ADX", needsLength: true },
  { value: "vwap_session", label: "VWAP (session)", needsLength: false },
  { value: "vwap_rolling", label: "VWAP (rolling N days)", needsLength: true },
];

// Indicators meaningful to overlay on a price chart (excludes the pseudo-
// indicator "close", which is identical to the price line already shown).
export const CHART_OVERLAY_INDICATORS = KNOWN_INDICATORS.filter((i) => i.value !== "close");

/**
 * Builds the backend's compare_to spec string, matching the parsing
 * convention in backend/scanner/engine.py's _parse_spec: a bare name like
 * "ema" has no params, "name:length" like "ema:200" passes length=<int>.
 * The literal "price" (raw instrument price, not an indicator) passes
 * through unchanged.
 */
export function buildCompareToSpec(indicator: string, length: number | undefined): string {
  if (indicator === "price") return "price";
  if (length !== undefined && length !== null) return `${indicator}:${length}`;
  return indicator;
}

// calc.vwap_rolling's lookback kwarg is named `days`, not `length` like every
// other parametrized indicator (mirrors backend/scanner/engine.py's
// _SPEC_PARAM_NAME) - a Condition's own `params` dict is passed straight to
// the indicator function with no spec-string remapping, so the LEFT-side
// indicator picker needs to build the right key itself.
export function buildIndicatorParams(indicator: string, length: number | undefined): Record<string, number> {
  if (length === undefined || length === null) return {};
  const paramName = indicator === "vwap_rolling" ? "days" : "length";
  return { [paramName]: length };
}
