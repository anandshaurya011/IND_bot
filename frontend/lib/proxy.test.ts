import { describe, expect, it } from "vitest";
import { buildBackendUrl } from "./proxy";

describe("buildBackendUrl", () => {
  it("builds a simple path", () => {
    expect(buildBackendUrl(["strategies", "abc123"], "", "http://127.0.0.1:8000"))
      .toBe("http://127.0.0.1:8000/strategies/abc123");
  });
  it("preserves the query string", () => {
    expect(buildBackendUrl(["scans"], "?strategy_id=abc&limit=10", "http://127.0.0.1:8000"))
      .toBe("http://127.0.0.1:8000/scans?strategy_id=abc&limit=10");
  });
  it("rejects a .. segment", () => {
    expect(() => buildBackendUrl(["..", "etc"], "", "http://127.0.0.1:8000")).toThrow();
  });
  it("rejects a segment containing a slash", () => {
    expect(() => buildBackendUrl(["a%2Fb"], "", "http://127.0.0.1:8000")).toThrow();
  });
});
