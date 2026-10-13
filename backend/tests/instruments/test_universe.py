from instruments.universe import list_universe, resolve


def test_nifty50_has_all_fifty_stock_instruments():
    # nifty50.json is now refreshed from NSE's own official constituent CSV
    # (see scripts/refresh_instrument_lists.py and its "_meta.source" key),
    # not a best-effort snapshot, so this asserts the exact live count.
    insts = list_universe("nifty50")
    assert len(insts) == 50
    assert all(i.kind == "stock" for i in insts)


def test_banknifty_has_stock_instruments():
    insts = list_universe("banknifty")
    assert len(insts) >= 10
    assert all(i.kind == "stock" for i in insts)


def test_niftyit_has_stock_instruments():
    insts = list_universe("niftyit")
    assert len(insts) >= 8
    assert all(i.kind == "stock" for i in insts)


def test_indices_universe_has_index_instruments():
    # indices.json is a broader set of NSE/BSE indices than the original 4,
    # but deliberately excludes tickers yfinance only exposes a current
    # quote for (no real daily history -> indicators can never compute) -
    # see indices.json's "_meta.note" for the excluded list and why.
    insts = list_universe("indices")
    assert len(insts) >= 10
    assert all(i.kind == "index" for i in insts)
    symbols = {i.symbol for i in insts}
    assert {"NIFTY50", "BANKNIFTY", "NIFTYIT", "SENSEX"} <= symbols


def test_indices_universe_excludes_quote_only_tickers():
    # Regression: NIFTYFIN (and 17 other sectoral tickers) were briefly
    # included after the indices-list expansion, but yfinance only ever
    # returns ONE row of "history" for them regardless of lookback window -
    # a strategy scanning them would always show satisfied=False with every
    # indicator value null, which looks broken even though it's technically
    # "never fabricate a value" working as designed. Dropped until yfinance
    # (or a future provider) actually backs them with real daily candles.
    insts = list_universe("indices")
    symbols = {i.symbol for i in insts}
    assert "NIFTYFIN" not in symbols
    assert "NIFTYAUTO" not in symbols


def test_all_stocks_is_deduped_union():
    all_stocks = list_universe("all_stocks")
    symbols = [i.symbol for i in all_stocks]
    assert len(symbols) == len(set(symbols))
    assert len(all_stocks) >= len(list_universe("nifty50"))
    assert all(i.kind == "stock" for i in all_stocks)


def test_resolve_known_symbol():
    inst = resolve("RELIANCE")
    assert inst is not None
    assert inst.yf_ticker == "RELIANCE.NS"


def test_resolve_known_index_symbol():
    inst = resolve("NIFTY50")
    assert inst is not None
    assert inst.yf_ticker == "^NSEI"
    assert inst.kind == "index"


def test_resolve_unknown_symbol_returns_none():
    assert resolve("NOT_A_REAL_SYMBOL") is None
