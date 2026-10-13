import { describe, expect, it } from "vitest";
import { fmtPrice, fmtIST } from "./format";

describe("fmtPrice", () => {
  it("formats a number", () => { expect(fmtPrice(1234.5)).toBe("1,234.50"); });
  it("renders null as an em dash, never a blank or zero", () => { expect(fmtPrice(null)).toBe("—"); });
});

describe("fmtIST", () => {
  it("renders an epoch-seconds timestamp in Asia/Kolkata", () => {
    // 2026-01-15T09:00:00+05:30 == 1768447800 epoch seconds
    expect(fmtIST(1768447800)).toContain("09:00");
  });
});
