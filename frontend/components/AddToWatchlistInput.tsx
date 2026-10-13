"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";

export function AddToWatchlistInput() {
  const [symbol, setSymbol] = useState("");
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => api("POST", "/watchlist", { symbol }),
    onSuccess: () => {
      setSymbol("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : "Failed to add symbol.");
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!symbol.trim()) return;
    mutation.mutate();
  }

  return (
    <form className="row" onSubmit={handleSubmit}>
      <label>
        Symbol
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="e.g. RELIANCE"
        />
      </label>
      <button type="submit" className="btn" disabled={mutation.isPending || !symbol.trim()}>
        Add
      </button>
      {error && <span className="r">{error}</span>}
    </form>
  );
}
