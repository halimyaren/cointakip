"""
FAZ M1 — PİYASA VERİSİ TESTLERİ

╔══════════════════════════════════════════════════════════════════════════╗
║  HİÇBİR TEST AĞA ÇIKMAZ.                                                 ║
║                                                                          ║
║  Buradaki tüm örnekler 5 Eylül 2026'da gerçek uçlardan kaydedilen        ║
║  yanıtların kısaltılmış hâlidir. `TestAgaCikilmiyor` bunu kanıtlar:      ║
║  urlopen monkeypatch'lenip patlaması sağlanır ve testler yine geçer.     ║
╚══════════════════════════════════════════════════════════════════════════╝

Test edilen davranışlar, tasarım kararlarının sırasıyla:
  1. Hüküm üretilmez, sayı üretilir  (ölüm kesişimi vakası)
  2. Dominans kaynağı her kayda yazılır; kaynak değişince fark alınmaz
  3. Bayat veri yaşıyla gider, çok eski veri hiç gitmez
  4. Genişlik uydurulmaz — veri yoksa hata yükselir
  5. Anahtarsız mod görünür kılınır
"""

import json
import os
import sys
import time

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(PROJECT_ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import archive                                  # noqa: E402
import market_service as ms                     # noqa: E402
from market_service import MarketDataService    # noqa: E402


# =====================================================================
# GERÇEK YANIT ÖRNEKLERİ (5 Eylül 2026, kısaltılmış)
# =====================================================================

def klines_uret(kapanislar, son_kapanis_ms=1788652799999):
    """Binance klines biçiminde dizi üretir. Yalnızca [4] ve [6] kullanılıyor."""
    out = []
    gun_ms = 86400000
    n = len(kapanislar)
    for i, k in enumerate(kapanislar):
        kapanis_ts = son_kapanis_ms - (n - 1 - i) * gun_ms
        out.append([
            kapanis_ts - gun_ms + 1, f"{k:.8f}", f"{k * 1.02:.8f}",
            f"{k * 0.98:.8f}", f"{k:.8f}", "14130.639", kapanis_ts,
            "1101387276.65", 3662805, "7128.14", "555981558.22", "0",
        ])
    return out


# Ölçüm gününün gerçek şekli: fiyat ortalamaların ÜSTÜNDE ama SMA50 SMA200'ün
# ALTINDA. Derin bir düşüşten sonra hızlı toparlanma bu tabloyu üretir.
def olum_kesisimi_klines():
    # 200 gün: önce yüksek plato, sonra derin düşüş, sonra sert toparlanma.
    kapanislar = []
    kapanislar += [95000.0] * 60      # eski yüksek plato -> SMA200'ü yukarı çeker
    kapanislar += [60000.0] * 110     # uzun düşük dönem -> SMA50'yi aşağı çeker
    kapanislar += [79754.0] * 30      # son toparlanma
    return klines_uret(kapanislar)


FNG_ORNEK = {
    "name": "Fear and Greed Index",
    "data": [
        {"value": "73", "value_classification": "Greed",
         "timestamp": "1788566400", "time_until_update": "14787"},
        {"value": "74", "value_classification": "Greed", "timestamp": "1788480000"},
        {"value": "65", "value_classification": "Greed", "timestamp": "1788393600"},
        {"value": "63", "value_classification": "Greed", "timestamp": "1788307200"},
        {"value": "69", "value_classification": "Greed", "timestamp": "1788220800"},
        {"value": "62", "value_classification": "Greed", "timestamp": "1788134400"},
        {"value": "69", "value_classification": "Greed", "timestamp": "1788048000"},
        {"value": "68", "value_classification": "Greed", "timestamp": "1787961600"},
    ],
    "metadata": {"error": None},
}

GLOBAL_ORNEK = {
    "data": {
        "active_cryptocurrencies": 19612,
        "total_market_cap": {"usd": 2715900000000.0, "btc": 34127971.78},
        "total_volume": {"usd": 59900000000.0},
        "market_cap_percentage": {"btc": 58.836891948902235, "eth": 11.095201375122663},
        "market_cap_change_percentage_24h_usd": -1.8162479628582893,
        "updated_at": 1788638607,
    }
}

# Gerçek ölçümden (5 Eylül 2026): 180 likit çiftin 146'sı artıda, BTC -0.03%,
# BTC'yi geçen 146. BTC'nin kendisi eksideki 34'ün içindedir — kurguda onu
# ayrıca saymamak gerekiyor.
def genislik_girdisi():
    satirlar = [{"symbol": "BTCUSDT", "change_pct": -0.03, "quote_volume": 1.2e9}]
    for i in range(146):
        satirlar.append({"symbol": f"A{i}USDT", "change_pct": 2.77,
                         "quote_volume": 5e6})
    for i in range(33):
        satirlar.append({"symbol": f"B{i}USDT", "change_pct": -1.5,
                         "quote_volume": 5e6})
    # Hacimsiz çöp çiftler — süzgeç bunları elemeli.
    for i in range(500):
        satirlar.append({"symbol": f"Z{i}USDT", "change_pct": 400.0,
                         "quote_volume": 12.0})
    return satirlar


class SahteFiyatMotoru:
    def __init__(self, girdi=None):
        self._girdi = girdi if girdi is not None else genislik_girdisi()

    def get_breadth_input(self):
        return list(self._girdi)


@pytest.fixture
def servis():
    s = MarketDataService(price_engine=SahteFiyatMotoru())
    return s


# =====================================================================
# 1. HÜKÜM DEĞİL SAYI
# =====================================================================
class TestHukumUretilmez:

    def test_olum_kesisimi_vakasi_etiketlenmez_sayilar_verilir(self):
        """Bu testin varlık sebebi bir gözlemdir, bir kural değil.

        Ölçüm gününde SMA50 < SMA200 idi — kitaba göre "ölüm kesişimi",
        yani düşüş sinyali. Ama fiyat her iki ortalamanın da üstündeydi.
        Etiket gerçeğin tersini söylüyordu. Bu yüzden modül sayıyı verir,
        hükmü vermez.
        """
        trend = MarketDataService._klines_to_trend(olum_kesisimi_klines(), "BTCUSDT")

        # Vakanın gerçekten kurulduğunu doğrula:
        assert trend["sma50_above_sma200"] is False, "kurgu ölüm kesişimini üretmeli"
        assert trend["pct_vs_sma50"] > 0, "fiyat SMA50'nin üstünde olmalı"
        assert trend["pct_vs_sma200"] > 0, "fiyat SMA200'ün üstünde olmalı"

        # ASIL İDDİA: hiçbir yerde hüküm/etiket yok.
        metin = json.dumps(trend, ensure_ascii=False).lower()
        for yasak in ("olum kesisimi", "ölüm kesişimi", "death cross",
                      "golden cross", "altin kesisim", "boga", "boğa",
                      "ayi piyasasi", "bullish", "bearish", "al ", "sat "):
            assert yasak not in metin, f"trend bloğunda hüküm sızmış: {yasak!r}"

    def test_trend_beklenen_alanlari_uretir(self):
        trend = MarketDataService._klines_to_trend(
            klines_uret([100.0] * 199 + [110.0]), "BTCUSDT")
        for alan in ("price", "change_7d_pct", "change_30d_pct", "sma50", "sma200",
                     "pct_vs_sma50", "pct_vs_sma200", "range_low", "range_high",
                     "pct_from_high", "daily_volatility_pct_30d", "candle_close_ts"):
            assert alan in trend, f"eksik alan: {alan}"
        assert trend["price"] == 110.0
        assert trend["range_high"] == 110.0
        assert trend["source"] == "BINANCE"

    def test_yetersiz_veride_sma200_uydurulmaz(self):
        """60 günlük veriyle SMA200 hesaplamak, yanlış sayıyı doğru gibi sunmaktır."""
        trend = MarketDataService._klines_to_trend(klines_uret([100.0] * 60), "BTCUSDT")
        assert trend["sma50"] is not None
        assert trend["sma200"] is None
        assert trend["pct_vs_sma200"] is None
        assert trend["sma50_above_sma200"] is None

    def test_bos_veya_bozuk_klines_hata_yukseltir(self):
        with pytest.raises(ValueError):
            MarketDataService._klines_to_trend([], "BTCUSDT")
        with pytest.raises(ValueError):
            MarketDataService._klines_to_trend({"hata": "yok"}, "BTCUSDT")

    def test_fear_greed_etiketi_bizim_degil_saglayicinin(self):
        fng = MarketDataService._fng_to_dict(FNG_ORNEK)
        assert fng["value"] == 73
        assert fng["classification"] == "Greed"
        assert fng["source"] == "alternative.me"
        # 7 gün önceki değer 68 -> fark +5
        assert fng["change_7d"] == 5
        assert fng["change_1d"] == -1
        assert len(fng["history"]) == 8

    def test_fng_dominans_bagimliligi_modele_soylenir(self):
        """F&G metodolojisinde BTC dominansı %10 ağırlıkla var; model bunları
        iki bağımsız teyit sanmamalı."""
        fng = MarketDataService._fng_to_dict(FNG_ORNEK)
        assert "dominans" in fng["note"].lower()

    def test_fng_kaynak_hata_bildirirse_yukseltilir(self):
        bozuk = {"data": [], "metadata": {"error": "quota exceeded"}}
        with pytest.raises(ValueError):
            MarketDataService._fng_to_dict(bozuk)


# =====================================================================
# 2. DOMİNANS BİR KONVANSİYONDUR
# =====================================================================
class TestDominansKonvansiyonu:

    def test_kaynak_adi_her_zaman_yazilir(self):
        g = MarketDataService._global_to_dict(GLOBAL_ORNEK)
        assert g["source"] == "CoinGecko"
        assert g["btc_dominance_pct"] == 58.84

    def test_konvansiyon_uyarisi_modele_gider(self):
        """Kullanıcı başka bir yerde 56.52 görebilir; sayı yanlış değil,
        tanım farklı. Model bunu bilmeli."""
        g = MarketDataService._global_to_dict(GLOBAL_ORNEK)
        assert "convention_note" in g
        # Ölçülen üç değer de notta geçmeli — iddia somut olmalı.
        for sayi in ("58.84", "56.52", "59.33"):
            assert sayi in g["convention_note"]

    def test_btc_disi_piyasa_degeri_turetilir(self):
        """Ham toplam mcap büyük ölçüde BTC+ETH'in yeniden ifadesi; asıl
        bilgi BTC dışı büyüklük."""
        g = MarketDataService._global_to_dict(GLOBAL_ORNEK)
        beklenen = 2715900000000.0 * (1 - 58.84 / 100.0)
        assert abs(g["market_cap_excl_btc_usd"] - beklenen) < 1e6
        assert g["market_cap_excl_btc_usd"] < g["total_market_cap_usd"]

    def test_eksik_alanlarda_hata_yukseltilir(self):
        with pytest.raises(ValueError):
            MarketDataService._global_to_dict({"data": {"total_market_cap": {"usd": 1}}})
        with pytest.raises(ValueError):
            MarketDataService._global_to_dict({"beklenmeyen": 1})


# =====================================================================
# 3. TAZELİK
# =====================================================================
class TestTazelik:

    def test_taze_veri_fresh_isaretlenir(self, servis):
        servis._cache["btc_trend"] = {
            "data": {"price": 100.0}, "fetched_at": time.time()}
        s = servis.get_snapshot()
        assert s["available"] is True
        assert s["blocks"]["btc_trend"]["freshness"] == ms.TAZE
        assert s["blocks"]["btc_trend"]["age_seconds"] < 5

    def test_bayat_veri_yasiyla_birlikte_gider(self, servis):
        # btc_trend eşiği: 2 saat bayat, 12 saat at.
        servis._cache["btc_trend"] = {
            "data": {"price": 100.0}, "fetched_at": time.time() - 10800}  # 3 saat
        s = servis.get_snapshot()
        blok = s["blocks"]["btc_trend"]
        assert blok["freshness"] == ms.BAYAT
        assert blok["age_seconds"] >= 10800
        assert "saat" in blok["age_human"]

    def test_cok_eski_veri_hic_verilmez(self, servis):
        servis._cache["btc_trend"] = {
            "data": {"price": 100.0}, "fetched_at": time.time() - 200000}  # ~55 saat
        s = servis.get_snapshot()
        assert "btc_trend" not in s["blocks"]
        assert "btc_trend" in s["dropped_as_too_old"]
        assert s["available"] is False

    def test_fear_greed_esigi_fiyattan_gevsek(self, servis):
        """F&G günde bir güncellenir; 30 saatlik değer HÂLÂ günceldir.
        Ona fiyat eşiği uygulamak sağlam veriyi boşuna atmak olur."""
        yas = time.time() - 108000        # 30 saat
        servis._cache["fear_greed"] = {"data": {"value": 73}, "fetched_at": yas}
        servis._cache["btc_trend"] = {"data": {"price": 100.0}, "fetched_at": yas}
        s = servis.get_snapshot()
        assert "fear_greed" in s["blocks"], "30 saatlik F&G atılmamalı"
        assert s["blocks"]["fear_greed"]["freshness"] == ms.TAZE
        assert "btc_trend" not in s["blocks"], "30 saatlik fiyat verisi atılmalı"

    def test_bir_kaynagin_bayatligi_digerlerini_etkilemez(self, servis):
        servis._cache["btc_trend"] = {"data": {"price": 1.0}, "fetched_at": time.time()}
        servis._cache["global"] = {"data": {"btc_dominance_pct": 58.8},
                                   "fetched_at": time.time() - 200000}
        s = servis.get_snapshot()
        assert "btc_trend" in s["blocks"]
        assert "global" not in s["blocks"]
        assert s["available"] is True


# =====================================================================
# 4. GENİŞLİK — SIFIR ÇAĞRI, AMA UYDURMA YOK
# =====================================================================
class TestGenislik:

    def test_gercek_olcum_yeniden_uretilir(self):
        g = MarketDataService._breadth_to_dict(genislik_girdisi())
        assert g["liquid_pairs"] == 180
        assert g["advancing"] == 146
        assert g["declining"] == 34
        assert g["advancing_pct"] == 81.1
        assert g["btc_change_24h_pct"] == -0.03

    def test_dusuk_hacimli_cop_ciftler_elenir(self):
        """500 adet %400 değişimli çöp çift medyanı mahvederdi."""
        g = MarketDataService._breadth_to_dict(genislik_girdisi())
        assert g["median_change_24h_pct"] < 10, "çöp çiftler medyanı bozmuş"
        assert g["liquid_pairs"] == 180, "hacim süzgeci uygulanmamış"

    def test_btcyi_gecen_orani_hesaplanir(self):
        g = MarketDataService._breadth_to_dict(genislik_girdisi())
        # BTC -0.03; 146 çift +2.77, 34 çift -1.5 -> 146 tanesi BTC'yi geçiyor
        assert g["outperforming_btc_pct"] == round(100 * 146 / 180, 1)

    def test_veri_yoksa_uydurulmaz(self):
        with pytest.raises(ValueError):
            MarketDataService._breadth_to_dict([])

    def test_yetersiz_ornekle_yuzde_uretilmez(self):
        """20 çiftin altında 'piyasanın %X'i artıda' demek yanıltıcıdır."""
        az = [{"symbol": "AUSDT", "change_pct": 5.0, "quote_volume": 5e6}] * 5
        with pytest.raises(ValueError):
            MarketDataService._breadth_to_dict(az)

    def test_binance_kapaliysa_genislik_hata_verir(self):
        servis = MarketDataService(price_engine=SahteFiyatMotoru(girdi=[]))
        with pytest.raises(ValueError):
            servis.fetch_breadth()

    def test_fiyat_motoru_yoksa_hata_verir(self):
        servis = MarketDataService(price_engine=None)
        with pytest.raises(ValueError):
            servis.fetch_breadth()


# =====================================================================
# 5. ANAHTAR POLİTİKASI — anahtarsız mod GÖRÜNÜR olmalı
# =====================================================================
class TestAnahtarPolitikasi:

    def test_anahtarsiz_mod_gorunur_kilinir(self, servis, monkeypatch):
        monkeypatch.setattr(servis, "_coingecko_anahtari", lambda: "")
        satirlar = {r["id"]: r for r in servis.describe_sources()}
        glb = satirlar["global"]
        assert glb["auth_mode"] == "keyless"
        assert glb["auth_is_preferred"] is False
        assert "anahtar" in glb["auth_hint"].lower()

    def test_anahtarli_mod_tercih_edilen_olarak_isaretlenir(self, servis, monkeypatch):
        monkeypatch.setattr(servis, "_coingecko_anahtari", lambda: "CG-test")
        satirlar = {r["id"]: r for r in servis.describe_sources()}
        assert satirlar["global"]["auth_mode"] == "demo_key"
        assert satirlar["global"]["auth_is_preferred"] is True

    def test_anahtar_varsa_baslik_gonderilir_taban_adres_degismez(self, servis, monkeypatch):
        """Demo anahtarı taban adresi DEĞİŞTİRMEZ; yalnızca başlık ekler."""
        gorulen = {}

        def sahte_getir(url, timeout, headers=None):
            gorulen["url"] = url
            gorulen["headers"] = headers or {}
            return GLOBAL_ORNEK

        monkeypatch.setattr(servis, "_getir", sahte_getir)
        monkeypatch.setattr(servis, "_coingecko_anahtari", lambda: "CG-abc123")
        monkeypatch.setattr(servis, "_url", lambda k: "https://api.coingecko.com/api/v3/global")

        out = servis.fetch_global()
        assert gorulen["url"].startswith("https://api.coingecko.com")
        assert gorulen["headers"].get("x-cg-demo-api-key") == "CG-abc123"
        assert out["auth_mode"] == "demo_key"

    def test_anahtarsizken_baslik_gonderilmez(self, servis, monkeypatch):
        gorulen = {}

        def sahte_getir(url, timeout, headers=None):
            gorulen["headers"] = headers
            return GLOBAL_ORNEK

        monkeypatch.setattr(servis, "_getir", sahte_getir)
        monkeypatch.setattr(servis, "_coingecko_anahtari", lambda: "")
        monkeypatch.setattr(servis, "_url", lambda k: "https://api.coingecko.com/api/v3/global")

        out = servis.fetch_global()
        assert not gorulen["headers"]
        assert out["auth_mode"] == "keyless"

    def test_anahtar_ayarlarda_obfuscate_edilenler_listesinde(self):
        import data_manager
        assert "coingecko_api_key" in data_manager._OBFUSCATED_KEYS

    def test_anahtar_varsayilan_ayarlarda_bos_tanimli(self):
        import data_manager
        assert data_manager.DEFAULT_SETTINGS["api_keys"]["coingecko_api_key"] == ""


# =====================================================================
# 6. YENİLEME DAVRANIŞI
# =====================================================================
class TestYenileme:

    def test_bir_kaynagin_patlamasi_digerlerini_durdurmaz(self, servis, monkeypatch):
        def patla():
            raise RuntimeError("ağ yok")

        monkeypatch.setattr(servis, "fetch_btc_trend", patla)
        monkeypatch.setattr(servis, "fetch_ethbtc", lambda: {"value": 0.031})
        monkeypatch.setattr(servis, "fetch_fear_greed", lambda: {"value": 73})
        monkeypatch.setattr(servis, "fetch_global", lambda: {"btc_dominance_pct": 58.8})
        monkeypatch.setattr(servis, "aktif_kaynaklar",
                            lambda: list(ms.MARKET_SOURCE_IDS))
        monkeypatch.setattr(servis, "_arsivle", lambda: None)

        yenilenen = servis.refresh_due(force=True)
        assert "btc_trend" not in yenilenen
        assert "ethbtc" in yenilenen and "fear_greed" in yenilenen
        assert servis._health["btc_trend"]["ok"] is False

    def test_basarisizlikta_eski_deger_silinmez(self, servis, monkeypatch):
        """Bayat veri, veri yokluğundan iyidir — yaşı bildirildiği sürece."""
        servis._cache["global"] = {"data": {"btc_dominance_pct": 58.8},
                                   "fetched_at": time.time() - 60}

        def patla():
            raise RuntimeError("22 saniye zaman aşımı")

        monkeypatch.setattr(servis, "fetch_global", patla)
        monkeypatch.setattr(servis, "aktif_kaynaklar", lambda: ["global"])
        monkeypatch.setattr(servis, "_arsivle", lambda: None)

        servis.refresh_due(force=True)
        assert servis._cache["global"]["data"]["btc_dominance_pct"] == 58.8

    def test_kapali_kaynak_hic_cagrilmaz(self, servis, monkeypatch):
        cagrildi = []
        monkeypatch.setattr(servis, "fetch_global",
                            lambda: cagrildi.append("global") or {})
        monkeypatch.setattr(servis, "aktif_kaynaklar", lambda: ["ethbtc"])
        monkeypatch.setattr(servis, "fetch_ethbtc", lambda: {"value": 0.031})
        monkeypatch.setattr(servis, "_arsivle", lambda: None)

        servis.refresh_due(force=True)
        assert cagrildi == []

    def test_ttl_dolmadan_tekrar_cagrilmaz(self, servis, monkeypatch):
        sayac = {"n": 0}

        def say():
            sayac["n"] += 1
            return {"value": 0.031}

        monkeypatch.setattr(servis, "fetch_ethbtc", say)
        monkeypatch.setattr(servis, "aktif_kaynaklar", lambda: ["ethbtc"])
        monkeypatch.setattr(servis, "_arsivle", lambda: None)

        servis.refresh_due(force=True)
        servis.refresh_due()          # TTL dolmadı
        servis.refresh_due()
        assert sayac["n"] == 1

    def test_ayarlardan_kapatilan_kaynak_aktif_listesinde_yok(self, servis, monkeypatch):
        monkeypatch.setattr(servis, "_ayarlar",
                            lambda: {"market_sources": {"global": {"enabled": False}}})
        aktif = servis.aktif_kaynaklar()
        assert "global" not in aktif
        assert "btc_trend" in aktif, "tanımsız kaynak varsayılan olarak açık olmalı"


# =====================================================================
# 7. ARŞİV — dominans geçmişi geri alınamaz, o yüzden saklanır
# =====================================================================
class TestArsiv:

    def _fotograf(self, dominans=58.84, kaynak="CoinGecko", fng=73, btc=79754.0):
        return {
            "available": True,
            "blocks": {
                "btc_trend": {"price": btc, "change_7d_pct": 1.9,
                              "change_30d_pct": 24.0, "sma50": 69131.0,
                              "sma200": 69719.0},
                "ethbtc": {"value": 0.03106},
                "fear_greed": {"value": fng, "classification": "Greed"},
                "global": {"btc_dominance_pct": dominans,
                           "total_market_cap_usd": 2715900000000.0,
                           "market_cap_excl_btc_usd": 1118000000000.0,
                           "source": kaynak},
                "breadth": {"advancing_pct": 81.1, "median_change_24h_pct": 2.77},
            },
        }

    def test_piyasa_tablosu_semada_var(self):
        """Sürüm numarasını sabitlemek yerine TABLONUN varlığını denetliyoruz.

        Eskiden burada `SCHEMA_VERSION == 3` yazıyordu ve arşive yeni bir
        tablo eklenen ilk fazda (F7, `exchange_events`) kırıldı — oysa M1'in
        garanti etmesi gereken şey sürüm numarası değil, piyasa geçmişinin
        yazılabildiğiydi. Numara sabitlemek, ilgisiz bir değişiklikte alarm
        veren ve o yüzden güveni azalan bir testtir.
        """
        archive.init_archive()
        durum = archive.archive_status()
        assert durum.get("schema_version") == archive.SCHEMA_VERSION
        assert archive.SCHEMA_VERSION >= 3
        assert archive.write_market_snapshot(self._fotograf()) is True

    def test_yazma_ve_okuma_tur_atlar(self):
        assert archive.write_market_snapshot(self._fotograf()) is True
        seri = archive.market_series(days=30)
        assert len(seri) == 1
        assert seri[0]["btc_dominance_pct"] == 58.84
        assert seri[0]["dominance_source"] == "CoinGecko"
        assert archive.market_snapshot_count() == 1

    def test_ayni_gun_uzerine_yazilir(self):
        archive.write_market_snapshot(self._fotograf(dominans=58.0))
        archive.write_market_snapshot(self._fotograf(dominans=59.5))
        assert archive.market_snapshot_count() == 1
        assert archive.market_series(days=5)[0]["btc_dominance_pct"] == 59.5

    def test_bos_fotograf_yazilmaz(self):
        assert archive.write_market_snapshot({"available": False}) is False
        assert archive.write_market_snapshot({"available": True, "blocks": {}}) is False
        assert archive.market_snapshot_count() == 0

    def test_kaynak_degisince_dominans_farki_alinmaz(self):
        """ASIL KORUMA. Kaynak değişirse iki farklı konvansiyonun farkını
        almak, gerçekte olmayan bir hareket üretir — ve model bunun üzerine
        tavsiye kurar."""
        archive.init_archive()
        with archive._connect() as conn:
            conn.execute(
                "INSERT INTO market_snapshots (taken_date, taken_at, taken_ts, "
                "btc_dominance_pct, dominance_source, fear_greed, btc_price_usd) "
                "VALUES ('2026-08-29','2026-08-29T12:00:00',1,56.52,'Coinpaprika',68,70000)")
        archive.write_market_snapshot(self._fotograf(dominans=58.84, kaynak="CoinGecko"))

        fark = archive.market_change_since(days_ago=7)
        assert fark is not None
        assert fark["btc_dominance_change_pts"] is None, \
            "farklı kaynakların dominans farkı ALINMAMALI"
        assert "dominance_note" in fark
        # Diğer metrikler kaynaktan bağımsız; onlar hesaplanmalı.
        assert fark["fear_greed_change"] == 5
        assert fark["btc_change_pct"] is not None

    def test_ayni_kaynakta_dominans_farki_alinir(self):
        archive.init_archive()
        with archive._connect() as conn:
            conn.execute(
                "INSERT INTO market_snapshots (taken_date, taken_at, taken_ts, "
                "btc_dominance_pct, dominance_source, fear_greed, btc_price_usd) "
                "VALUES ('2026-08-29','2026-08-29T12:00:00',1,56.84,'CoinGecko',68,70000)")
        archive.write_market_snapshot(self._fotograf(dominans=58.84, kaynak="CoinGecko"))

        fark = archive.market_change_since(days_ago=7)
        assert fark["btc_dominance_change_pts"] == 2.0

    def test_tek_kayitla_fark_hesaplanmaz(self):
        archive.write_market_snapshot(self._fotograf())
        assert archive.market_change_since(days_ago=7) is None

    def test_arsiv_bozuksa_uygulama_durmaz(self, monkeypatch):
        def bozuk():
            raise RuntimeError("disk dolu")

        monkeypatch.setattr(archive, "_connect", bozuk)
        assert archive.write_market_snapshot(self._fotograf()) is False
        assert archive.market_series(days=7) == []
        assert archive.market_change_since(days_ago=7) is None
        assert archive.market_snapshot_count() == 0


# =====================================================================
# 8. YZ BAĞLAMINA BAĞLANMA
# =====================================================================
class TestYapayZekaBaglami:

    def test_piyasa_verisi_yoksa_analiz_yine_calisir(self, monkeypatch):
        """Piyasa verisi bir konfordur. Analiz onu BEKLEMEZ."""
        import ai_service
        monkeypatch.setattr(ms.market_service, "get_snapshot",
                            lambda: {"available": False, "blocks": {}})
        ozet = ai_service.ai_advisor._piyasa_ozeti()
        assert ozet["available"] is False
        assert "reason" in ozet

    def test_piyasa_servisi_patlarsa_baglam_yine_doner(self, monkeypatch):
        import ai_service

        def patla():
            raise RuntimeError("servis yok")

        monkeypatch.setattr(ms.market_service, "get_snapshot", patla)
        ozet = ai_service.ai_advisor._piyasa_ozeti()
        assert ozet["available"] is False

    def test_bloklar_ve_okuma_talimati_modele_gider(self, monkeypatch):
        import ai_service
        monkeypatch.setattr(ms.market_service, "get_snapshot", lambda: {
            "available": True, "generated_at": 1,
            "blocks": {"btc_trend": {"price": 79754.0, "freshness": "fresh"}},
        })
        ozet = ai_service.ai_advisor._piyasa_ozeti()
        assert ozet["available"] is True
        assert "btc_trend" in ozet["blocks"]
        # Modelin en sık düştüğü tuzak tek sayıdan hüküm çıkarmak.
        assert "how_to_read" in ozet
        assert "sinyal" in ozet["how_to_read"].lower()

    def test_cerceve_piyasa_kurallarini_iceriyor(self):
        """Prompt'taki 6. kural olmadan model tek sayıdan hüküm çıkarır."""
        import ai_service
        import inspect
        kaynak = inspect.getsource(ai_service.AIFinancialAdvisor._call_gemini_api)
        assert "PİYASA VERİSİ" in kaynak
        assert "TEK BİR SAYIDAN HÜKÜM ÇIKARMA" in kaynak
        assert "DOMİNANS BİR KONVANSİYONDUR" in kaynak
        # Piyasa verisi diğer kuralları geçersiz kılmamalı.
        assert "PORTFÖYÜN YERİNE GEÇMEZ" in kaynak

    def test_yerel_motor_piyasa_notunu_yazar(self):
        import ai_service
        baglam = {"market": {"available": True, "blocks": {
            "btc_trend": {"price": 79754.0, "change_7d_pct": 1.9,
                          "change_30d_pct": 24.0, "pct_vs_sma50": 15.4,
                          "pct_vs_sma200": 14.4, "freshness": "fresh"},
            "global": {"btc_dominance_pct": 58.84, "source": "CoinGecko",
                       "market_cap_excl_btc_usd": 1.118e12, "freshness": "fresh"},
        }}}
        satirlar = ai_service.ai_advisor._piyasa_notu(baglam)
        metin = "\n".join(satirlar)
        assert "Piyasa Çerçevesi" in metin
        assert "79,754" in metin or "79754" in metin
        assert "CoinGecko" in metin

    def test_yerel_motor_bayat_veriyi_isaretler(self):
        import ai_service
        baglam = {"market": {"available": True, "blocks": {
            "fear_greed": {"value": 73, "classification": "Greed",
                           "freshness": "stale", "age_human": "40 saat"},
        }}}
        metin = "\n".join(ai_service.ai_advisor._piyasa_notu(baglam))
        assert "bayat" in metin
        assert "40 saat" in metin

    def test_veri_yokken_yerel_motor_bunu_soyler(self):
        import ai_service
        metin = "\n".join(ai_service.ai_advisor._piyasa_notu(
            {"market": {"available": False}}))
        assert "Piyasa verisi şu an yok" in metin


# =====================================================================
# 9. FİYAT MOTORU BAĞI — genişlik gerçekten sıfır çağrı mı?
# =====================================================================
class TestFiyatMotoruBagi:

    def test_binance_adaptoru_genislik_girdisini_doldurur(self):
        """Ek çağrı yok iddiasının kanıtı: veri, mevcut ticker yanıtından
        çıkarılıyor."""
        import price_service as ps
        motor = ps.SmartPriceDiscoveryEngine()
        sahte_yanit = [
            {"symbol": "BTCUSDT", "lastPrice": "79754.0", "volume": "100",
             "openPrice": "79800.0", "priceChangePercent": "-0.03",
             "quoteVolume": "1200000000"},
            {"symbol": "ETHUSDT", "lastPrice": "2470.0", "volume": "500",
             "openPrice": "2400.0", "priceChangePercent": "2.9",
             "quoteVolume": "800000000"},
            {"symbol": "BTCFDUSD", "lastPrice": "79750.0", "volume": "10",
             "openPrice": "79800.0", "priceChangePercent": "-0.06",
             "quoteVolume": "50000000"},
        ]
        cagri_sayisi = {"n": 0}

        def sahte_fetch(url, timeout=5, user_agent=None):
            cagri_sayisi["n"] += 1
            return sahte_yanit

        motor.fetch_url_json = sahte_fetch
        motor._adapter_binance({})

        girdi = motor.get_breadth_input()
        assert cagri_sayisi["n"] == 1, "genişlik için EK çağrı yapılmış"
        semboller = {r["symbol"] for r in girdi}
        assert semboller == {"BTCUSDT", "ETHUSDT"}, "yalnızca USDT çiftleri alınmalı"
        btc = next(r for r in girdi if r["symbol"] == "BTCUSDT")
        assert btc["quote_volume"] == 1200000000.0

    def test_bos_tur_eski_genislik_tablosunu_silmez(self):
        import price_service as ps
        motor = ps.SmartPriceDiscoveryEngine()
        motor._breadth_input = [{"symbol": "BTCUSDT", "change_pct": 1.0,
                                 "quote_volume": 1e9}]

        def bos(url, timeout=5, user_agent=None):
            raise RuntimeError("ağ yok")

        motor.fetch_url_json = bos
        motor._adapter_binance({})
        assert len(motor.get_breadth_input()) == 1


# =====================================================================
# 10. AĞA ÇIKILMIYOR — bu dosyanın en önemli testi
# =====================================================================
class TestAgaCikilmiyor:

    def test_hicbir_yardimci_urlopen_cagirmaz(self, monkeypatch):
        """urlopen'ı patlatıp tüm saf dönüştürücüleri çalıştırıyoruz.
        Biri gizlice ağa çıkıyorsa bu test kırılır."""
        import urllib.request

        def yasak(*a, **k):
            raise AssertionError("TEST AĞA ÇIKTI — bu kesinlikle yasak")

        monkeypatch.setattr(urllib.request, "urlopen", yasak)

        MarketDataService._klines_to_trend(klines_uret([100.0] * 210), "BTCUSDT")
        MarketDataService._fng_to_dict(FNG_ORNEK)
        MarketDataService._global_to_dict(GLOBAL_ORNEK)
        MarketDataService._breadth_to_dict(genislik_girdisi())

        s = MarketDataService(price_engine=SahteFiyatMotoru())
        s.fetch_breadth()
        s.get_snapshot()
        s.describe_sources()

    def test_snapshot_okumasi_ag_gerektirmez(self, monkeypatch):
        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("ağa çıkıldı")))
        s = MarketDataService()
        s._cache["fear_greed"] = {"data": {"value": 73}, "fetched_at": time.time()}
        out = s.get_snapshot()
        assert out["blocks"]["fear_greed"]["value"] == 73

    def test_gemini_ye_cagri_yok(self, monkeypatch):
        """Proje kuralı: hiçbir test Gemini API'ye çıkmaz."""
        import urllib.request

        def yasak(req, *a, **k):
            url = getattr(req, "full_url", str(req))
            raise AssertionError(f"YASAK ÇAĞRI: {url}")

        monkeypatch.setattr(urllib.request, "urlopen", yasak)
        import ai_service
        ozet = ai_service.ai_advisor._piyasa_notu({"market": {"available": False}})
        assert ozet


# =====================================================================
# 11. ARAYÜZ ŞERİDİ — modele giden sayı kullanıcıya da görünmeli
# =====================================================================
STATIC_DIR = os.path.join(PROJECT_ROOT, "app", "static")


def _oku(ad):
    with open(os.path.join(STATIC_DIR, ad), "r", encoding="utf-8") as f:
        return f.read()


class TestArayuzSeridi:

    def test_serit_html_de_var_ve_metotlara_baglanmis(self):
        html = _oku("index.html")
        assert "PİYASA ÇERÇEVESİ" in html
        for parca in ("marketCards()", "marketAvailable", "fetchMarket()",
                      "marketKeylessWarning"):
            assert parca in html, f"şerit '{parca}' ile bağlanmamış"

    def test_app_js_gerekli_metotlari_tanimliyor(self):
        js = _oku("app.js")
        for metot in ("async fetchMarket()", "get marketAvailable()",
                      "get marketKeylessWarning()", "marketCards()",
                      "showCoinGeckoKey"):
            assert metot in js, f"app.js '{metot}' tanımlamıyor"

    def test_serit_hukum_kelimesi_icermez(self):
        """Şerit ham ölçüm gösterir. Arayüzde 'boğa/ayı/ölüm kesişimi' gibi
        bir etiket belirirse, kaçındığımız hatayı arayüz tarafından geri
        getirmiş oluruz."""
        html = _oku("index.html")
        # Yalnızca piyasa şeridi bloğuna bak.
        bas = html.index("PİYASA ÇERÇEVESİ")
        son = html.index("4 Strategic Analysis Selector Cards")
        serit = html[bas:son].lower()
        for yasak in ("ölüm kesişimi", "altın kesişim", "boğa piyasası",
                      "ayı piyasası", "death cross", "golden cross"):
            assert yasak not in serit, f"şeritte hüküm var: {yasak}"

    def test_ayarlarda_anahtar_alani_ve_yedek_mod_uyarisi_var(self):
        html = _oku("index.html")
        assert "settings.api_keys.coingecko_api_key" in html
        assert "Yedek modda" in html
        assert "tercih edilen yoldur" in html

    def test_dominans_kaynagi_arayuzde_gosterilir(self):
        """Kullanıcı başka bir yerde farklı bir dominans görebilir; hangi
        konvansiyonu gösterdiğimizi söylemezsek bunu hata sanar."""
        js = _oku("app.js")
        assert "glb.source" in js
