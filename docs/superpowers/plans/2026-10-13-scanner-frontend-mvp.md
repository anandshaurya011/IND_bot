# Stock & Index Scanner — Frontend MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js dashboard UI for the stock/index scanner — Dashboard, Watchlist, Stock & Index Finder, Strategy Builder (settings), Scan history/results, and notification Settings — talking to the already-implemented and merged FastAPI backend (`backend/main.py` on branch `scanner-backend-mvp`, now merged to `master`).

**Architecture:** Next.js 15 App Router + Clerk + Tailwind-free handwritten dark-theme CSS (matching the sibling Delta bot's `frontend/`), React Query for data fetching, and a server-side BFF proxy route (`app/api/[...path]/route.ts`) that attaches the Clerk session token as a Bearer header before forwarding to the FastAPI backend — this is copied almost verbatim from `/home/anand-shaurya/Documents/personal/delta/frontend` (read-only reference, sibling project), since that pattern is already proven and the backend here was itself modeled on Delta's backend.

**Tech Stack:** Next.js 15 (App Router), React 19, TypeScript, `@clerk/nextjs`, `@tanstack/react-query`, Vitest (unit tests for pure lib functions — this plan does not add E2E/browser testing infrastructure, matching the sibling project's test scope).

**Spec:** `docs/superpowers/specs/2026-10-13-stock-scanner-spec.md` (sections 2 "User Interface" and 3 "Advanced Strategy Builder" are this plan's primary source; section 6 names the intended stack).

**Backend API contract this plan builds against (verified by reading `backend/main.py` directly, not guessed):**
- `GET /universe` → `{ [universeName: string]: Instrument[] }` for `nifty50`/`banknifty`/`niftyit`/`indices`/`all_stocks`. `Instrument = { symbol, name, yf_ticker, nse_symbol, kind: "stock"|"index" }`.
- `GET /watchlist` → `{ symbol, added_at }[]`. `POST /watchlist { symbol }` → `{ symbol }`. `DELETE /watchlist/{symbol}` → `{ deleted }`.
- `GET /strategies` → `Strategy[]`. `POST /strategies` (body: `StrategyIn` = `Strategy` minus `id`/`user_id`) → `Strategy`, or 400 `{ detail: { errors: string[] } }`. `PUT /strategies/{id}` same body → `Strategy` or 400/404. `DELETE /strategies/{id}` → `{ deleted }` or 404.
  - `Strategy = { id, user_id, name, universe: string[], instrument_type: "stock"|"index"|"both", timeframe: string, conditions: Condition[], logic: "AND"|"OR", min_consecutive_sessions: number, provider: string, enabled: boolean, scan_time: string /* HH:MM */, scan_days: "daily" | number[] /* 0=Mon..6=Sun */ }`.
  - `Condition = { indicator: string, params: Record<string, number>, comparison: "above"|"below"|"crosses_above"|"crosses_below", compare_to: string /* "price" or "ema:200" style spec */ }`.
- `POST /strategies/{id}/run-now` → `{ run_id: string | null }`.
- `GET /scans?strategy_id=&limit=` → `ScanRun[]` (`{ id, user_id, strategy_id, started_at, finished_at, status, instruments_scanned, matches_count, error }`).
- `GET /scans/{run_id}/results` → `ScanResultRow[]` (`{ run_id, symbol, kind, satisfied, consecutive_sessions, latest_price, latest_ts, indicator_values_json, last_candle_date }`, scoped to the authenticated user's own runs, 404 otherwise).
- `GET /settings` → `{ telegram_chat_id, telegram_bot_token_configured: boolean, active_provider, updated_at }`. `PUT /settings { telegram_chat_id?, telegram_bot_token?, active_provider? }` → same shape (partial update; omitted fields keep their existing value).
- `GET /dashboard` → `{ market_status: "pre_market"|"open"|"closed", strategies: { strategy_id, name, last_run: ScanRun|null, next_run_time: string|null }[] }`.
- Every route requires `Authorization: Bearer <Clerk token>` — a 401 means "not signed in."

## Global Constraints

- All data fetched through the BFF proxy (`/api/*` → backend), never calling the FastAPI backend directly from the browser — the proxy is what attaches the Clerk bearer token; a direct call would be unauthenticated.
- Never fabricate a displayed value: a `null`/missing field from the API (e.g. `last_run: null`, `latest_price: null`) renders as an explicit "—" / "no data yet" / "stale" indicator, never a blank that looks like zero or a guessed number.
- Times from the backend are Unix epoch seconds in Asia/Kolkata-relevant context (`started_at`, `latest_ts`, `added_at`, `updated_at`) or ISO strings already in IST (`next_run_time`) — render all of them in IST explicitly (`Intl.DateTimeFormat` with `timeZone: "Asia/Kolkata"`), never the browser's local timezone, so a user outside India still sees NSE-relevant times correctly.
- The UI never offers to place a trade or execute an order anywhere — this is a read-only scanner/signal tool, matching the backend's own scope.
- Every mutating action (create/update/delete strategy, add/remove watchlist symbol, save settings, run-now) must surface the backend's actual error message on failure (esp. the 400 `{ errors: string[] }` validation-error shape from strategy create/update) — never a generic "something went wrong" that hides which field was invalid.
- Dark-theme-first, compact, "financial-terminal" aesthetic per spec §2 — reuse the sibling project's `globals.css` design tokens and density rather than inventing a new visual language.

## Review Focus

- A strategy create/update that gets a 400 with multiple validation errors (e.g. bad `scan_time` AND an unknown universe name) must show ALL of them to the user, not just the first — a reasonable person fixing one error expects to see the rest before resubmitting.
- `GET /dashboard`'s `strategies[].last_run` being `null` (a strategy that has never run yet) must render as "never run" or equivalent, not crash the page or show `undefined`.
- `run-now` can take a while (the backend scans synchronously in the request per the backend plan's documented parked limitation) — the button must show a pending/loading state and must not be clickable again mid-request, or a user double-clicking "Run now" could be confused about whether one or two scans fired.
- The Strategy Builder's condition editor must prevent submitting a condition with an indicator the backend doesn't know about reaching the API as a typo'd free-text string — a reasonable person expects a dropdown of valid indicators, not a text field that silently 400s with a cryptic backend error.
- A scan result row with `satisfied: false` must be visually distinguishable at a glance from `satisfied: true` (not just a boolean buried in a column) — the whole point of the Finder/Dashboard is "which ones matched," and a reasonable person expects matches to be visually prioritized, not read off column-by-column.

---

## Task 0: Project scaffolding

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.ts` (or `.js`, minimal)
- Create: `frontend/app/layout.tsx` (root layout, wraps `ClerkProvider`)
- Create: `frontend/app/providers.tsx` (React Query `QueryClientProvider`)
- Create: `frontend/app/globals.css`
- Create: `frontend/app/sign-in/[[...sign-in]]/page.tsx`
- Create: `frontend/.env.local.example`
- Create: `frontend/vitest.config.ts`

**Interfaces:**
- Produces: a runnable `npm run dev` Next.js app with Clerk sign-in wired at the root, importable `@/lib/*` and `@/components/*` path aliases (`tsconfig.json`'s `paths`), and the CSS custom-property design tokens (`--bg`, `--panel`, `--line`, `--text`, `--dim`, `--green`, `--red`, `--accent`, `--warn`) available globally for every later task's components.

- [ ] **Step 1:** Write `frontend/package.json` with dependencies `@clerk/nextjs`, `@tanstack/react-query`, `next`, `react`, `react-dom` and devDependencies `@types/node`, `@types/react`, `@types/react-dom`, `typescript`, `vitest` — use the same version ranges as `/home/anand-shaurya/Documents/personal/delta/frontend/package.json` (read that file for exact pinned versions) since this is a sibling, same-vintage project and there's no reason to diverge. Scripts: `dev` (`next dev -p 3001` — note port 3001, not 3000, so this app can run alongside the Delta frontend locally), `build`, `start`, `typecheck` (`tsc --noEmit`), `test` (`vitest run`).
- [ ] **Step 2:** Write `frontend/tsconfig.json` (copy structure from the Delta frontend's `tsconfig.json`, adjust nothing path-specific needed — it's a fresh project). Include `"@/*": ["./*"]` path alias.
- [ ] **Step 3:** Write `frontend/app/globals.css` — copy the full contents of `/home/anand-shaurya/Documents/personal/delta/frontend/app/globals.css` verbatim (it's the dark-theme design-token system this plan's Global Constraints call for reusing) and keep it as-is; later tasks add new component-specific classes to this same file rather than inventing a new stylesheet.
- [ ] **Step 4:** Write `frontend/app/layout.tsx` — root layout wrapping children in `<ClerkProvider>` and the `Providers` component from Step 5, with `<html lang="en">`/`<body>` and a `<link>` to the globals stylesheet (Next.js handles this automatically via the `import "./globals.css"` convention — follow the Delta frontend's `app/layout.tsx` structure).
- [ ] **Step 5:** Write `frontend/app/providers.tsx` — a `"use client"` component wrapping children in `<QueryClientProvider client={new QueryClient()}>` (one `QueryClient` instance per app, created once — follow the React Query Next.js App Router guidance of creating the client inside a `useState` initializer to avoid recreating it on every render).
- [ ] **Step 6:** Write `frontend/app/sign-in/[[...sign-in]]/page.tsx` — Clerk's catch-all sign-in page (`<SignIn />` from `@clerk/nextjs`), copied structurally from the Delta frontend's equivalent page.
- [ ] **Step 7:** Write `frontend/.env.local.example` documenting `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `BACKEND_URL` (default `http://127.0.0.1:8000`, matching the backend's own default port).
- [ ] **Step 8:** Write `frontend/vitest.config.ts` (minimal — matches Delta frontend's).
- [ ] **Step 9:** `cd frontend && npm install`, then `npm run typecheck` — confirm it passes with zero files beyond scaffolding (an empty/trivial typecheck pass is expected at this stage).
- [ ] **Step 10:** Commit.
```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/next.config.ts frontend/app frontend/.env.local.example frontend/vitest.config.ts
git commit -m "chore: scaffold scanner frontend (Next.js + Clerk + React Query)"
```

---

## Task 1: BFF proxy route + typed API client

**Files:**
- Create: `frontend/app/api/[...path]/route.ts`
- Create: `frontend/lib/proxy.ts`
- Create: `frontend/lib/api.ts`
- Create: `frontend/lib/types.ts`
- Create: `frontend/lib/format.ts`
- Test: `frontend/lib/proxy.test.ts`
- Test: `frontend/lib/format.test.ts`

**Interfaces:**
- Consumes: nothing from Task 0 beyond the scaffolded project.
- Produces: `buildBackendUrl(path: string[], search: string, base: string): string` (path-traversal-safe URL builder); the `GET/POST/PUT/DELETE` route handlers in `route.ts` that attach `Authorization: Bearer <clerk token>` and forward to `process.env.BACKEND_URL`; `class ApiError extends Error { status: number }`; `async function api<T>(method: string, path: string, body?: unknown): Promise<T>` (fetches `/api${path}`, throws `ApiError` on non-2xx, redirects to `/sign-in` on 401); all TypeScript types from the contract above in `lib/types.ts` (`Instrument`, `Strategy`, `Condition`, `ScanRun`, `ScanResultRow`, `DashboardStrategy`, `Settings`); `fmtIST(epochSecondsOrIso: number | string, opts?) -> string` and `fmtPrice(n: number | null) -> string` (returns `"—"` for `null`) in `format.ts`.

- [ ] **Step 1: Write the failing tests** for `buildBackendUrl` (mirror the Delta frontend's `lib/proxy.test.ts` exactly — same path-traversal-rejection cases: `".."`, `"."`, a segment containing `"/"`) and for `fmtPrice`/`fmtIST`:
```typescript
// lib/proxy.test.ts
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
```
```typescript
// lib/format.test.ts
import { describe, expect, it } from "vitest";
import { fmtPrice, fmtIST } from "./format";

describe("fmtPrice", () => {
  it("formats a number", () => { expect(fmtPrice(1234.5)).toBe("1,234.50"); });
  it("renders null as an em dash, never a blank or zero", () => { expect(fmtPrice(null)).toBe("—"); });
});

describe("fmtIST", () => {
  it("renders an epoch-seconds timestamp in Asia/Kolkata", () => {
    // 2026-01-15T09:00:00+05:30 == 1768446600 epoch seconds
    expect(fmtIST(1768446600)).toContain("09:00");
  });
});
```
- [ ] **Step 2: Run tests to verify they fail** — `cd frontend && npm test` → FAIL (modules don't exist).
- [ ] **Step 3: Implement `lib/proxy.ts`** — copy `buildBackendUrl` verbatim from `/home/anand-shaurya/Documents/personal/delta/frontend/lib/proxy.ts` (it's already correct and already has a passing test suite in the sibling project; this plan's only job is to reuse it unmodified).
- [ ] **Step 4: Implement `app/api/[...path]/route.ts`** — copy the Delta frontend's `app/api/[...path]/route.ts` verbatim (same BFF-proxy pattern: read Clerk token via `auth()`, 401 if absent, build the backend URL via `buildBackendUrl`, forward method/body/headers, return the backend's raw response body and status).
- [ ] **Step 5: Implement `lib/api.ts`** — copy the Delta frontend's `lib/api.ts` structure (the `api<T>()` fetch wrapper and `ApiError` class), but REMOVE the Delta-specific `412` "missing Delta credentials" branch (this scanner backend has no equivalent precondition-failed status) and keep only the 401-redirects-to-sign-in behavior plus generic non-2xx → `ApiError` with the backend's `detail` message extracted (this backend's 400 errors come back as `{ detail: { errors: string[] } }` for strategy validation — `errorMessage()` should join that array into a readable string, e.g. `error_message = Array.isArray(data?.detail?.errors) ? data.detail.errors.join("; ") : (typeof data?.detail === "string" ? data.detail : JSON.stringify(data?.detail ?? data))`).
- [ ] **Step 6: Implement `lib/types.ts`** — the TypeScript interfaces from this plan's "Backend API contract" section above, verbatim.
- [ ] **Step 7: Implement `lib/format.ts`** — `fmtPrice(n: number | null): string` (returns `"—"` for `null`, else `n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })`); `fmtIST(value: number | string, opts?: Intl.DateTimeFormatOptions): string` (if `value` is a `number`, treat as epoch seconds and `new Date(value * 1000)`; if `string`, `new Date(value)`; format with `timeZone: "Asia/Kolkata"`, default `opts` showing date+time).
- [ ] **Step 8: Run tests to verify they pass.**
- [ ] **Step 9: Commit.**
```bash
git add frontend/app/api frontend/lib
git commit -m "feat: add BFF proxy route and typed API client"
```

---

## Task 2: App shell (layout, nav, Clerk header)

**Files:**
- Create: `frontend/app/(app)/layout.tsx`
- Create: `frontend/components/Nav.tsx`
- Create: `frontend/components/Ui.tsx`
- Modify: `frontend/app/globals.css` (append any nav/header classes not already covered by the copied Delta stylesheet — check first, most should already exist)

**Interfaces:**
- Consumes: `@/lib/api` (`api` function), Clerk's `<UserButton />`.
- Produces: `<AppLayout>` wrapping every page under `app/(app)/` in a sticky header (app title + `UserButton`) and a `<Nav>` row; `Nav` renders links for `/` (Dashboard), `/watchlist`, `/finder`, `/strategies`, `/settings`, highlighting the active one via `usePathname()`; `Ui.tsx` exports `Stat`, `Tag`, `Chip` components (same shape as the Delta frontend's, reused for this app's stat tiles and status badges).

- [ ] **Step 1:** Write `components/Nav.tsx` — same structural pattern as the Delta frontend's `Nav.tsx` (a `LINKS` array of `{ href, label }`, `usePathname()`-based active-link highlighting), with this app's links: Dashboard (`/`), Watchlist (`/watchlist`), Finder (`/finder`), Strategies (`/strategies`), Settings (`/settings`).
- [ ] **Step 2:** Write `components/Ui.tsx` — copy `Stat`, `Tag`, `Chip` from the Delta frontend's `components/Ui.tsx` verbatim (generic presentational primitives, no Delta-specific logic in them).
- [ ] **Step 3:** Write `app/(app)/layout.tsx` — a header with an `<h1>` app title (e.g. "NSE Scanner") and `<UserButton />` on the right, then `<Nav />`, then `<main>{children}</main>` — simpler than the Delta frontend's layout (no live price ticker or open-positions strip needed here, since this isn't a trading app).
- [ ] **Step 4:** `npm run typecheck` — confirm it passes.
- [ ] **Step 5:** Commit.
```bash
git add frontend/app/\(app\)/layout.tsx frontend/components/Nav.tsx frontend/components/Ui.tsx frontend/app/globals.css
git commit -m "feat: add app shell (header, nav, Clerk UserButton)"
```

---

## Task 3: Dashboard page

**Files:**
- Create: `frontend/app/(app)/page.tsx`
- Create: `frontend/components/MarketStatusBadge.tsx`

**Interfaces:**
- Consumes: `GET /dashboard` via `api<DashboardResponse>("GET", "/dashboard")` (React Query, `refetchInterval: 60_000` — a 1-minute poll is reasonable for a dashboard that changes at most once a day plus a market-status flip twice a day).
- Produces: the `/` route rendering market status, a per-strategy row (name, last run status/time, next scheduled run, a "View results" link to the strategy's scan history if `last_run` exists), and a prominent empty state ("No strategies yet — create one" linking to `/strategies/new`) when `strategies` is empty.

- [ ] **Step 1:** Write `components/MarketStatusBadge.tsx` — takes `status: "pre_market" | "open" | "closed"`, renders a `<Tag>` with `cls="w"` (warn/amber) for `pre_market`, `cls="g"` (green) for `open`, `cls="d"` (dim/grey) for `closed`, with the label capitalized and underscores replaced with spaces ("Pre Market" / "Open" / "Closed").
- [ ] **Step 2:** Write `app/(app)/page.tsx` as a `"use client"` component: `useQuery(["dashboard"], () => api<DashboardResponse>("GET", "/dashboard"), { refetchInterval: 60_000 })`. Render:
  - A `<section>` with `<MarketStatusBadge>` and a loading/error state while the query is pending/errored.
  - A `<section>` per the spec's "Dashboard" requirements: a table or card list of `strategies`, each row showing `name`, last run's `status`/`started_at` (via `fmtIST`) and `matches_count` (render "never run" in place of these three when `last_run` is `null` — per this plan's Global Constraints, never show a blank/undefined), `next_run_time` (via `fmtIST`, or "not scheduled" if `null`), and a link to `/strategies/{strategy_id}/scans` (the scan-history view built in Task 6).
  - Empty state when `strategies.length === 0`.
- [ ] **Step 3:** `npm run typecheck`.
- [ ] **Step 4:** Commit.
```bash
git add frontend/app/\(app\)/page.tsx frontend/components/MarketStatusBadge.tsx
git commit -m "feat: add dashboard page (market status, per-strategy summary)"
```

---

## Task 4: Watchlist page

**Files:**
- Create: `frontend/app/(app)/watchlist/page.tsx`
- Create: `frontend/components/AddToWatchlistInput.tsx`

**Interfaces:**
- Consumes: `GET /watchlist` → `{ symbol, added_at }[]`; `GET /universe` (to resolve each watchlist symbol's full `Instrument` — name, kind, `yf_ticker` — since `/watchlist` itself only stores `symbol`); `POST /watchlist { symbol }`; `DELETE /watchlist/{symbol}`.
- Produces: the `/watchlist` route: a searchable/sortable table of watchlist entries (symbol, resolved name, kind badge stock/index, added date), a text input + "Add" button wired to `POST /watchlist` (invalidating the `["watchlist"]` query on success), and a remove button per row wired to `DELETE /watchlist/{symbol}`.

- [ ] **Step 1:** Write `components/AddToWatchlistInput.tsx` — a controlled text input (uppercase-on-type, matching the Delta frontend's symbol-input convention) + "Add" button; on submit, calls `useMutation(() => api("POST", "/watchlist", { symbol }))`, invalidates `["watchlist"]` on success, shows the backend's error message (via `ApiError.message`) on failure (e.g. if the symbol doesn't exist in any known universe — note: the backend's `POST /watchlist` does NOT currently validate the symbol against the instrument master, so accept whatever the backend accepts; this input doesn't need client-side symbol validation for MVP).
- [ ] **Step 2:** Write `app/(app)/watchlist/page.tsx` — `useQuery(["watchlist"], ...)` and `useQuery(["universe"], ...)`; build a `Map<symbol, Instrument>` from the universe response (flatten all 5 universe arrays, keyed by `symbol`) to resolve each watchlist entry's display name/kind (fall back to showing the bare symbol with a "kind: unknown" tag if a watchlist symbol isn't found in any known universe — don't crash). Render a table: Symbol | Name | Kind (Tag: stock/index) | Added (fmtIST) | Remove button. Client-side search-filter input over the symbol/name (plain JS `.filter()`, no backend search endpoint needed for a watchlist-sized list). Sortable by clicking column headers (simple local state, ascending/descending toggle).
- [ ] **Step 3:** `npm run typecheck`.
- [ ] **Step 4:** Commit.
```bash
git add frontend/app/\(app\)/watchlist frontend/components/AddToWatchlistInput.tsx
git commit -m "feat: add watchlist page (add/remove, search, sort)"
```

---

## Task 5: Stock & Index Finder page

**Files:**
- Create: `frontend/app/(app)/finder/page.tsx`
- Create: `frontend/components/UniverseChips.tsx`

**Interfaces:**
- Consumes: `GET /universe` → `{ [universeName]: Instrument[] }`; `POST /watchlist` (to add a found instrument directly from the Finder).
- Produces: the `/finder` route: a universe-selector (chip row: Nifty 50 / Nifty Next 50 / Bank Nifty / Nifty IT / Indices / All Stocks — note: per the backend's actual `UNIVERSE_NAMES`, confirm the exact 5 names exposed by `GET /universe` at implementation time and label the chips accordingly, since "Nifty Next 50" may or may not be a distinct universe from "all_stocks" depending on what Task 2 of the backend plan actually shipped — read `backend/instruments/universe.py`'s `VALID_UNIVERSE_NAMES`/`list_universe` to get the authoritative list, don't guess from the spec alone), a text search box filtering the selected universe(s) by symbol/name substring, a table of matching instruments (symbol, name, kind), and an "Add to watchlist" button per row.

- [ ] **Step 1:** Write `components/UniverseChips.tsx` — a `Chip`-based multi-select (reusing `Ui.tsx`'s `Chip`) over the universe names returned by `GET /universe`'s keys (don't hard-code the list in this component — derive it from the query response so it automatically tracks whatever the backend actually exposes), with an "All" chip that selects every universe at once.
- [ ] **Step 2:** Write `app/(app)/finder/page.tsx` — `useQuery(["universe"], ...)`; local state for selected universes (default: all) and a search string; derive the filtered instrument list by unioning the selected universes' arrays (dedupe by `symbol`, since `all_stocks` may overlap with the per-index universes) and filtering by case-insensitive substring match on `symbol` or `name`. Render as a table with an "Add to watchlist" button per row — `useMutation(() => api("POST", "/watchlist", { symbol: instrument.symbol }))`, disable the button and show a checkmark/"Added" state for instruments already on the watchlist (cross-reference against a `GET /watchlist` query, matched by symbol).
- [ ] **Step 3:** `npm run typecheck`.
- [ ] **Step 4:** Commit.
```bash
git add frontend/app/\(app\)/finder frontend/components/UniverseChips.tsx
git commit -m "feat: add stock & index finder page (universe browse, search, add to watchlist)"
```

---

## Task 6: Strategy list + Strategy Builder (create/edit) pages

**Files:**
- Create: `frontend/app/(app)/strategies/page.tsx`
- Create: `frontend/app/(app)/strategies/new/page.tsx`
- Create: `frontend/app/(app)/strategies/[id]/edit/page.tsx`
- Create: `frontend/components/StrategyForm.tsx`
- Create: `frontend/components/ConditionEditor.tsx`
- Create: `frontend/lib/indicators.ts`
- Test: `frontend/lib/indicators.test.ts`

**Interfaces:**
- Consumes: `GET/POST/PUT/DELETE /strategies[/{id}]`; `GET /universe` (for the universe multi-select, reusing `UniverseChips` from Task 5).
- Produces: `/strategies` (list view: name, universe summary, enabled toggle, last/next run if available via a lightweight re-fetch of `/dashboard` or a per-strategy `/scans?strategy_id=&limit=1`, edit/delete/run-now buttons); `/strategies/new` and `/strategies/[id]/edit` both rendering `<StrategyForm initial={...} onSubmit={...}>`; `StrategyForm` is the full spec §3 strategy builder (instrument type, universe multi-select, timeframe, provider, one-or-more `ConditionEditor` rows combined with an AND/OR toggle, `min_consecutive_sessions` number input, `scan_time`/`scan_days` schedule picker, enabled toggle); `KNOWN_INDICATORS: { value: string; label: string; needsLength: boolean }[]` in `lib/indicators.ts` (a hard-coded list mirroring the backend's `_INDICATOR_FUNCS` dispatch table — `ema`, `sma`, `rsi`, `macd`, `bollinger`, `supertrend`, `adx`, `vwap_session`, `vwap_rolling` — read `backend/indicators/calc.py`'s actual function names at implementation time to keep this list in sync, don't guess).

- [ ] **Step 1: Write the failing test** for the one pure-logic piece worth unit testing here — `lib/indicators.ts`'s helper that turns a `ConditionEditor`'s form state into the backend's `compare_to` spec string format (e.g. indicator `"ema"` + length `200` → `"ema:200"`, matching the backend's `_parse_spec` parsing convention confirmed by reading `backend/scanner/engine.py`):
```typescript
// lib/indicators.test.ts
import { describe, expect, it } from "vitest";
import { buildCompareToSpec, KNOWN_INDICATORS } from "./indicators";

describe("buildCompareToSpec", () => {
  it("builds an indicator:length spec", () => {
    expect(buildCompareToSpec("ema", 200)).toBe("ema:200");
  });
  it("returns the literal 'price' when comparing to raw price", () => {
    expect(buildCompareToSpec("price", undefined)).toBe("price");
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
```
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3:** Implement `lib/indicators.ts`: `KNOWN_INDICATORS` array (read `backend/indicators/calc.py` for the authoritative function list before writing this), `buildCompareToSpec(indicator: string, length: number | undefined): string` (`"price"` stays `"price"` literally; anything else becomes `` `${indicator}:${length}` `` when `length` is provided, else bare `indicator` name — match whatever format `backend/scanner/engine.py`'s `_parse_spec` actually parses, confirmed by reading that function, not assumed).
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5:** Write `components/ConditionEditor.tsx` — one row of the strategy builder: indicator dropdown (from `KNOWN_INDICATORS`), a length number input (shown only when `needsLength`), comparison dropdown (`above`/`below`/`crosses_above`/`crosses_below`), a `compare_to` selector (radio or dropdown: "Price" vs "Another indicator" — if the latter, show a second indicator+length pair and build its spec via `buildCompareToSpec`), remove-condition button.
- [ ] **Step 6:** Write `components/StrategyForm.tsx` — full form: name (text), instrument type (select: stock/index/both), universe (reuse `UniverseChips`, multi-select), timeframe (select: daily/weekly/5m/15m/1h — with a visible warning/disabled-reason when an intraday timeframe is paired with a provider lacking intraday support, per spec §3's VWAP/session caveats; since the backend's `validate_strategy` is the real source of truth for valid combinations, this is a soft client-side hint, not a hard block — always let the user submit and surface the backend's actual validation error if it disagrees), provider (select: yfinance/nse), one or more `ConditionEditor` rows + an "Add condition" button + an AND/OR toggle (shown only when 2+ conditions exist), `min_consecutive_sessions` (number input, min 1), `scan_time` (HTML `<input type="time">`), `scan_days` (radio: "Every day" vs "Select days" → day-of-week checkboxes 0=Mon..6=Sun), enabled (checkbox). On submit, calls the provided `onSubmit(strategy: StrategyIn)` prop; on a 400 `ApiError`, render every error string from the backend's `errors` array as a list (per this plan's Review Focus — show all errors, not just one).
- [ ] **Step 7:** Write `app/(app)/strategies/new/page.tsx` — renders `<StrategyForm>` with sensible defaults (`timeframe: "daily"`, `provider: "yfinance"`, `logic: "AND"`, `min_consecutive_sessions: 5`, `scan_time: "09:00"`, `scan_days: "daily"`, `enabled: true`, one empty condition), `onSubmit` calls `POST /strategies`, redirects to `/strategies` on success.
- [ ] **Step 8:** Write `app/(app)/strategies/[id]/edit/page.tsx` — fetches the existing strategy via `GET /strategies` (find by `id` client-side, since there's no `GET /strategies/{id}` single-fetch endpoint — confirm this against `main.py` at implementation time; if a single-strategy GET does exist, use it instead), renders `<StrategyForm initial={strategy}>`, `onSubmit` calls `PUT /strategies/{id}`.
- [ ] **Step 9:** Write `app/(app)/strategies/page.tsx` — `useQuery(["strategies"], ...)`; table: name, universe (comma-joined), instrument type, enabled toggle (immediately calls `PUT /strategies/{id}` with `enabled` flipped on click — optimistic update, revert on error), edit link, delete button (with a confirm step — reuse a `ConfirmDialog` pattern if useful, or a simple `window.confirm` for MVP), "Run now" button (calls `POST /strategies/{id}/run-now`, disabled + shows a spinner while the mutation is in flight per this plan's Review Focus on run-now's long synchronous duration, and on success links to the new `run_id`'s results page from Task 7).
- [ ] **Step 10:** `npm run typecheck` and `npm test`.
- [ ] **Step 11:** Commit.
```bash
git add frontend/app/\(app\)/strategies frontend/components/StrategyForm.tsx frontend/components/ConditionEditor.tsx frontend/lib/indicators.ts frontend/lib/indicators.test.ts
git commit -m "feat: add strategy list and strategy builder (create/edit) pages"
```

---

## Task 7: Scan history and results pages

**Files:**
- Create: `frontend/app/(app)/strategies/[id]/scans/page.tsx`
- Create: `frontend/app/(app)/scans/[runId]/page.tsx`
- Create: `frontend/components/ScanResultsTable.tsx`

**Interfaces:**
- Consumes: `GET /scans?strategy_id=&limit=` → `ScanRun[]`; `GET /scans/{run_id}/results` → `ScanResultRow[]`.
- Produces: `/strategies/[id]/scans` (a history list of runs for one strategy: started/finished time, status badge, instruments scanned, matches count, link to each run's results); `/scans/[runId]` (the results table for one run); `ScanResultsTable` renders `ScanResultRow[]` with matched rows visually distinguished per this plan's Review Focus.

- [ ] **Step 1:** Write `components/ScanResultsTable.tsx` — takes `results: ScanResultRow[]`; sorts matches first (`satisfied: true` rows before `false`); renders a table: Symbol | Kind | Satisfied (a prominent `Tag` — green "Match" for `true`, dim "No match" for `false`) | Consecutive Sessions | Latest Price (via `fmtPrice`, showing "—" for `null` per Global Constraints — and when `latest_price` is `null`, also show a "data unavailable" note instead of leaving the row looking like a normal non-match) | Last Candle Date | indicator values (parse `indicator_values_json`, render as a compact comma-joined `key: value` string). Include a client-side filter toggle: "Show all" vs "Matches only."
- [ ] **Step 2:** Write `app/(app)/strategies/[id]/scans/page.tsx` — `useQuery(["scans", strategyId], () => api("GET", `/scans?strategy_id=${strategyId}&limit=50`))`; table of runs (started_at via `fmtIST`, status `Tag`, `instruments_scanned`, `matches_count`, a link to `/scans/{id}` for results, and the `error` field shown inline when `status === "error"` per this plan's never-hide-a-failure constraint).
- [ ] **Step 3:** Write `app/(app)/scans/[runId]/page.tsx` — `useQuery(["scanResults", runId], () => api("GET", `/scans/${runId}/results`))`; renders `<ScanResultsTable results={data}>`, with a 404-aware error state (the backend scopes this endpoint to the authenticated user, so a 404 here means "not your run or doesn't exist" — render that message plainly, not a generic error).
- [ ] **Step 4:** `npm run typecheck`.
- [ ] **Step 5:** Commit.
```bash
git add frontend/app/\(app\)/strategies/\[id\]/scans frontend/app/\(app\)/scans frontend/components/ScanResultsTable.tsx
git commit -m "feat: add scan history and results pages"
```

---

## Task 8: Settings page (notifications + data provider)

**Files:**
- Create: `frontend/app/(app)/settings/page.tsx`

**Interfaces:**
- Consumes: `GET/PUT /settings`.
- Produces: `/settings` — a form: Telegram chat ID (text input, prefilled from `telegram_chat_id`), Telegram bot token (password-style input, NEVER prefilled with the actual token since the backend only ever returns `telegram_bot_token_configured: boolean` — show a "configured ✓ (enter a new value to replace)" hint instead of a blank-looking-like-not-set field), active provider (select: yfinance/nse, prefilled from `active_provider`, with a one-line disclaimer per spec §5 that this setting is informational for MVP and strategies still use their own per-strategy `provider` field — confirm against the backend fix-wave ledger's note that `active_provider` is stored but not yet read by the scanner, and say so plainly in the UI rather than implying it controls scan behavior it doesn't yet control), Save button.

- [ ] **Step 1:** Write `app/(app)/settings/page.tsx` — `useQuery(["settings"], ...)` to prefill the form; `useMutation(() => api("PUT", "/settings", body))` on save, invalidating `["settings"]`; only send `telegram_bot_token` in the PUT body if the user actually typed a new value in that field (leave it `undefined` otherwise, matching the backend's partial-update semantics — sending an empty string would overwrite the existing token with blank, which is wrong). Show a save-confirmation toast/message on success and the backend's error message on failure.
- [ ] **Step 2:** `npm run typecheck`.
- [ ] **Step 3:** Commit.
```bash
git add frontend/app/\(app\)/settings
git commit -m "feat: add settings page (Telegram notifications, data provider)"
```

---

## Self-review notes

- Spec coverage: §2.A (Dashboard) → Task 3; §2.B (Watchlist) → Task 4; §2.C (Finder) → Task 5; §3 (Strategy Builder) → Task 6; §8 (notifications/history — the history half) → Task 7, (notifications half) → Task 8; §6 (stack: Next.js/React/Tailwind — this plan uses handwritten CSS matching the sibling project instead of Tailwind specifically, since the sibling project it's modeled on made that same substitution and the spec's "Tailwind CSS" was a suggestion under "Suggested stack," not a hard requirement — flagged here as a deliberate, disclosed deviation, not a silent one); charts (`Lightweight Charts`, spec §6) are explicitly NOT in this plan — no task renders a price/indicator chart, only tabular data. If charting is wanted, it's a follow-up task once this MVP's pages are live and the actual data shapes are confirmed against real backend responses.
- No backend changes in this plan — it is strictly additive against the already-merged `backend/` on `master`.
- Auth: this plan assumes a Clerk project already exists and its publishable/secret keys will be supplied via `.env.local` before `npm run dev` is first run — provisioning the actual Clerk project (signing up, getting keys) is an environment-setup step outside this plan's tasks, same as it was for the backend plan.
