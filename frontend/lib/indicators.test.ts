import { describe, expect, it } from "vitest";
import { buildCompareToSpec, KNOWN_INDICATORS } from "./indicators";

describe("buildCompareToSpec", () => {
  it("builds an indicator:length spec", () => {
    expect(buildCompareToSpec("ema", 200)).toBe("ema:200");
  });
  it("returns the literal 'price' when comparing to raw price", () => {
    expect(buildCompareToSpec("price", undefined)).toBe("price");
  });
  it("returns the bare indicator name when no length is given", () => {
    expect(buildCompareToSpec("close", undefined)).toBe("close");
  });
});

describe("KNOWN_INDICATORS", () => {
  it("is non-empty and every entry has a value and label", () => {
    expect(KNOWN_INDICATORS.length).toBeGreaterThan(0);
    for (const i of KNOWN_INDICATORS) {
      expect(i.value).toBeTruthy();
      expect(i.label).toBeTruthy();
    }
  });
});
