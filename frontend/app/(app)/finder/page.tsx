"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Instrument, WatchlistEntry } from "@/lib/types";
import { Tag } from "@/components/Ui";
import { UniverseChips } from "@/components/UniverseChips";

type KindFilter = "all" | "stock" | "index";

export default function FinderPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [selectedUniverses, setSelectedUniverses] = useState<Set<string>>(new Set());

  const universeQuery = useQuery({
    queryKey: ["universe"],
    queryFn: () => api<Record<string, Instrument[]>>("GET", "/universe"),
  });

  const watchlistQuery = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api<WatchlistEntry[]>("GET", "/watchlist"),
  });

  const universeNames = useMemo(() => {
    return universeQuery.data ? Object.keys(universeQuery.data).sort() : [];
  }, [universeQuery.data]);

  // Default to all universes selected once the data arrives.
  useEffect(() => {
    if (universeNames.length > 0 && selectedUniverses.size === 0) {
      setSelectedUniverses(new Set(universeNames));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [universeNames]);

  const watchlistSymbols = useMemo(() => {
    const set = new Set<string>();
    if (watchlistQuery.data) {
      for (const entry of watchlistQuery.data) {
        set.add(entry.symbol);
      }
    }
    return set;
  }, [watchlistQuery.data]);

  const filteredInstruments = useMemo(() => {
    if (!universeQuery.data) return [];
    const bySymbol = new Map<string, Instrument>();
    for (const name of selectedUniverses) {
      const list = universeQuery.data[name] ?? [];
      for (const inst of list) {
        bySymbol.set(inst.symbol, inst);
      }
    }
    let all = Array.from(bySymbol.values());
    if (kindFilter !== "all") {
      all = all.filter((inst) => inst.kind === kindFilter);
    }

    // Deeper search: split the query into whitespace-separated tokens and
    // require every token to match SOMEWHERE in "symbol + name" - this lets
    // "hdfc bank" or "tata motors" match across the combined text rather
    // than requiring the whole phrase to appear verbatim in one field.
    const tokens = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const filtered = tokens.length
      ? all.filter((inst) => {
          const haystack = `${inst.symbol} ${inst.name}`.toLowerCase();
          return tokens.every((t) => haystack.includes(t));
        })
      : all;
    return filtered.sort((a, b) => a.symbol.localeCompare(b.symbol));
  }, [universeQuery.data, selectedUniverses, search, kindFilter]);

  const addMutation = useMutation({
    mutationFn: (symbol: string) => api("POST", "/watchlist", { symbol }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const isLoading = universeQuery.isLoading || watchlistQuery.isLoading;
  const isError = universeQuery.isError || watchlistQuery.isError;

  return (
    <>
      <section>
        <h2>Stock & Index Finder</h2>
        {universeQuery.data && (
          <UniverseChips
            universeNames={universeNames}
            selected={selectedUniverses}
            onChange={setSelectedUniverses}
          />
        )}
      </section>

      <section>
        <div className="row">
          <label>
            Search
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search symbol or name (e.g. &quot;hdfc bank&quot;)"
            />
          </label>
          <label>
            Kind
            <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value as KindFilter)}>
              <option value="all">All</option>
              <option value="stock">Stocks</option>
              <option value="index">Indices</option>
            </select>
          </label>
        </div>
        {isLoading && <p>Loading...</p>}
        {isError && <p>Failed to load instruments.</p>}
        {!isLoading && !isError && filteredInstruments.length === 0 && <p>No instruments found.</p>}
        {!isLoading && !isError && filteredInstruments.length > 0 && (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name</th>
                  <th>Kind</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredInstruments.map((inst) => {
                  const added = watchlistSymbols.has(inst.symbol);
                  return (
                    <tr key={inst.symbol}>
                      <td style={{ textAlign: "left" }}>
                        <Link href={`/instruments/${inst.symbol}`}>{inst.symbol}</Link>
                      </td>
                      <td style={{ textAlign: "left" }}>{inst.name}</td>
                      <td>
                        <Tag text={inst.kind} cls={inst.kind === "stock" ? "g" : "w"} />
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn ghost sm"
                          disabled={added || addMutation.isPending}
                          onClick={() => addMutation.mutate(inst.symbol)}
                        >
                          {added ? "Added ✓" : "Add to watchlist"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
