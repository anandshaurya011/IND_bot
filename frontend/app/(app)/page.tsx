"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtIST } from "@/lib/format";
import type { DashboardResponse } from "@/lib/types";
import { MarketStatusBadge } from "@/components/MarketStatusBadge";

export default function DashboardPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardResponse>("GET", "/dashboard"),
    refetchInterval: 60_000,
  });

  return (
    <>
      <section>
        <h2>Market status</h2>
        {isLoading && <p>Loading...</p>}
        {isError && <p>Failed to load market status.</p>}
        {data && <MarketStatusBadge status={data.market_status} />}
      </section>

      <section>
        <h2>Strategies</h2>
        {isLoading && <p>Loading...</p>}
        {isError && <p>Failed to load dashboard.</p>}
        {data && data.strategies.length === 0 && (
          <p>
            No strategies yet — <Link href="/strategies/new">create one</Link>
          </p>
        )}
        {data && data.strategies.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Last run status</th>
                <th>Last run time</th>
                <th>Matches</th>
                <th>Next scheduled run</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.strategies.map((s) => (
                <tr key={s.strategy_id}>
                  <td>{s.name}</td>
                  <td>{s.last_run ? s.last_run.status : "never run"}</td>
                  <td>{s.last_run ? fmtIST(s.last_run.started_at) : "never run"}</td>
                  <td>{s.last_run ? s.last_run.matches_count : "never run"}</td>
                  <td>{s.next_run_time ? fmtIST(s.next_run_time) : "not scheduled"}</td>
                  <td>
                    {s.last_run && (
                      <Link href={`/strategies/${s.strategy_id}/scans`}>View results</Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
