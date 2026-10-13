"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Strategy, StrategyIn } from "@/lib/types";
import { StrategyForm } from "@/components/StrategyForm";

export default function EditStrategyPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params.id;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["strategies"],
    queryFn: () => api<Strategy[]>("GET", "/strategies"),
  });

  const strategy = data?.find((s) => s.id === id);

  async function handleSubmit(updated: StrategyIn) {
    await api<Strategy>("PUT", `/strategies/${id}`, updated);
    router.push("/strategies");
  }

  if (isLoading) return <p>Loading...</p>;
  if (isError) return <p>Failed to load strategy.</p>;
  if (!strategy) return <p>Strategy not found.</p>;

  return (
    <section>
      <h2>Edit strategy</h2>
      <StrategyForm initial={strategy} onSubmit={handleSubmit} />
    </section>
  );
}
