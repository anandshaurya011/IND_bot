"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Strategy } from "@/lib/types";

export default function StrategiesPage() {
  const queryClient = useQueryClient();
  const [runningId, setRunningId] = useState<string | null>(null);
  const [runLinks, setRunLinks] = useState<Record<string, string>>({});

  const { data, isLoading, isError } = useQuery({
    queryKey: ["strategies"],
    queryFn: () => api<Strategy[]>("GET", "/strategies"),
  });

  const toggleEnabledMutation = useMutation({
    mutationFn: (strategy: Strategy) =>
      api<Strategy>("PUT", `/strategies/${strategy.id}`, { ...strategy, enabled: !strategy.enabled }),
    onMutate: async (strategy) => {
      await queryClient.cancelQueries({ queryKey: ["strategies"] });
      const previous = queryClient.getQueryData<Strategy[]>(["strategies"]);
      queryClient.setQueryData<Strategy[]>(["strategies"], (old) =>
        old?.map((s) => (s.id === strategy.id ? { ...s, enabled: !s.enabled } : s)),
      );
      return { previous };
    },
    onError: (_err, _strategy, context) => {
      if (context?.previous) queryClient.setQueryData(["strategies"], context.previous);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api("DELETE", `/strategies/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
    },
  });

  async function handleRunNow(id: string) {
    setRunningId(id);
    try {
      const result = await api<{ run_id: string | null }>("POST", `/strategies/${id}/run-now`);
      if (result.run_id) {
        setRunLinks((prev) => ({ ...prev, [id]: result.run_id as string }));
      }
    } finally {
      setRunningId(null);
    }
  }

  function handleDelete(id: string, name: string) {
    if (window.confirm(`Delete strategy "${name}"? This cannot be undone.`)) {
      deleteMutation.mutate(id);
    }
  }

  return (
    <section>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Strategies</h2>
        <Link href="/strategies/new" className="btn">
          New strategy
        </Link>
      </div>
      {isLoading && <p>Loading...</p>}
      {isError && <p>Failed to load strategies.</p>}
      {data && data.length === 0 && <p>No strategies yet.</p>}
      {data && data.length > 0 && (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Universe</th>
                <th>Instrument type</th>
                <th>Enabled</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.id}>
                  <td style={{ textAlign: "left" }}>{s.name}</td>
                  <td style={{ textAlign: "left" }}>{s.universe.join(", ")}</td>
                  <td>{s.instrument_type}</td>
                  <td>
                    <button
                      type="button"
                      className="btn ghost sm"
                      onClick={() => toggleEnabledMutation.mutate(s)}
                    >
                      {s.enabled ? "On" : "Off"}
                    </button>
                  </td>
                  <td>
                    <div className="row" style={{ gap: "0.5rem" }}>
                      <Link href={`/strategies/${s.id}/edit`} className="btn ghost sm">
                        Edit
                      </Link>
                      <button
                        type="button"
                        className="btn ghost sm"
                        onClick={() => handleDelete(s.id, s.name)}
                        disabled={deleteMutation.isPending}
                      >
                        Delete
                      </button>
                      <button
                        type="button"
                        className="btn ghost sm"
                        onClick={() => handleRunNow(s.id)}
                        disabled={runningId === s.id}
                      >
                        {runningId === s.id ? "Running..." : "Run now"}
                      </button>
                      {runLinks[s.id] && (
                        <Link href={`/strategies/${s.id}/scans/${runLinks[s.id]}`}>View results</Link>
                      )}
                    </div>
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
