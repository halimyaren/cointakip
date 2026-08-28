r"""
CoinTakip — FAZ F1d Testleri: Kaynak Başına User-Agent ve Kaynak Sağlığı

İki gerçek hatayı kalıcı olarak kapatır.

**1. Zıt User-Agent gereksinimleri.**
Kaynaklar bu konuda birbirinin tersine davranıyor:

  DexScreener : çıplak urllib isteğini reddeder → tarayıcı UA'sı ŞART
  Gate.io     : tarayıcı UA'sını reddeder (403) → UA GÖNDERİLMEMELİ

Tek bir ortak başlık kullanıldığı sürece bunlardan biri hep kırık kalır.
Nitekim Gate.io adaptörü ilk sürümden (`5d90907`) beri hiç çalışmadı: her
turda 403 aldı, hata `logger.debug` ile yutuldu, kimse fark etmedi.

**2. Sessiz başarısızlık.**
Hiç çalışmayan bir kaynakla "bu turda bir şey bulamadım" diyen kaynak arayüzde
birbirinin aynısı görünüyordu. Kullanıcı kaynağı açık sanıp neden fiyat
gelmediğini anlayamıyordu.

NOT: Buradaki hiçbir test gerçek ağa çıkmaz — `fetch_url_json` her testte
taklit edilir.
"""

import pytest

import price_service as ps


@pytest.fixture
def motor():
    m = ps.SmartPriceDiscoveryEngine()
    m._config_cache = m._default_config()
    m._config_ts = 9e18          # yapılandırma diskten okunmasın
    return m


# =====================================================================
# BÖLÜM 1 — KAYNAK BAŞINA USER-AGENT
# =====================================================================
class TestUserAgent:

    def test_gateio_user_agent_GONDERMEZ(self, motor, monkeypatch):
        """
        Asıl regresyon testi. Gate.io tarayıcı UA'sını 403 ile reddediyor;
        bu satır bozulursa kaynak yine sessizce ölür.
        """
        gorulen = {}

        def sahte(url, timeout=5, user_agent="DEGISMEDI"):
            gorulen["ua"] = user_agent
            return []

        monkeypatch.setattr(motor, "fetch_url_json", sahte)
        motor._adapter_gateio({})
        assert gorulen["ua"] is None, \
            "Gate.io'ya User-Agent gönderiliyor — 403 alacak ve kaynak ölecek."

    def test_dexscreener_tarayici_user_agent_GONDERIR(self, motor, monkeypatch):
        """Ters yön: DexScreener çıplak isteği reddediyor, UA şart."""
        gorulen = {}

        def sahte(url, timeout=5, user_agent=None):
            gorulen["ua"] = user_agent
            return {"pairs": []}

        monkeypatch.setattr(motor, "fetch_url_json", sahte)
        monkeypatch.setattr(motor, "fetch_dex_pair", lambda a: None)
        motor.fetch_dex_screener("RDNT")
        assert gorulen["ua"] == ps.BROWSER_UA, \
            "DexScreener'a tarayıcı UA'sı gönderilmiyor — 403 alacak."

    def test_iki_kaynak_farkli_baslik_alir(self, motor):
        """Sözleşme: bu ikisi ASLA aynı başlığı kullanamaz."""
        assert ps.SOURCE_USER_AGENTS["gateio"] is None
        assert ps.SOURCE_USER_AGENTS["dex"] == ps.BROWSER_UA
        assert ps.SOURCE_USER_AGENTS["gateio"] != ps.SOURCE_USER_AGENTS["dex"]

    def test_fetch_url_json_none_verilince_baslik_koymaz(self, motor, monkeypatch):
        yakalanan = {}

        class SahteYanit:
            def read(self): return b"{}"
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def sahte_urlopen(req, timeout=5):
            yakalanan["headers"] = dict(req.headers)
            return SahteYanit()

        monkeypatch.setattr(ps.urllib.request, "urlopen", sahte_urlopen)

        motor.fetch_url_json("https://ornek.test/x", user_agent=None)
        # urllib başlık adlarını "User-agent" biçiminde normalize eder.
        assert not any(k.lower() == "user-agent" for k in yakalanan["headers"]), \
            "user_agent=None verildiği hâlde başlık gönderildi."

        motor.fetch_url_json("https://ornek.test/x", user_agent="AjanX/1.0")
        assert any(k.lower() == "user-agent" and v == "AjanX/1.0"
                   for k, v in yakalanan["headers"].items())

    def test_varsayilan_tarayici_ua_sidir(self, motor, monkeypatch):
        """Çağıran belirtmezse eski davranış korunur (Binance/MEXC/WhiteBIT)."""
        gorulen = {}

        def sahte(url, timeout=5, user_agent=ps.BROWSER_UA):
            gorulen["ua"] = user_agent
            return []

        monkeypatch.setattr(motor, "fetch_url_json", sahte)
        motor._adapter_mexc({})
        assert gorulen["ua"] == ps.BROWSER_UA


# =====================================================================
# BÖLÜM 2 — KAYNAK SAĞLIĞI
# =====================================================================
class TestKaynakSagligi:

    def test_basarili_kaynak_saglikli_isaretlenir(self, motor, monkeypatch):
        monkeypatch.setattr(motor, "_adapter_mexc",
                            lambda api_urls: ({"BTCUSDT": {"price": 1.0}}, []))
        motor._run_adapter("mexc", {})
        assert motor._source_health["mexc"]["ok"] is True
        assert motor._source_health["mexc"]["fail_count"] == 0

    def test_tek_hata_kaynagi_hemen_olu_ilan_etmez(self, motor, monkeypatch):
        """Geçici ağ hıçkırığı rozet çıkarmamalı."""
        def patlat(api_urls):
            raise OSError("gecici ag hatasi")
        monkeypatch.setattr(motor, "_adapter_gateio", patlat)

        motor._run_adapter("gateio", {})
        assert motor._source_health["gateio"]["ok"] is True, \
            "Tek hatadan sonra kaynak ölü sayıldı."
        assert motor._source_health["gateio"]["fail_count"] == 1

    def test_ust_uste_hata_kaynagi_olu_isaretler(self, motor, monkeypatch):
        def patlat(api_urls):
            raise ps.urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
        monkeypatch.setattr(motor, "_adapter_gateio", patlat)

        for _ in range(ps.SOURCE_FAIL_THRESHOLD):
            motor._run_adapter("gateio", {})

        h = motor._source_health["gateio"]
        assert h["ok"] is False
        assert h["fail_count"] == ps.SOURCE_FAIL_THRESHOLD
        assert "403" in h["last_error"]

    def test_basari_sayaci_sifirlar(self, motor, monkeypatch):
        def patlat(api_urls):
            raise OSError("hata")
        monkeypatch.setattr(motor, "_adapter_gateio", patlat)
        for _ in range(ps.SOURCE_FAIL_THRESHOLD):
            motor._run_adapter("gateio", {})
        assert motor._source_health["gateio"]["ok"] is False

        monkeypatch.setattr(motor, "_adapter_gateio",
                            lambda api_urls: ({"BTCUSDT": {"price": 1.0}}, []))
        motor._run_adapter("gateio", {})
        h = motor._source_health["gateio"]
        assert h["ok"] is True and h["fail_count"] == 0 and h["last_error"] is None

    def test_hatasiz_ama_bos_donmek_de_basarisizliktir(self, motor, monkeypatch):
        """
        Gate.io'nun asıl davranışı buydu: istisna fırlatmıyor, boş dönüyordu.
        Kullanıcı için sonuç aynı — kaynak işe yaramıyor.
        """
        monkeypatch.setattr(motor, "_adapter_gateio", lambda api_urls: ({}, []))
        for _ in range(ps.SOURCE_FAIL_THRESHOLD):
            motor._run_adapter("gateio", {})
        assert motor._source_health["gateio"]["ok"] is False
        assert "boş" in motor._source_health["gateio"]["last_error"]

    def test_dex_ulasilabilirse_saglikli(self, motor, monkeypatch):
        """DEX'te boş sonuç arıza değildir — sembol o zincirde olmayabilir."""
        monkeypatch.setattr(motor, "fetch_url_json",
                            lambda url, timeout=5, user_agent=None: {"pairs": []})
        monkeypatch.setattr(motor, "fetch_dex_pair", lambda a: None)
        motor.fetch_dex_screener("YOKBOYLECOIN")
        assert motor._source_health["dex"]["ok"] is True

    def test_dex_ulasilamiyorsa_saglıksiz(self, motor, monkeypatch):
        def patlat(url, timeout=5, user_agent=None):
            raise OSError("baglanti yok")
        monkeypatch.setattr(motor, "fetch_url_json", patlat)
        for _ in range(ps.SOURCE_FAIL_THRESHOLD):
            motor.fetch_dex_screener("RDNT")
        assert motor._source_health["dex"]["ok"] is False


class TestSaglikArayuzeTasiniyor:

    def test_describe_sources_saglik_alanlarini_icerir(self, motor):
        for row in motor.describe_sources():
            for alan in ("healthy", "fail_count", "last_error", "last_ok_ts"):
                assert alan in row, f"'{alan}' alanı eksik — arayüz rozeti çizemez."

    def test_denenmemis_kaynak_healthy_none_doner(self, motor):
        """Kapalı kaynak hiç denenmez; 'bozuk' demek yanlış olur."""
        satir = next(r for r in motor.describe_sources() if r["id"] == "gateio")
        assert satir["healthy"] is None

    def test_bozuk_kaynak_arayuzde_isaretlenir(self, motor, monkeypatch):
        def patlat(api_urls):
            raise ps.urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
        monkeypatch.setattr(motor, "_adapter_gateio", patlat)
        for _ in range(ps.SOURCE_FAIL_THRESHOLD):
            motor._run_adapter("gateio", {})

        satir = next(r for r in motor.describe_sources() if r["id"] == "gateio")
        assert satir["healthy"] is False
        assert satir["fail_count"] == ps.SOURCE_FAIL_THRESHOLD
        assert satir["last_error"]

    def test_api_ucu_saglik_bilgisini_doner(self, client):
        r = client.get("/api/price-sources")
        assert r.status_code == 200
        kaynaklar = r.json()["registry"]
        assert kaynaklar and all("healthy" in s for s in kaynaklar)
