"""
price_service.py birim testleri (FAZ C2)

TÜM harici HTTP çağrıları mock'lanmıştır — hiçbir test gerçek ağ isteği atmaz.
(Çalışma Kuralı #1: sıfır kota israfı, Kural #6: fallback zinciri.)
"""

import json

import pytest

from price_service import SmartPriceDiscoveryEngine


@pytest.fixture
def motor():
    """Her test için temiz bir motor örneği (singleton'a dokunmadan)."""
    return SmartPriceDiscoveryEngine()


def _arama_indeksi_yukle(motor, kayitlar):
    motor.symbol_search_index = kayitlar


# ===========================================================================
# SEMBOL ARAMA
# ===========================================================================

def test_bos_sorgu_bos_liste_doner(motor):
    assert motor.search_symbols("") == []
    assert motor.search_symbols("   ") == []


def test_tam_eslesme_en_uste_gelir(motor, monkeypatch):
    _arama_indeksi_yukle(motor, [
        {"symbol": "BTCDOWNUSDT", "base": "BTCDOWN", "display": "BTCDOWN/USDT",
         "exchange": "BINANCE", "price": 1.0},
        {"symbol": "BTCUSDT", "base": "BTC", "display": "BTC/USDT",
         "exchange": "BINANCE", "price": 100000.0},
    ])
    # DEX'e düşmesin diye ağ çağrısını kapat
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: None)

    sonuclar = motor.search_symbols("BTC")
    # İlk sırada BTC ile ilgili bir kayıt olmalı (DEX seçeneği veya tam eşleşme)
    assert any(s["base"] == "BTC" for s in sonuclar[:2])


def test_arama_sonuclari_tekrarsizdir(motor, monkeypatch):
    _arama_indeksi_yukle(motor, [
        {"symbol": "ETHUSDT", "base": "ETH", "display": "ETH/USDT",
         "exchange": "BINANCE", "price": 2000.0},
        {"symbol": "ETHUSDT", "base": "ETH", "display": "ETH/USDT",
         "exchange": "BINANCE", "price": 2000.0},
    ])
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: None)

    sonuclar = motor.search_symbols("ETH")
    anahtarlar = [f"{s['symbol']}@{s['exchange']}" for s in sonuclar]
    assert len(anahtarlar) == len(set(anahtarlar)), "Aynı sembol/borsa iki kez dönmemeli"


def test_arama_limiti_asilmaz(motor, monkeypatch):
    _arama_indeksi_yukle(motor, [
        {"symbol": f"COIN{i}USDT", "base": f"COIN{i}", "display": f"COIN{i}/USDT",
         "exchange": "BINANCE", "price": 1.0}
        for i in range(50)
    ])
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: None)

    assert len(motor.search_symbols("COIN", limit=5)) <= 5


# ===========================================================================
# FİYAT ÖNBELLEĞİ VE ARAMA
# ===========================================================================

def test_onbellekten_fiyat_okuma(motor):
    motor.prices = {"BTCUSDT": {"price": 100000.0, "source": "BINANCE"}}
    assert motor.get_price_for_symbol("BTCUSDT")["price"] == 100000.0


def test_usdt_soneki_olmadan_da_bulunur(motor):
    """BNB, SOL, ETH gibi soneksiz kayıtlar için — gerçek veride mevcut."""
    motor.prices = {"BTCUSDT": {"price": 100000.0, "source": "BINANCE"}}
    assert motor.get_price_for_symbol("BTC")["price"] == 100000.0


def test_bulunamayan_sembol_olu_olarak_isaretlenir(motor, monkeypatch):
    """Kural #6: fiyat bulunamazsa uygulama çökmemeli, 'ölü' dönmeli."""
    motor.prices = {}
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: None)

    sonuc = motor.get_price_for_symbol("YOKBOYLECOIN")
    assert sonuc["is_dead"] is True
    assert sonuc["price"] == 0.0


def test_cex_te_olmayan_token_dex_ten_bulunur(motor, monkeypatch):
    """Kademe 3: Binance/MEXC'te yoksa DexScreener devreye girer."""
    sahte_dex = {
        "price": 2.5e-09, "open_price": 2.4e-09, "change_pct": 4.1,
        "source": "DEX (BSC Pancakeswap)", "base_symbol": "CPL",
        "is_dead": False, "is_dex": True,
    }
    motor.prices = {}
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: sahte_dex)

    sonuc = motor.get_price_for_symbol("CPL")
    assert sonuc["is_dex"] is True
    assert sonuc["price"] == pytest.approx(2.5e-09)
    # Sonuç önbelleğe yazılmalı ki tekrar sorgulanmasın
    assert "CPL" in motor.prices


# ===========================================================================
# SPARKLINE (7 GÜNLÜK MİNİ GRAFİK)
# ===========================================================================

def test_sparkline_binance_verisinden_uretilir(motor, monkeypatch):
    # Binance klines formatı: her mum bir liste, index 4 = kapanış
    sahte_mumlar = [[0, "0", "0", "0", str(90 + i), "0"] for i in range(7)]

    class SahteYanit:
        def read(self): return json.dumps(sahte_mumlar).encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("price_service.urllib.request.urlopen", lambda *a, **k: SahteYanit())

    sonuc = motor.get_sparkline_7d("BTCUSDT", live_price=100.0)
    assert len(sonuc["points"]) == 7
    assert sonuc["points"][-1] == pytest.approx(100.0), "Son nokta canlı fiyatla güncellenmeli"
    assert sonuc["min_price"] == min(sonuc["points"])
    assert sonuc["max_price"] == max(sonuc["points"])


def test_sparkline_ag_hatasinda_sentetik_egri_uretir(motor, monkeypatch):
    """Kural #6: Binance erişilemezse DEX tokenları için sentetik eğri üretilir."""
    def patla(*a, **k):
        raise OSError("ağ yok")
    monkeypatch.setattr("price_service.urllib.request.urlopen", patla)

    sonuc = motor.get_sparkline_7d("CPLUSDT", live_price=2.0e-09, change_24h=5.0)
    assert len(sonuc["points"]) == 7
    assert sonuc["points"][-1] == pytest.approx(2.0e-09)

    # Regresyon testi — testlerin yakaladığı gerçek bug:
    # Sentetik eğri round(..., 8) ile yuvarlanıyordu. CPL (~2.3e-09) gibi nano
    # fiyatlı DEX tokenlarında tüm ara noktalar 0.0'a çöküyor, 7 günlük mini
    # grafik "düz sıfır çizgisi + son noktada dikey sıçrama" olarak çiziliyordu.
    assert all(p > 0 for p in sonuc["points"]), (
        "Nano fiyatlarda ara noktalar sıfıra çökmemeli (round(...,8) regresyonu)"
    )
    # Noktalar canlı fiyatla aynı büyüklük mertebesinde olmalı
    assert all(1.0e-10 < p < 1.0e-08 for p in sonuc["points"])


def test_sparkline_normal_fiyatlarda_da_dogru_calisir(motor, monkeypatch):
    """Nano düzeltmesi normal fiyatlı coinleri bozmamalı."""
    def patla(*a, **k):
        raise OSError("ağ yok")
    monkeypatch.setattr("price_service.urllib.request.urlopen", patla)

    sonuc = motor.get_sparkline_7d("BTCUSDT", live_price=100000.0, change_24h=5.0)
    assert len(sonuc["points"]) == 7
    assert sonuc["points"][-1] == pytest.approx(100000.0)
    assert all(50000.0 < p < 150000.0 for p in sonuc["points"])


def test_sparkline_onbellege_alinir(motor, monkeypatch):
    cagri_sayaci = {"n": 0}
    sahte_mumlar = [[0, "0", "0", "0", str(90 + i), "0"] for i in range(7)]

    class SahteYanit:
        def read(self):
            cagri_sayaci["n"] += 1
            return json.dumps(sahte_mumlar).encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("price_service.urllib.request.urlopen", lambda *a, **k: SahteYanit())

    motor.get_sparkline_7d("BTCUSDT", live_price=100.0)
    motor.get_sparkline_7d("BTCUSDT", live_price=101.0)
    assert cagri_sayaci["n"] == 1, "İkinci çağrı önbellekten gelmeli (15 dk TTL)"


# ===========================================================================
# FİYAT GÜNCELLEME DÖNGÜSÜ
# ===========================================================================

def test_binance_kademesi_dusuk_hacimli_semboleri_eler(motor, monkeypatch):
    """Kademe 1 filtresi: fiyat > 0 VE hacim > 0.01 olmalı."""
    binance_ticker = [
        {"symbol": "BTCUSDT", "lastPrice": "100000", "volume": "500", "openPrice": "98000", "priceChangePercent": "2.0"},
        {"symbol": "SIFIRUSDT", "lastPrice": "0", "volume": "500", "openPrice": "0", "priceChangePercent": "0"},
        {"symbol": "OLUUSDT", "lastPrice": "1.0", "volume": "0", "openPrice": "1.0", "priceChangePercent": "0"},
    ]

    def sahte_getir(url, timeout=5, user_agent=None):
        if "binance" in url:
            return binance_ticker
        raise OSError("MEXC bu testte devre dışı")   # kademeleri ayrı tut

    monkeypatch.setattr(motor, "fetch_url_json", sahte_getir)
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: None)

    motor.update_all_prices()

    assert "BTCUSDT" in motor.prices
    assert "SIFIRUSDT" not in motor.prices, "Fiyatı 0 olan sembol alınmamalı"
    assert "OLUUSDT" not in motor.prices, "Hacmi 0 olan sembol Binance kademesinde alınmamalı"


def test_mexc_kademesi_dusuk_hacimli_tokenlari_kabul_eder(motor, monkeypatch):
    """
    Kademe 2'de bilinçli olarak hacim filtresi YOKTUR: MEXC, Binance'te
    bulunmayan ince likiditeli altcoinler için son CEX şansıdır. Hacme göre
    elemek kullanıcının gerçekten tuttuğu tokenları görünmez yapardı.
    """
    def sahte_getir(url, timeout=5, user_agent=None):
        if "binance" in url:
            raise OSError("Binance bu testte devre dışı")
        return [{"symbol": "INCEUSDT", "lastPrice": "0.5", "volume": "0",
                 "openPrice": "0.5", "priceChangePercent": "0"}]

    monkeypatch.setattr(motor, "fetch_url_json", sahte_getir)
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: None)

    motor.update_all_prices()

    assert "INCEUSDT" in motor.prices
    assert motor.prices["INCEUSDT"]["source"] == "MEXC"


def test_tum_kaynaklar_coktugunde_uygulama_ayakta_kalir(motor, monkeypatch):
    """Kural #6: Her kaynak başarısız olsa da update_all_prices istisna fırlatmamalı."""
    def patla(*a, **k):
        raise OSError("ağ yok")
    monkeypatch.setattr(motor, "fetch_url_json", patla)
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: None)

    motor.update_all_prices()   # istisna fırlatmamalı
    assert motor.prices == {}


def test_binance_fiyatlari_mexc_tarafindan_ezilmez(motor, monkeypatch):
    """Kademe önceliği: Binance verisi varsa MEXC üzerine yazmamalı."""
    def sahte_getir(url, timeout=5, user_agent=None):
        if "binance" in url:
            return [{"symbol": "BTCUSDT", "lastPrice": "100000", "volume": "500",
                     "openPrice": "98000", "priceChangePercent": "2.0"}]
        return [{"symbol": "BTCUSDT", "lastPrice": "99999", "volume": "500",
                 "openPrice": "98000", "priceChangePercent": "2.0"}]

    monkeypatch.setattr(motor, "fetch_url_json", sahte_getir)
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: None)

    motor.update_all_prices()
    assert motor.prices["BTCUSDT"]["source"] == "BINANCE"
    assert motor.prices["BTCUSDT"]["price"] == pytest.approx(100000.0)
