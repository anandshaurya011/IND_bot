"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Tag } from "@/components/Ui";
import { fmtIST } from "@/lib/format";
import type { ScanRun } from "@/lib/types";

function statusTag(status: string) {
  if (status === "success" || status === "done" || status === "completed") {
    return <Tag text={status} cls="g" />;
  }
  if (status === "error") return <Tag text={status} cls="r" />;
  if (status === "running" || status === "pending") return <Tag text={status} cls="w" />;
  return <Tag text={status} cls="d" />;
}

export default function StrategyScansPage() {
  const params = useParams<{ id: string }>();
  const strategyId = params.id;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["scans", strategyId],
    queryFn: () => api<ScanRun[]>("GET", `/scans?strategy_id=${strategyId}&limit=50`),
  });

  return (
    <section>
      <h2>Scan history</h2>
      {isLoading && <p>Loading...</p>}
      {isError && <p>Failed to load scan history.</p>}
      {data && data.length === 0 && <p>No scans yet for this strategy.</p>}
      {data && data.length > 0 && (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Started</th>
                <th>Finished</th>
                <th>Status</th>
                <th>Instruments Scanned</th>
                <th>Matches</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.map((run) => (
                <tr key={run.id}>
                  <td>{fmtIST(run.started_at)}</td>
                  <td>{run.finished_at !== null ? fmtIST(run.finished_at) : "—"}</td>
                  <td>
                    {statusTag(run.status)}
                    {run.status === "error" && run.error && (
                      <div style={{ color: "var(--red)", fontSize: "0.85em" }}>{run.error}</div>
                    )}
                  </td>
                  <td>{run.instruments_scanned}</td>
                  <td>{run.matches_count}</td>
                  <td>
                    <Link href={`/scans/${run.id}`} className="btn ghost sm">
                      View results
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
