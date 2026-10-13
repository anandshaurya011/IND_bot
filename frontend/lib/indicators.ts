// Mirrors backend/scanner/engine.py's _INDICATOR_FUNCS dispatch table.
export const KNOWN_INDICATORS: { value: string; label: string; needsLength: boolean }[] = [
  { value: "close", label: "Close price", needsLength: false },
  { value: "ema", label: "EMA", needsLength: true },
  { value: "sma", label: "SMA", needsLength: true },
  { value: "rsi", label: "RSI", needsLength: true },
  { value: "macd", label: "MACD", needsLength: false },
  { value: "bollinger", label: "Bollinger Bands", needsLength: true },
  { value: "supertrend", label: "Supertrend", needsLength: true },
  { value: "adx", label: "ADX", needsLength: true },
  { value: "vwap_session", label: "VWAP (session)", needsLength: false },
  { value: "vwap_rolling", label: "VWAP (rolling)", needsLength: false },
];

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
