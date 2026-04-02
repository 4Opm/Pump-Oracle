import pytest
from src.analyzers.onchain import (
    parse_pair,
    is_interesting,
    calculate_buy_sell_ratio,
    analyze_pairs,
    get_interesting_pairs,
)

# ── Dane testowe ────────────────────────────────────────────────────────────

def make_pair(**overrides) -> dict:
    base = {
        "pairAddress":   "TestAddress123",
        "dexId":         "raydium",
        "baseToken":     {"address": "BaseAddr", "name": "TestCoin", "symbol": "TEST"},
        "quoteToken":    {"address": "QuoteAddr", "name": "Wrapped SOL", "symbol": "SOL"},
        "priceUsd":      "0.001",
        "liquidity":     {"usd": 20000},
        "volume":        {"h24": 80000, "h1": 5000},
        "priceChange":   {"h1": 15.0, "h24": 30.0},
        "txns":          {"h1": {"buys": 150, "sells": 80}},
        "pairCreatedAt": 1700000000000,  # stary timestamp — wiek będzie duży
        "url":           "https://dexscreener.com/solana/test",
    }
    base.update(overrides)
    return base


def make_fresh_pair(**overrides) -> dict:
    """Para która spełnia wszystkie kryteria filtrowania."""
    import time
    fresh_ts = int(time.time() * 1000) - (10 * 3600 * 1000)  # 10 godzin temu
    return make_pair(pairCreatedAt=fresh_ts, **overrides)


# ── Testy parse_pair ────────────────────────────────────────────────────────

class TestParsePair:

    def test_poprawna_para_zwraca_dict(self):
        result = parse_pair(make_fresh_pair())
        assert result is not None
        assert isinstance(result, dict)

    def test_zawiera_wymagane_pola(self):
        result = parse_pair(make_fresh_pair())
        wymagane = [
            "pair_address", "name", "liquidity_usd",
            "volume_24h", "change_1h", "age_hours", "url"
        ]
        for pole in wymagane:
            assert pole in result, f"Brak pola: {pole}"

    def test_nazwa_pary_poprawna(self):
        result = parse_pair(make_fresh_pair())
        assert result["name"] == "TEST/SOL"

    def test_brak_liquidity_daje_zero(self):
        result = parse_pair(make_fresh_pair(liquidity=None))
        assert result["liquidity_usd"] == 0.0

    def test_brak_volume_daje_zero(self):
        result = parse_pair(make_fresh_pair(volume=None))
        assert result["volume_24h"] == 0.0

    def test_wiek_pary_jest_liczony(self):
        result = parse_pair(make_fresh_pair())
        assert result["age_hours"] is not None
        assert 9 < result["age_hours"] < 11  # ~10h


# ── Testy calculate_buy_sell_ratio ──────────────────────────────────────────

class TestBuySellRatio:

    def test_normalny_stosunek(self):
        pair = {"buys_1h": 100, "sells_1h": 50}
        assert calculate_buy_sell_ratio(pair) == pytest.approx(2.0)

    def test_brak_sprzedajacych(self):
        pair = {"buys_1h": 100, "sells_1h": 0}
        assert calculate_buy_sell_ratio(pair) == float("inf")

    def test_brak_transakcji(self):
        pair = {"buys_1h": 0, "sells_1h": 0}
        assert calculate_buy_sell_ratio(pair) == 0.0

    def test_wiecej_sprzedajacych(self):
        pair = {"buys_1h": 30, "sells_1h": 100}
        assert calculate_buy_sell_ratio(pair) == pytest.approx(0.3)


# ── Testy is_interesting ────────────────────────────────────────────────────

class TestIsInteresting:

    def test_dobra_para_przechodzi(self):
        parsed = parse_pair(make_fresh_pair())
        parsed["buy_sell_ratio"] = calculate_buy_sell_ratio(parsed)
        ok, reasons = is_interesting(parsed)
        assert ok, f"Para powinna przejść filtry. Powody odrzucenia: {reasons}"

    def test_za_mala_plynnosc(self):
        parsed = parse_pair(make_fresh_pair(liquidity={"usd": 100}))
        parsed["buy_sell_ratio"] = calculate_buy_sell_ratio(parsed)
        ok, reasons = is_interesting(parsed)
        assert not ok
        assert any("płynność" in r.lower() for r in reasons)

    def test_za_maly_wolumen(self):
        parsed = parse_pair(make_fresh_pair(volume={"h24": 100, "h1": 10}))
        parsed["buy_sell_ratio"] = calculate_buy_sell_ratio(parsed)
        ok, reasons = is_interesting(parsed)
        assert not ok
        assert any("wolumen" in r.lower() for r in reasons)

    def test_za_stara_para(self):
        stara = make_pair(pairCreatedAt=1000000000)  # rok 2001
        parsed = parse_pair(stara)
        parsed["buy_sell_ratio"] = calculate_buy_sell_ratio(parsed)
        ok, reasons = is_interesting(parsed)
        assert not ok
        assert any("stara" in r.lower() for r in reasons)

    def test_ujemna_zmiana_ceny(self):
        parsed = parse_pair(make_fresh_pair(priceChange={"h1": -10.0, "h24": -5.0}))
        parsed["buy_sell_ratio"] = calculate_buy_sell_ratio(parsed)
        ok, reasons = is_interesting(parsed)
        assert not ok
        assert any("wzrost" in r.lower() for r in reasons)


# ── Testy analyze_pairs ─────────────────────────────────────────────────────

class TestAnalyzePairs:

    def test_pusta_lista_zwraca_pusty_df(self):
        df = analyze_pairs([])
        assert df.empty

    def test_zwraca_dataframe_z_kolumnami(self):
        import pandas as pd
        df = analyze_pairs([make_fresh_pair()])
        assert isinstance(df, pd.DataFrame)
        assert "interesting" in df.columns
        assert "buy_sell_ratio" in df.columns

    def test_dobra_para_jest_ciekawa(self):
        df = analyze_pairs([make_fresh_pair()])
        assert df["interesting"].any()

    def test_zla_para_nie_jest_ciekawa(self):
        zla = make_fresh_pair(liquidity={"usd": 1}, volume={"h24": 1, "h1": 0})
        df = analyze_pairs([zla])
        assert not df["interesting"].any()