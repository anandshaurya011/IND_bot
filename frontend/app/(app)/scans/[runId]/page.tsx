"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { ScanResultsTable } from "@/components/ScanResultsTable";
import type { ScanResultRow } from "@/lib/types";

export default function ScanResultsPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;

  const { data, isLoading, error } = useQuery({
    queryKey: ["scanResults", runId],
    queryFn: () => api<ScanResultRow[]>("GET", `/scans/${runId}/results`),
    retry: false,
  });

  const isNotFound = error instanceof ApiError && error.status === 404;

  return (
    <section>
      <h2>Scan results</h2>
      {isLoading && <p>Loading...</p>}
      {isNotFound && <p>This scan run was not found or isn&apos;t yours.</p>}
      {error && !isNotFound && <p>Failed to load scan results.</p>}
      {data && <ScanResultsTable results={data} />}
    </section>
  );
}
