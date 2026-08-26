"""
Fiyat Kaynağı Kayıt Defteri testleri (FAZ B++)

Bu dosya, uygulamanın tek bir kişinin portföyüne gömülü olmaktan çıkıp
yapılandırılabilir hale gelmesini koruyan testleri içerir.

Kapsanan gerçek hatalar:
  - Kademe 3'ün sabit ["RDNT", "CATERPILLAR", "CPL"] listesi olması
  - settings.json'daki API adreslerinin hiç okunmaması (dekoratif ayarlar)
  - Fiyat bulunamayınca maliyetin canlı fiyat gibi gösterilmesi
  - Cüzdanda tutulan BNB/SOL/ETH'nin yanlışlıkla DEX havuzu fiyatına düşmesi

TÜM harici HTTP çağrıları mock'lanmıştır — hiçbir test gerçek ağ isteği atmaz.
"""

import pytest

import data_manager
from price_service import SmartPriceDiscoveryEngine, _norm_symbol, _derive_open


@pytest.fixture
def motor():
    """Her test için temiz bir motor örneği (singleton'a dokunmadan)."""
    return SmartPriceDiscoveryEngine()


# ===========================================================================
# SEMBOL NORMALİZASYONU
# ===========================================================================

@pytest.mark.parametrize("girdi,beklenen", [
    ("SCM_USDT", "SCMUSDT"),
    ("btc-usdt", "BTCUSDT"),
    ("ETH/USDT", "ETHUSDT"),
    ("  bnbusdt ", "BNBUSDT"),
])
def test_norm_symbol_ayraclari_temizler(girdi, beklenen):
    assert _norm_symbol(girdi) == beklenen


@pytest.mark.parametrize("girdi,beklenen", [
    ("SCM", "SCM"),
    ("SCMUSDT", "SCM"),
    ("scm_usdt", "SCM"),
    ("BTC/USDT", "BTC"),
])
def test_normalize_symbol_key_usdt_ekini_atar(girdi, beklenen):
    assert data_manager.normalize_symbol_key(girdi) == beklenen


def test_derive_open_yuzde_degisimden_acilis_uretir():
    # %10 artmışsa, açılış = son / 1.10
    assert _derive_open(110.0, 10.0) == pytest.approx(100.0)
    # Değişim yoksa açılış = son
    assert _derive_open(50.0, 0.0) == pytest.approx(50.0)


# ===========================================================================
# KAYNAK TANIMI DOĞRULAMA
# ===========================================================================

def test_gecerli_cex_tanimi_kabul_edilir():
    temiz, hata = data_manager.validate_source_spec(
        {"type": "CEX", "source": "WhiteBIT", "market": "SCM_USDT"}
    )
    assert hata is None
    assert temiz == {"type": "cex", "source": "whitebit", "market": "SCM_USDT"}


def test_cex_tanimi_market_adi_olmadan_reddedilir():
    temiz, hata = data_manager.validate_source_spec({"type": "cex", "source": "whitebit"})
    assert temiz is None
    assert "market" in hata.lower()


def test_dex_tanimi_kontrat_adresini_kabul_eder():
    temiz, hata = data_manager.validate_source_spec(
        {"type": "dex", "contract": "0x8353b92201f19B4812EeE32EFd325f7EDe123718"}
    )
    assert hata is None
    assert temiz["type"] == "dex"
    assert temiz["query"].startswith("0x8353")


def test_manuel_fiyat_sifir_veya_negatif_olamaz():
    for kotu in (0, -1, "abc"):
        temiz, hata = data_manager.validate_source_spec({"type": "manual", "price": kotu})
        assert temiz is None, f"{kotu} kabul edilmemeliydi"
        assert hata


def test_bilinmeyen_kaynak_turu_reddedilir():
    temiz, hata = data_manager.validate_source_spec({"type": "sihir"})
    assert temiz is None
    assert "sihir" in hata


# ===========================================================================
# AYARLARDA KALICILIK
# ===========================================================================

def test_sembol_kaynagi_kaydedilir_ve_okunur():
    ok, hata = data_manager.set_symbol_source("scmusdt", {
        "type": "cex", "source": "whitebit", "market": "SCM_USDT"
    })
    assert ok and hata is None
    # Anahtar normalize edilmiş olmalı: "scmusdt" → "SCM"
    assert data_manager.get_symbol_sources()["SCM"]["market"] == "SCM_USDT"


def test_sembol_kaynagi_silinir():
    data_manager.set_symbol_source("SCM", {"type": "manual", "price": 0.001})
    assert data_manager.delete_symbol_source("SCM") is True
    assert "SCM" not in data_manager.get_symbol_sources()
    # İkinci silme False dönmeli
    assert data_manager.delete_symbol_source("SCM") is False


def test_varsayilan_ayarlarda_hicbir_kullanici_coini_yoktur():
    """
    Regresyon: eski sürümde RDNT/CATERPILLAR/CPL koda gömülüydü.
    Varsayılan ayarlar hiçbir kullanıcıya özel sembol içermemeli.
    """
    assert data_manager.DEFAULT_SETTINGS["symbol_sources"] == {}


def test_tum_kaynaklari_kapatmak_reddedilir():
    ok, hata = data_manager.set_price_sources({
        sid: {"enabled": False, "order": i + 1}
        for i, sid in enumerate(["binance", "mexc", "whitebit", "gateio", "dex"])
    })
    assert ok is False
    assert "en az bir" in hata.lower()


def test_kademe_sirasi_kaydedilir():
    ok, hata = data_manager.set_price_sources({
        "whitebit": {"enabled": True, "order": 1},
        "binance": {"enabled": True, "order": 2},
    })
    assert ok, hata
    kayitli = data_manager.load_settings()["price_sources"]
    assert kayitli["whitebit"]["order"] == 1
    assert kayitli["binance"]["order"] == 2
    # Dokunulmayan kaynaklar korunmalı
    assert "dex" in kayitli


# ===========================================================================
# MOTOR — YAPILANDIRMA OKUMA
# ===========================================================================

def test_motor_ayarlardan_kademe_sirasini_okur(motor):
    """
    Regresyon: settings.json'daki API/kaynak ayarları eskiden hiç
    okunmuyordu — ayarlar ekranı dekoratifti.
    """
    data_manager.set_price_sources({
        "whitebit": {"enabled": True, "order": 1},
        "binance": {"enabled": True, "order": 2},
        "mexc": {"enabled": False, "order": 3},
        "gateio": {"enabled": False, "order": 4},
        "dex": {"enabled": False, "order": 5},
    })
    motor.invalidate_config()
    assert motor.get_active_source_ids() == ["whitebit", "binance"]


def test_motor_ayarlardaki_api_adresini_kullanir(motor, monkeypatch):
    ayarlar = data_manager.load_settings()
    ayarlar["api_urls"]["whitebit_ticker"] = "https://ozel-adres.test/ticker"
    data_manager.save_settings(ayarlar)
    motor.invalidate_config()

    istenen = {}

    def sahte_getir(url, timeout=5):
        istenen["url"] = url
        return {"SCM_USDT": {"last_price": "0.000003", "change": "1.0", "isFrozen": False}}

    monkeypatch.setattr(motor, "fetch_url_json", sahte_getir)
    motor._adapter_whitebit(motor.load_config()["api_urls"])
    assert istenen["url"] == "https://ozel-adres.test/ticker"


def test_bozuk_ayar_dosyasinda_motor_varsayilanlara_duser(motor, monkeypatch):
    """Kural #6: bozuk ayar, fiyat motorunu körleştirmemeli."""
    def patla():
        raise ValueError("bozuk json")
    monkeypatch.setattr(data_manager, "load_settings", patla)
    motor.invalidate_config()
    assert "binance" in motor.get_active_source_ids()


# ===========================================================================
# ADAPTÖRLER
# ===========================================================================

def test_whitebit_adaptoru_market_adini_normalize_eder(motor, monkeypatch):
    monkeypatch.setattr(motor, "fetch_url_json", lambda url, timeout=5: {
        "SCM_USDT": {"last_price": "0.000003499", "change": "-1.05", "isFrozen": False},
        "DONMUS_USDT": {"last_price": "1.0", "change": "0", "isFrozen": True},
    })
    fiyatlar, index = motor._adapter_whitebit({})

    assert "SCMUSDT" in fiyatlar, "SCM_USDT → SCMUSDT olarak normalize edilmeli"
    assert fiyatlar["SCMUSDT"]["source"] == "WHITEBIT"
    assert fiyatlar["SCMUSDT"]["change_pct"] == pytest.approx(-1.05)
    # Açılış fiyatı yüzdeden türetilmeli
    assert fiyatlar["SCMUSDT"]["open_price"] == pytest.approx(0.000003499 / (1 - 0.0105))
    assert "DONMUSUSDT" not in fiyatlar, "Donmuş market alınmamalı"
    assert index[0]["base"] == "SCM"


def test_gateio_adaptoru_currency_pair_okur(motor, monkeypatch):
    monkeypatch.setattr(motor, "fetch_url_json", lambda url, timeout=5: [
        {"currency_pair": "BTC_USDT", "last": "78000", "change_percentage": "2.5"},
        {"currency_pair": "BOS_USDT", "last": "0", "change_percentage": "0"},
    ])
    fiyatlar, _ = motor._adapter_gateio({})
    assert fiyatlar["BTCUSDT"]["price"] == 78000.0
    assert fiyatlar["BTCUSDT"]["source"] == "GATE.IO"
    assert "BOSUSDT" not in fiyatlar, "Fiyatı 0 olan çift alınmamalı"


def test_adaptor_coktugunde_digerleri_calismaya_devam_eder(motor, monkeypatch):
    def sahte_getir(url, timeout=5):
        if "whitebit" in url:
            raise OSError("WhiteBIT kapalı")
        if "binance" in url:
            return [{"symbol": "BTCUSDT", "lastPrice": "78000", "volume": "100",
                     "openPrice": "77000", "priceChangePercent": "1.3"}]
        raise OSError("diğerleri kapalı")

    monkeypatch.setattr(motor, "fetch_url_json", sahte_getir)
    motor.update_all_prices()
    assert motor.prices["BTCUSDT"]["source"] == "BINANCE"


# ===========================================================================
# ZİNCİR ÜSTÜ ADRES BİÇİMLERİ
# ===========================================================================

def _sahte_pair(fiyat="2.309e-09"):
    return {"pairs": [{
        "priceUsd": fiyat,
        "priceChange": {"h24": 1.5},
        "dexId": "pancakeswap",
        "chainId": "bsc",
        "liquidity": {"usd": 84510.0},
        "baseToken": {"symbol": "CPL", "name": "Caterpillar", "address": "0xD0ed8f9C"},
        "quoteToken": {"symbol": "WBNB"},
        "pairAddress": "0x32B1A5CA",
    }]}


def test_havuz_adresi_arama_bos_donunce_ozel_uctan_cozulur(motor, monkeypatch):
    """
    Gerçek kullanılabilirlik tuzağı: DexScreener'ın arama ucu yalnızca TOKEN
    kontratıyla eşleşir. Kullanıcının kopyalayacağı adres ise genellikle
    DexScreener URL'sindeki HAVUZ adresidir; bu durumda arama boş döner.
    """
    cagrilan = []

    def sahte_getir(url, timeout=5):
        cagrilan.append(url)
        if "/dex/search" in url:
            return {"pairs": []}
        if "/dex/pairs/bsc/" in url:
            return _sahte_pair()
        return {"pairs": []}

    monkeypatch.setattr(motor, "fetch_url_json", sahte_getir)
    sonuc = motor.fetch_dex_screener("0x32B1A5CAc697B13f6C413704b104f5b05a5BDC20")

    assert sonuc is not None, "Havuz adresi çözülebilmeli"
    assert sonuc["price"] == pytest.approx(2.309e-09)
    assert sonuc["chain_id"] == "bsc"
    assert any("/dex/pairs/" in u for u in cagrilan), "Havuz uç noktası denenmeliydi"


def test_adres_olmayan_sorgu_icin_havuz_ucu_denenmez(motor, monkeypatch):
    cagrilan = []

    def sahte_getir(url, timeout=5):
        cagrilan.append(url)
        return {"pairs": []}

    monkeypatch.setattr(motor, "fetch_url_json", sahte_getir)
    assert motor.fetch_dex_screener("CPL") is None
    assert not any("/dex/pairs/" in u for u in cagrilan), \
        "Sembol için havuz uç noktası denenmemeli (gereksiz istek)"


@pytest.mark.parametrize("adres,beklenen", [
    ("0x32B1A5CAc697B13f6C413704b104f5b05a5BDC20", True),
    ("8XNw4ajTywKT85DjLtRNL87rxeGcp7sTYmnnbk4kxrCX", True),
    ("CPL", False),
    ("0x123", False),
])
def test_adres_bicimi_tanima(adres, beklenen):
    assert SmartPriceDiscoveryEngine._looks_like_address(adres) is beklenen


def test_pair_to_price_sifir_fiyati_reddeder(motor):
    assert motor._pair_to_price({"priceUsd": "0"}) is None


# ===========================================================================
# KADEME ÖNCELİĞİ VE ÖZEL TANIMLAR
# ===========================================================================

def _sadece_binance_ve_whitebit(monkeypatch, motor, binance, whitebit):
    def sahte_getir(url, timeout=5):
        if "binance" in url:
            return binance
        if "whitebit" in url:
            return whitebit
        raise OSError("bu testte kapalı")
    monkeypatch.setattr(motor, "fetch_url_json", sahte_getir)


def test_ilk_bulan_kademe_kazanir(motor, monkeypatch):
    _sadece_binance_ve_whitebit(
        monkeypatch, motor,
        binance=[{"symbol": "BTCUSDT", "lastPrice": "78000", "volume": "100",
                  "openPrice": "77000", "priceChangePercent": "1.3"}],
        whitebit={"BTC_USDT": {"last_price": "999", "change": "0", "isFrozen": False}},
    )
    motor.update_all_prices()
    assert motor.prices["BTCUSDT"]["source"] == "BINANCE"


def test_kullanici_sirasi_kademe_onceligini_degistirir(motor, monkeypatch):
    data_manager.set_price_sources({
        "whitebit": {"enabled": True, "order": 1},
        "binance": {"enabled": True, "order": 2},
        "mexc": {"enabled": False, "order": 3},
        "gateio": {"enabled": False, "order": 4},
        "dex": {"enabled": False, "order": 5},
    })
    motor.invalidate_config()
    _sadece_binance_ve_whitebit(
        monkeypatch, motor,
        binance=[{"symbol": "BTCUSDT", "lastPrice": "78000", "volume": "100",
                  "openPrice": "77000", "priceChangePercent": "1.3"}],
        whitebit={"BTC_USDT": {"last_price": "999", "change": "0", "isFrozen": False}},
    )
    motor.update_all_prices()
    assert motor.prices["BTCUSDT"]["source"] == "WHITEBIT"


def test_sembol_tanimi_kademe_sonucunu_ezer(motor, monkeypatch):
    """
    Gerçek durum: RDNT hem Binance'te (0.00328) hem zincir üstünde (0.000407)
    var ve kullanıcı zincir üstü fiyatı istiyor. Eskiden bu, koda gömülü
    `"RDNT" not in sym` kontrolüyle sağlanıyordu.
    """
    data_manager.set_symbol_source("RDNT", {"type": "dex", "query": "RDNT"})
    motor.invalidate_config()

    monkeypatch.setattr(motor, "fetch_url_json", lambda url, timeout=5: (
        [{"symbol": "RDNTUSDT", "lastPrice": "0.00328", "volume": "1000",
          "openPrice": "0.0033", "priceChangePercent": "-1.0"}]
        if "binance" in url else (_ for _ in ()).throw(OSError("kapalı"))
    ))
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: {
        "price": 0.000407, "open_price": 0.0004, "change_pct": 1.0,
        "source": "DEX (BSC Pancakeswap)", "is_dex": True, "base_symbol": "RDNT",
    })

    motor.update_all_prices()
    assert motor.prices["RDNTUSDT"]["price"] == pytest.approx(0.000407)
    assert motor.prices["RDNTUSDT"]["is_dex"] is True


def test_sembolle_bulunan_dex_fiyati_isaretlenir(motor, monkeypatch, kayitli_portfoy):
    """
    Gerçek risk: sembol adları zincirler arasında benzersiz değildir.
    Kullanıcının SCM'i Ethereum'daki Scamfari; sembol araması ise Solana'daki
    "Social Capital Markets" tokenını buluyor ve fiyat makul göründüğü için
    hata fark edilmiyor. Eşleşmenin nasıl kurulduğu işaretlenmeli.
    """
    monkeypatch.setattr(motor, "fetch_url_json", lambda url, timeout=5: [])
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: {
        "price": 3.76e-06, "open_price": 3.7e-06, "change_pct": 1.0,
        "source": "DEX (SOLANA Pumpswap)", "is_dex": True, "base_symbol": "SCM",
    })
    motor.update_all_prices()
    assert motor.prices["CPLUSDT"]["match_by"] == "symbol"


def test_adresle_tanimlanan_kaynak_kesin_isaretlenir(motor, monkeypatch):
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: {
        "price": 2.3e-09, "source": "DEX (BSC Pancakeswap)", "is_dex": True,
    })
    kesin = motor.resolve_symbol_source(
        {"type": "dex", "query": "0x32B1A5CAc697B13f6C413704b104f5b05a5BDC20"}
    )
    belirsiz = motor.resolve_symbol_source({"type": "dex", "query": "CPL"})
    assert kesin["match_by"] == "address"
    assert belirsiz["match_by"] == "symbol"


def test_borsadan_gelen_fiyat_sembol_uyarisi_tasimaz(kayitli_portfoy):
    fiyatlar = {"BTCUSDT": {"price": 100000.0, "open_price": 98000.0,
                            "change_pct": 2.0, "source": "BINANCE"}}
    metrikler = data_manager.calculate_portfolio_metrics(kayitli_portfoy, fiyatlar)
    btc = next(c for c in metrikler["consolidated_coins"] if c["display_name"] == "BTCUSDT")
    assert btc["price_match_by"] is None


def test_manuel_kaynak_sabit_fiyat_verir(motor):
    sonuc = motor.resolve_symbol_source({"type": "manual", "price": 0.00042}, symbol="XYZ")
    assert sonuc["price"] == pytest.approx(0.00042)
    assert sonuc["is_manual"] is True
    assert sonuc["change_pct"] == 0.0


def test_gecersiz_tanim_none_doner(motor):
    assert motor.resolve_symbol_source({"type": "cex", "source": "yokboyleborsa",
                                        "market": "X_USDT"}) is None
    assert motor.resolve_symbol_source(None) is None


# ===========================================================================
# İZLEME LİSTESİ — SABİT LİSTE YOK
# ===========================================================================

def test_izleme_listesi_portfoyden_turetilir(motor, kayitli_portfoy):
    """Regresyon: eskiden ["RDNT", "CATERPILLAR", "CPL"] sabit listesiydi."""
    liste = motor.get_watchlist(force=True)
    assert "CPLUSDT" in liste
    assert "BTCUSDT" in liste
    assert "CATERPILLAR" not in liste, "Sabit liste kalıntısı olmamalı"


def test_borsada_bulunan_ciplak_sembol_dex_taramasina_dusmez(motor, monkeypatch, kayitli_portfoy):
    """
    Gerçek hata: Portföyde "BNB" gibi çıplak sembolle kayıtlı cüzdan
    pozisyonları, borsa adaptörü fiyatı "BNBUSDT" olarak yazdığı için
    "bulunamadı" sayılıyor ve yanlışlıkla bir DEX havuzu fiyatına
    (Solana Raydium BNB) düşüyordu.
    """
    portfoy = data_manager.load_portfolio()
    portfoy["transactions"].append({
        "id": 999, "date": "2026-04-01", "coin": "BNB", "exchange": "DEX",
        "qty": 0.05, "cost": 700.0, "status": "Aktif", "notes": "", "category": "Majör / L1"
    })
    data_manager.save_portfolio(portfoy)

    dex_cagrilari = []
    monkeypatch.setattr(motor, "fetch_dex_screener",
                        lambda q: dex_cagrilari.append(q) or None)
    monkeypatch.setattr(motor, "fetch_url_json", lambda url, timeout=5: (
        [{"symbol": "BNBUSDT", "lastPrice": "701.56", "volume": "5000",
          "openPrice": "700", "priceChangePercent": "0.2"}]
        if "binance" in url else (_ for _ in ()).throw(OSError("kapalı"))
    ))

    motor.update_all_prices()

    assert "BNB" not in dex_cagrilari, "Binance'te bulunan BNB için DEX sorgusu yapılmamalı"
    assert motor.prices["BNBUSDT"]["source"] == "BINANCE"


def test_hicbir_kaynakta_bulunamayan_sembol_kaynak_yok_doner(motor, monkeypatch):
    monkeypatch.setattr(motor, "fetch_url_json", lambda url, timeout=5: [])
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda q: None)

    sonuc = motor.get_price_for_symbol("YOKBOYLECOIN")
    assert sonuc["no_source"] is True
    assert sonuc["price"] == 0.0


# ===========================================================================
# PORTFÖY HESABI — MALİYET ARTIK SESSİZCE FİYAT SAYILMIYOR
# ===========================================================================

def test_kaynagi_olmayan_pozisyon_isaretlenir(kayitli_portfoy):
    """
    Gerçek hata (SCM): fiyat bulunamayınca maliyet canlı fiyat gibi
    gösteriliyordu; pozisyon kalıcı olarak "%0.00 başabaş" görünüyordu.
    Değerleme hâlâ maliyet üzerinden yapılır (toplam kasa çökmesin) ama
    artık `no_source` bayrağıyla etiketlenir.
    """
    metrikler = data_manager.calculate_portfolio_metrics(kayitli_portfoy, {})
    coinler = {c["display_name"]: c for c in metrikler["consolidated_coins"]}

    btc = coinler["BTCUSDT"]
    assert btc["no_source"] is True
    assert btc["live_price"] == pytest.approx(btc["avg_cost"])
    assert metrikler["kpis"]["no_source_count"] > 0


def test_kaynagi_olan_pozisyon_isaretlenmez(kayitli_portfoy):
    fiyatlar = {"BTCUSDT": {"price": 100000.0, "open_price": 98000.0,
                            "change_pct": 2.0, "source": "BINANCE"}}
    metrikler = data_manager.calculate_portfolio_metrics(kayitli_portfoy, fiyatlar)
    btc = next(c for c in metrikler["consolidated_coins"] if c["display_name"] == "BTCUSDT")

    assert btc["no_source"] is False
    assert btc["live_price"] == 100000.0


def test_dex_isareti_kayittaki_borsadan_degil_fiyat_kaynagindan_gelir(kayitli_portfoy):
    """
    Gerçek hata: borsası "DEX" yazan her pozisyon zincir üstü sayılıyordu.
    Cüzdanda tutulan BNB/SOL/ETH de öyle işaretlenip DexScreener grafiğine
    yönlendiriliyordu. Artık ölçüt, fiyatın gerçekte nereden geldiğidir.
    """
    fiyatlar = {"CPLUSDT": {"price": 2.3e-09, "open_price": 2.3e-09, "change_pct": 0.0,
                            "source": "DEX (BSC Pancakeswap)", "is_dex": True,
                            "pair_address": "0xabc", "chain_id": "bsc"}}
    metrikler = data_manager.calculate_portfolio_metrics(kayitli_portfoy, fiyatlar)
    coinler = {c["display_name"]: c for c in metrikler["consolidated_coins"]}

    assert coinler["CPLUSDT"]["is_dex"] is True
    assert coinler["CPLUSDT"]["pair_address"] == "0xabc"
    # Borsası DEX ama fiyatı gelmeyen bir pozisyon zincir üstü sayılmamalı
    assert coinler["BTCUSDT"]["is_dex"] is False


def test_hicbir_yerde_gomulu_kontrat_adresi_kalmadi(kayitli_portfoy):
    """Regresyon: CPL'in kontrat adresi data_manager'a üç kez gömülüydü."""
    metrikler = data_manager.calculate_portfolio_metrics(kayitli_portfoy, {})
    for coin in metrikler["consolidated_coins"]:
        for alan in ("dex_url", "dex_embed_url", "dextools_url"):
            deger = coin.get(alan)
            assert not deger or "0x32b1a5cac697b13f6c413704b104f5b05a5bdc20" not in deger


# ===========================================================================
# AYAR KAYDETME — BÖLÜM SİLME REGRESYONU
# ===========================================================================
# Gerçek veri kaybı: `POST /api/settings` gelen gövdeyi dosyanın TAMAMININ
# yerine yazıyordu. Arayüz yalnızca api_urls/api_keys/preferences gönderdiği
# için, kullanıcı "Kaydet"e her bastığında `security` bölümü (PIN hash'i,
# salt, kurtarma anahtarı) ve fiyat kaynağı tanımları siliniyordu.
# PIN koruması sessizce kapanıyordu.

def test_kismi_kaydetme_diger_bolumleri_silmez():
    data_manager.set_symbol_source("SCM", {"type": "manual", "price": 0.001})
    data_manager.set_pin("3072")

    birlesik = data_manager.merge_settings({
        "api_urls": {"binance_ticker": "https://yeni-adres.test"}
    })
    data_manager.save_settings(birlesik)

    kayitli = data_manager.load_settings()
    assert kayitli["api_urls"]["binance_ticker"] == "https://yeni-adres.test"
    assert kayitli["security"]["pin_enabled"] is True, "PIN koruması silinmemeli"
    assert kayitli["security"]["pin_hash"], "PIN hash'i silinmemeli"
    assert kayitli["symbol_sources"]["SCM"]["type"] == "manual"
    assert kayitli["price_sources"], "Kademe defteri silinmemeli"


def test_kismi_kaydetme_ayni_bolumdeki_diger_alanlari_korur():
    birlesik = data_manager.merge_settings({"api_urls": {"mexc_ticker": "https://x.test"}})
    assert birlesik["api_urls"]["mexc_ticker"] == "https://x.test"
    assert birlesik["api_urls"]["binance_ticker"], "Aynı bölümdeki diğer alan korunmalı"


def test_ayar_kaydetme_ucu_pini_kapatmaz(client):
    """Uçtan uca: arayüzün gönderdiği gövde PIN'i düşürmemeli."""
    data_manager.set_pin("3072")
    data_manager.set_symbol_source("RDNT", {"type": "dex", "query": "RDNT"})

    r = client.post("/api/settings", json={
        "api_urls": {"binance_ticker": "https://api.binance.com/api/v3/ticker/24hr"},
        "api_keys": {"gemini_api_key": ""},
        "preferences": {"refresh_interval_sec": 3.5},
    })
    assert r.status_code == 200

    kayitli = data_manager.load_settings()
    assert kayitli["security"]["pin_enabled"] is True
    assert kayitli["symbol_sources"]["RDNT"]["type"] == "dex"


def test_merge_settings_dict_olmayan_girdiyi_yok_sayar():
    mevcut = data_manager.load_settings()
    assert data_manager.merge_settings(None) == mevcut
    assert data_manager.merge_settings("metin") == mevcut


# ===========================================================================
# API UÇLARI
# ===========================================================================

def test_kaynak_listesi_ucu(client):
    r = client.get("/api/price-sources")
    assert r.status_code == 200
    veri = r.json()
    kimlikler = [s["id"] for s in veri["registry"]]
    assert "binance" in kimlikler and "whitebit" in kimlikler
    assert veri["symbol_sources"] == {}


def test_kademe_kaydetme_ucu(client):
    r = client.post("/api/price-sources", json={"registry": {
        "whitebit": {"enabled": True, "order": 1},
        "binance": {"enabled": True, "order": 2},
    }})
    assert r.status_code == 200
    sirali = [s["id"] for s in r.json()["registry"]]
    assert sirali[0] == "whitebit"


def test_tum_kademeleri_kapatan_istek_400_doner(client):
    r = client.post("/api/price-sources", json={"registry": {
        sid: {"enabled": False, "order": 1}
        for sid in ["binance", "mexc", "whitebit", "gateio", "dex"]
    }})
    assert r.status_code == 400


def test_sembol_kaynagi_kaydetme_ve_silme_ucu(client):
    r = client.post("/api/symbol-sources", json={
        "symbol": "SCM",
        "source": {"type": "manual", "price": 0.0000035}
    })
    assert r.status_code == 200
    assert r.json()["symbol_sources"]["SCM"]["type"] == "manual"

    r2 = client.delete("/api/symbol-sources/SCM")
    assert r2.status_code == 200
    assert r2.json()["symbol_sources"] == {}


def test_olmayan_sembol_kaynagini_silmek_404_doner(client):
    assert client.delete("/api/symbol-sources/YOKBOYLE").status_code == 404


def test_gecersiz_sembol_kaynagi_400_doner(client):
    r = client.post("/api/symbol-sources", json={
        "symbol": "SCM", "source": {"type": "cex", "source": "whitebit"}
    })
    assert r.status_code == 400


def test_onizleme_ucu_kaydetmeden_dener(client):
    r = client.post("/api/symbol-sources/preview", json={
        "symbol": "XYZ", "source": {"type": "manual", "price": 0.5}
    })
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert r.json()["price"] == 0.5
    # Önizleme kaydetmemeli
    assert client.get("/api/price-sources").json()["symbol_sources"] == {}


def test_onizleme_sonuc_bulamazsa_basarisiz_doner(client, monkeypatch):
    import price_service as ps
    monkeypatch.setattr(ps.price_service, "fetch_dex_screener", lambda q: None)
    r = client.post("/api/symbol-sources/preview", json={
        "symbol": "YOKBOYLE", "source": {"type": "dex", "query": "0xyok"}
    })
    assert r.status_code == 200
    assert r.json()["success"] is False
