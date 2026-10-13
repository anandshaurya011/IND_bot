"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Condition, Instrument, StrategyIn } from "@/lib/types";
import { UniverseChips } from "@/components/UniverseChips";
import { ConditionEditor } from "@/components/ConditionEditor";

const TIMEFRAMES: { value: string; label: string; intradayCaveat?: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "5m", label: "5 minutes", intradayCaveat: "intraday" },
  { value: "15m", label: "15 minutes", intradayCaveat: "intraday" },
  { value: "1h", label: "1 hour", intradayCaveat: "intraday" },
];

const PROVIDERS = [
  { value: "yfinance", label: "yfinance" },
  { value: "nse", label: "NSE" },
];

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function emptyCondition(): Condition {
  return { indicator: "ema", params: { length: 20 }, comparison: "above", compare_to: "price" };
}

export function StrategyForm({
  initial,
  onSubmit,
}: {
  initial: StrategyIn;
  onSubmit: (strategy: StrategyIn) => Promise<void>;
}) {
  const [name, setName] = useState(initial.name);
  const [instrumentType, setInstrumentType] = useState<StrategyIn["instrument_type"]>(initial.instrument_type);
  const [universe, setUniverse] = useState<Set<string>>(new Set(initial.universe));
  const [timeframe, setTimeframe] = useState(initial.timeframe);
  const [provider, setProvider] = useState(initial.provider);
  const [conditions, setConditions] = useState<Condition[]>(
    initial.conditions.length > 0 ? initial.conditions : [emptyCondition()],
  );
  const [logic, setLogic] = useState<StrategyIn["logic"]>(initial.logic);
  const [minConsecutive, setMinConsecutive] = useState(initial.min_consecutive_sessions);
  const [scanTime, setScanTime] = useState(initial.scan_time);
  const [scanDaysMode, setScanDaysMode] = useState<"daily" | "select">(
    initial.scan_days === "daily" ? "daily" : "select",
  );
  const [selectedDays, setSelectedDays] = useState<Set<number>>(
    new Set(Array.isArray(initial.scan_days) ? initial.scan_days : []),
  );
  const [enabled, setEnabled] = useState(initial.enabled);
  const [errors, setErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const universeQuery = useQuery({
    queryKey: ["universe"],
    queryFn: () => api<Record<string, Instrument[]>>("GET", "/universe"),
  });
  const universeNames = useMemo(
    () => (universeQuery.data ? Object.keys(universeQuery.data).sort() : []),
    [universeQuery.data],
  );

  const selectedTimeframe = TIMEFRAMES.find((t) => t.value === timeframe);
  const showIntradayHint = selectedTimeframe?.intradayCaveat === "intraday" && provider !== "yfinance";

  function updateCondition(index: number, next: Condition) {
    setConditions((prev) => prev.map((c, i) => (i === index ? next : c)));
  }

  function removeCondition(index: number) {
    setConditions((prev) => prev.filter((_, i) => i !== index));
  }

  function addCondition() {
    setConditions((prev) => [...prev, emptyCondition()]);
  }

  function toggleDay(day: number) {
    setSelectedDays((prev) => {
      const next = new Set(prev);
      if (next.has(day)) next.delete(day);
      else next.add(day);
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrors([]);
    setSubmitting(true);
    const strategy: StrategyIn = {
      name,
      instrument_type: instrumentType,
      universe: Array.from(universe),
      timeframe,
      conditions,
      logic,
      min_consecutive_sessions: minConsecutive,
      provider,
      enabled,
      scan_time: scanTime,
      scan_days: scanDaysMode === "daily" ? "daily" : Array.from(selectedDays).sort(),
    };
    try {
      await onSubmit(strategy);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.message.split("; "));
      } else {
        setErrors(["Something went wrong. Please try again."]);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      {errors.length > 0 && (
        <div className="card err">
          <ul>
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>

      <label>
        Instrument type
        <select
          value={instrumentType}
          onChange={(e) => setInstrumentType(e.target.value as StrategyIn["instrument_type"])}
        >
          <option value="stock">Stock</option>
          <option value="index">Index</option>
          <option value="both">Both</option>
        </select>
      </label>

      <div>
        <p>Universe</p>
        {universeQuery.isLoading && <p>Loading universes...</p>}
        {universeQuery.isError && <p>Failed to load universes.</p>}
        {universeNames.length > 0 && (
          <UniverseChips universeNames={universeNames} selected={universe} onChange={setUniverse} />
        )}
      </div>

      <label>
        Timeframe
        <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
          {TIMEFRAMES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      {showIntradayHint && (
        <p className="hint">
          Heads up: intraday timeframes may not be supported by the selected provider. The server will
          reject this combination if it&apos;s invalid.
        </p>
      )}

      <label>
        Provider
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {PROVIDERS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
      </label>

      <div>
        <p>Conditions</p>
        {conditions.map((c, i) => (
          <ConditionEditor
            key={i}
            condition={c}
            onChange={(next) => updateCondition(i, next)}
            onRemove={() => removeCondition(i)}
            canRemove={conditions.length > 1}
          />
        ))}
        <button type="button" className="btn ghost sm" onClick={addCondition}>
          Add condition
        </button>
        {conditions.length >= 2 && (
          <label>
            Combine with
            <select value={logic} onChange={(e) => setLogic(e.target.value as StrategyIn["logic"])}>
              <option value="AND">AND</option>
              <option value="OR">OR</option>
            </select>
          </label>
        )}
      </div>

      <label>
        Minimum consecutive sessions
        <input
          type="number"
          min={1}
          value={minConsecutive}
          onChange={(e) => setMinConsecutive(Number(e.target.value))}
        />
      </label>

      <label>
        Scan time
        <input type="time" value={scanTime} onChange={(e) => setScanTime(e.target.value)} />
      </label>

      <div>
        <p>Scan days</p>
        <label>
          <input
            type="radio"
            checked={scanDaysMode === "daily"}
            onChange={() => setScanDaysMode("daily")}
          />
          Every day
        </label>
        <label>
          <input
            type="radio"
            checked={scanDaysMode === "select"}
            onChange={() => setScanDaysMode("select")}
          />
          Select days
        </label>
        {scanDaysMode === "select" && (
          <div className="row" style={{ gap: "0.5rem" }}>
            {DAY_LABELS.map((label, day) => (
              <label key={day}>
                <input
                  type="checkbox"
                  checked={selectedDays.has(day)}
                  onChange={() => toggleDay(day)}
                />
                {label}
              </label>
            ))}
          </div>
        )}
      </div>

      <label>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        Enabled
      </label>

      <div>
        <button type="submit" className="btn" disabled={submitting}>
          {submitting ? "Saving..." : "Save strategy"}
        </button>
      </div>
    </form>
  );
}
