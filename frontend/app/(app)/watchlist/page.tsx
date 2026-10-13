"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtIST } from "@/lib/format";
import type { Instrument, WatchlistEntry } from "@/lib/types";
import { Tag } from "@/components/Ui";
import { AddToWatchlistInput } from "@/components/AddToWatchlistInput";

interface Row {
  symbol: string;
  name: string;
  kind: "stock" | "index" | "unknown";
  added_at: number;
}

type SortKey = "symbol" | "name" | "kind" | "added_at";

export default function WatchlistPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("added_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const watchlistQuery = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api<WatchlistEntry[]>("GET", "/watchlist"),
  });

  const universeQuery = useQuery({
    queryKey: ["universe"],
    queryFn: () => api<Record<string, Instrument[]>>("GET", "/universe"),
  });

  const removeMutation = useMutation({
    mutationFn: (symbol: string) => api("DELETE", `/watchlist/${symbol}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const instrumentsBySymbol = useMemo(() => {
    const map = new Map<string, Instrument>();
    if (universeQuery.data) {
      for (const list of Object.values(universeQuery.data)) {
        for (const inst of list) {
          map.set(inst.symbol, inst);
        }
      }
    }
    return map;
  }, [universeQuery.data]);

  const rows: Row[] = useMemo(() => {
    if (!watchlistQuery.data) return [];
    return watchlistQuery.data.map((entry) => {
      const inst = instrumentsBySymbol.get(entry.symbol);
      return {
        symbol: entry.symbol,
        name: inst ? inst.name : entry.symbol,
        kind: inst ? inst.kind : "unknown",
        added_at: entry.added_at,
      };
    });
  }, [watchlistQuery.data, instrumentsBySymbol]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = q
      ? rows.filter((r) => r.symbol.toLowerCase().includes(q) || r.name.toLowerCase().includes(q))
      : rows;
    const sorted = [...filtered].sort((a, b) => {
      let cmp = 0;
      if (a[sortKey] < b[sortKey]) cmp = -1;
      else if (a[sortKey] > b[sortKey]) cmp = 1;
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [rows, search, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function sortIndicator(key: SortKey) {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? " ▲" : " ▼";
  }

  const isLoading = watchlistQuery.isLoading || universeQuery.isLoading;
  const isError = watchlistQuery.isError || universeQuery.isError;

  return (
    <>
      <section>
        <h2>Add to watchlist</h2>
        <AddToWatchlistInput />
      </section>

      <section>
        <h2>Watchlist</h2>
        <div className="row">
          <label>
            Search
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search symbol or name"
            />
          </label>
        </div>
        {isLoading && <p>Loading...</p>}
        {isError && <p>Failed to load watchlist.</p>}
        {!isLoading && !isError && rows.length === 0 && <p>No symbols in your watchlist yet.</p>}
        {!isLoading && !isError && rows.length > 0 && (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th onClick={() => toggleSort("symbol")} style={{ cursor: "pointer" }}>
                    Symbol{sortIndicator("symbol")}
                  </th>
                  <th onClick={() => toggleSort("name")} style={{ cursor: "pointer" }}>
                    Name{sortIndicator("name")}
                  </th>
                  <th onClick={() => toggleSort("kind")} style={{ cursor: "pointer" }}>
                    Kind{sortIndicator("kind")}
                  </th>
                  <th onClick={() => toggleSort("added_at")} style={{ cursor: "pointer" }}>
                    Added{sortIndicator("added_at")}
                  </th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => (
                  <tr key={row.symbol}>
                    <td style={{ textAlign: "left" }}>
                      <Link href={`/instruments/${row.symbol}`}>{row.symbol}</Link>
                    </td>
                    <td style={{ textAlign: "left" }}>{row.name}</td>
                    <td>
                      <Tag
                        text={row.kind}
                        cls={row.kind === "stock" ? "g" : row.kind === "index" ? "w" : "d"}
                      />
                    </td>
                    <td>{fmtIST(row.added_at)}</td>
                    <td>
                      <button
                        type="button"
                        className="btn ghost sm"
                        disabled={removeMutation.isPending}
                        onClick={() => removeMutation.mutate(row.symbol)}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
