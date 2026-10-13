export function fmtPrice(n: number | null): string {
  if (n === null) return "—";
  return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtIST(value: number | string, opts?: Intl.DateTimeFormatOptions): string {
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  const defaultOpts: Intl.DateTimeFormatOptions = {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  };
  return new Intl.DateTimeFormat("en-IN", { ...defaultOpts, ...opts }).format(date);
}
