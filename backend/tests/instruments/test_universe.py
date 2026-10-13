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
    insts = list_universe("indices")
    assert len(insts) == 4
    assert all(i.kind == "index" for i in insts)


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
