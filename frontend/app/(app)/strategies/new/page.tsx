"use client";

import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Strategy, StrategyIn } from "@/lib/types";
import { StrategyForm } from "@/components/StrategyForm";

const DEFAULTS: StrategyIn = {
  name: "",
  instrument_type: "stock",
  universe: [],
  timeframe: "daily",
  conditions: [{ indicator: "ema", params: { length: 20 }, comparison: "above", compare_to: "price" }],
  logic: "AND",
  min_consecutive_sessions: 5,
  provider: "yfinance",
  enabled: true,
  scan_time: "09:00",
  scan_days: "daily",
};

export default function NewStrategyPage() {
  const router = useRouter();

  async function handleSubmit(strategy: StrategyIn) {
    await api<Strategy>("POST", "/strategies", strategy);
    router.push("/strategies");
  }

  return (
    <section>
      <h2>New strategy</h2>
      <StrategyForm initial={DEFAULTS} onSubmit={handleSubmit} />
    </section>
  );
}
