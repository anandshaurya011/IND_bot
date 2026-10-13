import { Tag } from "@/components/Ui";

const CLS: Record<"pre_market" | "open" | "closed", string> = {
  pre_market: "w",
  open: "g",
  closed: "d",
};

function label(status: "pre_market" | "open" | "closed"): string {
  return status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function MarketStatusBadge({ status }: { status: "pre_market" | "open" | "closed" }) {
  return <Tag text={label(status)} cls={CLS[status]} />;
}
