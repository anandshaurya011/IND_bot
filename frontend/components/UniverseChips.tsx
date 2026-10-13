"use client";

import { Chip } from "@/components/Ui";

const LABELS: Record<string, string> = {
  nifty50: "Nifty 50",
  banknifty: "Bank Nifty",
  niftyit: "Nifty IT",
  indices: "Indices",
  all_stocks: "All Stocks",
};

function labelFor(name: string): string {
  return LABELS[name] ?? name;
}

export function UniverseChips({
  universeNames,
  selected,
  onChange,
}: {
  universeNames: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}) {
  const allSelected = universeNames.length > 0 && universeNames.every((n) => selected.has(n));

  function toggleAll() {
    if (allSelected) {
      onChange(new Set());
    } else {
      onChange(new Set(universeNames));
    }
  }

  function toggle(name: string) {
    const next = new Set(selected);
    if (next.has(name)) {
      next.delete(name);
    } else {
      next.add(name);
    }
    onChange(next);
  }

  return (
    <div className="row" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
      <Chip on={allSelected} onClick={toggleAll}>
        All
      </Chip>
      {universeNames.map((name) => (
        <Chip key={name} on={selected.has(name)} onClick={() => toggle(name)}>
          {labelFor(name)}
        </Chip>
      ))}
    </div>
  );
}
