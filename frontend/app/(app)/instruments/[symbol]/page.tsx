"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { PriceChart } from "@/components/PriceChart";
import { Tag } from "@/components/Ui";
import { fmtIST, fmtPrice } from "@/lib/format";
import type { InstrumentCandlesResponse } from "@/lib/types";

export default function InstrumentDetailPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = params.symbol;

  const { data, isLoading, error } = useQuery({
    queryKey: ["instrumentCandles", symbol],
    queryFn: () => api<InstrumentCandlesResponse>("GET", `/instruments/${symbol}/candles`),
    retry: false,
  });

  const isNotFound = error instanceof ApiError && error.status === 404;
  const isProviderError = error instanceof ApiError && error.status === 502;

  const latest = data?.candles[data.candles.length - 1] ?? null;

  return (
    <section>
      <h2>{symbol}</h2>
      {isLoading && <p>Loading...</p>}
      {isNotFound && <p>Unknown instrument {symbol}.</p>}
      {isProviderError && <p>Could not fetch live data for {symbol} right now. {error?.message}</p>}
      {error && !isNotFound && !isProviderError && <p>Failed to load chart data.</p>}
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
          <PriceChart candles={data.candles} overlay={data.overlay} />
          {!data.overlay && (
            <p className="muted" style={{ marginTop: "0.5rem" }}>
              No indicator overlay yet — this instrument hasn&apos;t matched a strategy for you before.
            </p>
          )}
        </>
      )}
    </section>
  );
}
