export interface Instrument {
  symbol: string;
  name: string;
  yf_ticker: string;
  nse_symbol: string;
  kind: "stock" | "index";
}

export interface Condition {
  indicator: string;
  params: Record<string, number>;
  comparison: "above" | "below" | "crosses_above" | "crosses_below";
  compare_to: string;
}

export interface Strategy {
  id: string;
  user_id: string;
  name: string;
  universe: string[];
  instrument_type: "stock" | "index" | "both";
  timeframe: string;
  conditions: Condition[];
  logic: "AND" | "OR";
  min_consecutive_sessions: number;
  provider: string;
  enabled: boolean;
  scan_time: string;
  scan_days: "daily" | number[];
}

export type StrategyIn = Omit<Strategy, "id" | "user_id">;

export interface ScanRun {
  id: string;
  user_id: string;
  strategy_id: string;
  started_at: number;
  finished_at: number | null;
  status: string;
  instruments_scanned: number;
  matches_count: number;
  error: string | null;
}

export interface ScanResultRow {
  run_id: string;
  symbol: string;
  kind: "stock" | "index";
  satisfied: boolean;
  consecutive_sessions: number;
  latest_price: number | null;
  latest_ts: number | null;
  indicator_values_json: string;
  last_candle_date: string | null;
}

export interface DashboardStrategy {
  strategy_id: string;
  name: string;
  last_run: ScanRun | null;
  next_run_time: string | null;
}

export interface DashboardResponse {
  market_status: "pre_market" | "open" | "closed";
  strategies: DashboardStrategy[];
}

export interface Settings {
  telegram_chat_id: string | null;
  telegram_bot_token_configured: boolean;
  active_provider: string;
  updated_at: number;
}

export interface WatchlistEntry {
  symbol: string;
  added_at: number;
}
