"""
FAZ M2 — kaldıraç ortamı: fonlama oranları ve açık pozisyon.

Yanıt biçimleri gerçek uçlardan kaydedildi (10 Eylül 2026); testler onları
aynen oynatıyor. Bu, biçim işlerinde tek güvenilir yol — uydurulmuş bir
örnek, gerçekte olmayan bir alanı varsayabilir.

EN ÖNEMLİ GÜVENCE EN SONDA: **hüküm üretilmez.** Kullanıcı bunu açıkça
istedi — "spot kaynaklı", "kaldıraç kaynaklı", "aşırı kaldıraç" gibi
deterministik etiketler üretilmeyecek; ham değer ve açık tanımlı değişim
verilecek, yorum modele bırakılacak. Modülün 1 numaralı tasarım kuralı da
zaten bu ve orada somut bir örnekle gerekçelendirilmiş: ölçüm günü "ölüm
kesişimi" etiketi gerçeğin tam tersini söylüyordu.
"""

import pytest

import market_service as ms
from market_service import MarketDataService


# Gerçek `premiumIndex` yanıtından kısaltılmış satırlar.
def _fon(sembol, oran):
    return {"symbol": sembol, "markPrice": "100.0", "indexPrice": "100.0",
            "estimatedSettlePrice": "100.0", "lastFundingRate": str(oran),
            "interestRate": "0.00010000", "nextFundingTime": 1789000000000,
            "time": 1788999000000}


def _ap_gecmis(satirlar):
    """(gun_ofseti, oi, deger) üçlülerinden `openInterestHist` yanıtı."""
    gun = 86400000
    simdi = 1789000000000
    return [{"symbol": "BTCUSDT", "sumOpenInterest": str(oi),
             "sumOpenInterestValue": str(deger),
             "CMCCirculatingSupply": "20081628.00000000",
             "timestamp": simdi - ofset * gun}
            for ofset, oi, deger in satirlar]


# =====================================================================
# Fonlama
# =====================================================================
class TestFonlama:

    def _ham(self):
        return [
            _fon("BTCUSDT", 0.00007357),
            _fon("ETHUSDT", 0.00005000),
            _fon("SOLUSDT", -0.00002000),
            _fon("XRPUSDT", 0.00010000),
            # USDT olmayanlar dağılıma girmemeli: coin marjlı perpetual
            # farklı bir enstrüman.
            _fon("BTCUSD_PERP", 0.00050000),
        ]

    def test_btc_orani_okunur(self):
        blok = MarketDataService._funding_to_dict(self._ham())
        assert blok["btc"]["rate_8h"] == pytest.approx(0.00007357)

    def test_yillik_basit_carpimla_hesaplanir(self):
        """Bileşiklemek oranın sabit kalacağını varsaymak olurdu."""
        blok = MarketDataService._funding_to_dict(self._ham())
        beklenen = 0.00007357 * 3 * 365 * 100.0
        assert blok["btc"]["annualized_pct"] == pytest.approx(beklenen)

    def test_eth_ayri_verilir(self):
        blok = MarketDataService._funding_to_dict(self._ham())
        assert blok["eth"]["rate_8h"] == pytest.approx(0.00005)

    def test_coin_marjli_dagilima_girmez(self):
        """`BTCUSD_PERP` en yüksek oranı taşıyor; sayıma girseydi medyanı
        ve pozitif oranını bozardı."""
        blok = MarketDataService._funding_to_dict(self._ham())
        assert blok["sample_size"] == 4

    def test_pozitif_orani_sayimdir(self):
        blok = MarketDataService._funding_to_dict(self._ham())
        assert blok["positive_count"] == 3
        assert blok["positive_share_pct"] == pytest.approx(75.0)

    def test_medyan_cift_sayida_ortalamadir(self):
        blok = MarketDataService._funding_to_dict(self._ham())
        # sıralı: -0.00002, 0.00005, 0.00007357, 0.0001
        assert blok["median_rate_8h"] == pytest.approx((0.00005 + 0.00007357) / 2)

    def test_olmayan_sembol_none_doner(self):
        """Uydurmak yerine yokluğu söylemek."""
        blok = MarketDataService._funding_to_dict([_fon("SOLUSDT", 0.0001)])
        assert blok["btc"] is None and blok["eth"] is None

    def test_tanim_metni_veriliyor(self):
        """Modelin sayıyı doğru okuması için biriminin ne olduğu yazılı
        olmalı; '0.00007' tek başına 8 saatlik mi yıllık mı belli değildir."""
        blok = MarketDataService._funding_to_dict(self._ham())
        assert "8 saat" in blok["definition"] or "3 ödeme" in blok["definition"]

    def test_bozuk_yanit_hata_verir(self):
        for kotu in ([], {}, "olmadi", None):
            with pytest.raises(ValueError):
                MarketDataService._funding_to_dict(kotu)

    def test_sayiya_cevrilemeyen_satir_atlanir(self):
        ham = self._ham() + [{"symbol": "ZZZUSDT", "lastFundingRate": "abc"}]
        assert MarketDataService._funding_to_dict(ham)["sample_size"] == 4


# =====================================================================
# Açık pozisyon
# =====================================================================
class TestAcikPozisyon:

    def _anlik(self, oi=107309.0):
        return {"symbol": "BTCUSDT", "openInterest": str(oi),
                "time": 1789000500000}

    def test_canli_deger_okunur(self):
        blok = MarketDataService._oi_to_dict(
            "BTCUSDT", self._anlik(), _ap_gecmis([(0, 105106, 8227209024)]))
        assert blok["open_interest"] == pytest.approx(107309.0)
        assert blok["live_at"] == 1789000500000

    def test_dolar_karsiligi_son_satirdan_gelir(self):
        blok = MarketDataService._oi_to_dict(
            "BTCUSDT", self._anlik(), _ap_gecmis([(0, 105106, 8227209024)]))
        assert blok["open_interest_usd"] == pytest.approx(8227209024)

    def test_degisim_canli_deger_ile_gunluk_fotograf_arasinda(self):
        """Ölçüldü: canlı değer ile bugünkü günlük fotoğraf 2.203 BTC
        farklıydı. İkisini aynı şey saymak olmayan bir hareket uydururdu,
        bu yüzden karşılaştırma AÇIKÇA canlı-değer-ile-N-gün-önce."""
        gecmis = _ap_gecmis([(1, 100000, 8_000_000_000),
                             (0, 105106, 8_227_209_024)])
        blok = MarketDataService._oi_to_dict("BTCUSDT", self._anlik(107309.0),
                                             gecmis)
        assert blok["change_1d_pct"] == pytest.approx(
            (107309.0 - 100000) / 100000 * 100.0)

    def test_karsilastirilan_iki_zaman_damgasi_da_verilir(self):
        """"Açık tanımlı değişim" demek, neyin neyle karşılaştırıldığının
        kayıtta durması demek."""
        gecmis = _ap_gecmis([(1, 100000, 8e9), (0, 105106, 8.2e9)])
        blok = MarketDataService._oi_to_dict("BTCUSDT", self._anlik(), gecmis)
        assert blok["baselines"]["1d"]["open_interest"] == pytest.approx(100000)
        assert blok["baselines"]["1d"]["at"] > 0
        assert blok["live_at"] > 0

    def test_yedi_gunluk_degisim(self):
        gecmis = _ap_gecmis([(i, 100000 + i, 8e9) for i in range(7, -1, -1)])
        blok = MarketDataService._oi_to_dict("BTCUSDT", self._anlik(110000.0),
                                             gecmis)
        assert "change_7d_pct" in blok and "change_1d_pct" in blok

    def test_gecmis_yetmezse_degisim_UYDURULMAZ(self):
        """Yeterli geçmiş yoksa alan hiç doğmaz; sıfır yazmak 'değişmedi'
        demek olurdu ve bu yanlış bir iddiadır."""
        gecmis = _ap_gecmis([(1, 100000, 8e9), (0, 105106, 8.2e9)])
        blok = MarketDataService._oi_to_dict("BTCUSDT", self._anlik(), gecmis)
        assert "change_1d_pct" in blok
        assert "change_7d_pct" not in blok

    def test_gecmis_hic_yoksa_canli_deger_yine_verilir(self):
        blok = MarketDataService._oi_to_dict("BTCUSDT", self._anlik(), [])
        assert blok["open_interest"] == pytest.approx(107309.0)
        assert blok["baselines"] == {}

    def test_sifir_taban_bolme_hatasi_uretmez(self):
        gecmis = _ap_gecmis([(1, 0, 0), (0, 105106, 8.2e9)])
        blok = MarketDataService._oi_to_dict("BTCUSDT", self._anlik(), gecmis)
        assert "change_1d_pct" not in blok

    def test_bozuk_yanit_hata_verir(self):
        for kotu in ({}, {"symbol": "BTCUSDT"}, None, "olmadi"):
            with pytest.raises(ValueError):
                MarketDataService._oi_to_dict("BTCUSDT", kotu, [])


# =====================================================================
# KULLANICININ AÇIK KURALI: HÜKÜM ÜRETİLMEZ
# =====================================================================
class TestHukumUretilmez:
    """Ham değer ve açık tanımlı değişim verilir; "spot kaynaklı",
    "kaldıraç kaynaklı", "aşırı kaldıraç" gibi deterministik etiketler
    ÜRETİLMEZ. Yorum modele ve kullanıcıya aittir."""

    YASAK = ("leverage_driven", "spot_driven", "overleveraged", "excessive",
             "crowded", "signal", "verdict", "bullish", "bearish", "regime",
             "asiri", "kaldirac_kaynakli", "spot_kaynakli", "yorum")

    def test_fonlama_blogunda_hukum_alani_yok(self):
        blok = MarketDataService._funding_to_dict([_fon("BTCUSDT", 0.01)])
        for anahtar in blok:
            assert not any(y in anahtar.lower() for y in self.YASAK), anahtar

    def test_acik_pozisyon_blogunda_hukum_alani_yok(self):
        blok = MarketDataService._oi_to_dict(
            "BTCUSDT", {"symbol": "BTCUSDT", "openInterest": "1", "time": 1},
            _ap_gecmis([(1, 1, 1), (0, 2, 2)]))
        for anahtar in blok:
            assert not any(y in anahtar.lower() for y in self.YASAK), anahtar

    def test_asiri_oranda_bile_yalnizca_sayi_doner(self):
        """Fonlama %1/8saat (yıllık ~%1095) olsa bile etiket yok."""
        blok = MarketDataService._funding_to_dict([_fon("BTCUSDT", 0.01)])
        assert blok["btc"]["annualized_pct"] > 1000
        assert set(blok["btc"]) == {"rate_8h", "rate_8h_pct", "annualized_pct"}

    def test_kaynak_dosyada_hukum_esigi_yok(self):
        """Kaynak seviyesinde denetim: ileride biri "şu eşiğin üstü aşırı"
        diye bir sabit eklemek isterse bu test onu durdurur."""
        import os
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(kok, "app", "market_service.py"),
                  encoding="utf-8") as f:
            kaynak = f.read()
        for yasak in ("ASIRI_", "OVERLEVERAGED", "FONLAMA_ESIGI",
                      "AP_ESIGI", "KALDIRAC_ESIGI"):
            assert yasak not in kaynak, yasak


# =====================================================================
# Kayıt defteri ve servis bütünlüğü
# =====================================================================
class TestKayitDefteri:

    def test_iki_kaynak_da_kayitli(self):
        assert "funding" in ms.MARKET_SOURCE_IDS
        assert "open_interest" in ms.MARKET_SOURCE_IDS

    def test_her_kaynagin_etiketi_var(self):
        for kid in ms.MARKET_SOURCE_IDS:
            assert kid in ms.MARKET_SOURCE_LABELS

    def test_her_kaynagin_tazelik_esigi_var(self):
        """Eşiği olmayan kaynak bayat veriyi taze gibi gösterirdi."""
        for kid in ms.MARKET_SOURCE_IDS:
            assert kid in ms.TAZELIK_ESIKLERI, kid

    def test_cekiciler_kayitla_ortusur(self):
        servis = MarketDataService()
        assert set(servis._cekiciler()) == set(ms.MARKET_SOURCE_IDS)

    def test_bir_sembol_dusse_digeri_yasar(self, monkeypatch):
        servis = MarketDataService()
        cagri = {"n": 0}

        def sahte(sembol):
            cagri["n"] += 1
            if sembol == "BTCUSDT":
                raise RuntimeError("fapi engelli")
            return {"symbol": sembol, "open_interest": 5.0}

        monkeypatch.setattr(servis, "_sembol_acik_pozisyon", sahte)
        blok = servis.fetch_open_interest()
        assert list(blok["symbols"]) == ["ETHUSDT"]
        assert cagri["n"] == 2

    def test_hicbiri_gelmezse_hata(self, monkeypatch):
        """Boş bir blok döndürmek 'açık pozisyon sıfır' gibi okunurdu."""
        servis = MarketDataService()
        monkeypatch.setattr(servis, "_sembol_acik_pozisyon",
                            lambda s: (_ for _ in ()).throw(RuntimeError("yok")))
        with pytest.raises(ValueError):
            servis.fetch_open_interest()


# =====================================================================
# Arşiv
# =====================================================================
class TestArsivAlanlari:

    def test_bloklar_yoksa_sutunlar_none_kalir(self):
        """Sıfır yazmak 'fonlama sıfırdı' demek olurdu; bu, 'bakamadık'tan
        tamamen farklı bir iddiadır."""
        import archive
        alanlar = archive._kaldirac_alanlari({})
        assert set(alanlar.values()) == {None}

    def test_bloklar_varsa_sutunlar_dolar(self):
        import archive
        alanlar = archive._kaldirac_alanlari({
            "funding": {"btc": {"rate_8h": 0.0001}, "eth": {"rate_8h": 0.00005},
                        "median_rate_8h": 0.00002, "positive_share_pct": 70.0},
            "open_interest": {"symbols": {
                "BTCUSDT": {"open_interest": 107309.0,
                            "open_interest_usd": 8.2e9,
                            "change_1d_pct": 2.1},
                "ETHUSDT": {"open_interest": 2000.0, "change_1d_pct": -1.0}}},
        })
        assert alanlar["funding_btc_8h"] == pytest.approx(0.0001)
        assert alanlar["oi_btc_change_1d_pct"] == pytest.approx(2.1)
        assert alanlar["oi_eth"] == pytest.approx(2000.0)

    def test_eski_arsive_sutunlar_eklenir(self, tmp_path, monkeypatch):
        """`CREATE TABLE IF NOT EXISTS` var olan tabloya sütun EKLEMEZ.
        Göç olmadan kullanıcının arşivi "no such column" ile yazmayı
        reddederdi."""
        import sqlite3

        import archive
        import data_manager

        monkeypatch.setattr(data_manager, "DATA_DIR", str(tmp_path))
        yol = str(tmp_path / "archive.db")
        # M2 ÖNCESİ şemayı taklit et.
        with sqlite3.connect(yol) as conn:
            conn.execute("""CREATE TABLE market_snapshots (
                taken_date TEXT PRIMARY KEY, taken_at TEXT NOT NULL,
                taken_ts REAL NOT NULL, btc_price_usd REAL, raw_json TEXT)""")
            conn.execute("INSERT INTO market_snapshots VALUES "
                         "('2026-09-01','2026-09-01T00:00:00',1.0,50000.0,'{}')")

        archive.init_archive()
        with sqlite3.connect(yol) as conn:
            sutunlar = {r[1] for r in conn.execute(
                "PRAGMA table_info(market_snapshots)")}
            satir = conn.execute("SELECT btc_price_usd FROM market_snapshots"
                                 " WHERE taken_date='2026-09-01'").fetchone()
        assert "funding_btc_8h" in sutunlar and "oi_btc" in sutunlar
        assert satir[0] == pytest.approx(50000.0)      # eski satır korundu

    def test_goc_ikinci_calistirmada_patlamaz(self, tmp_path, monkeypatch):
        import archive
        import data_manager
        monkeypatch.setattr(data_manager, "DATA_DIR", str(tmp_path))
        assert archive.init_archive() is True
        assert archive.init_archive() is True


class TestArayuzKartlari:
    """Kartlar da hüküm taşımamalı ve yokluğu sıfırdan ayırmalı."""

    def _js(self):
        import os
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(kok, "app", "static", "app.js"),
                  encoding="utf-8") as f:
            return f.read()

    def test_iki_metrik_de_ekranda(self):
        js = self._js()
        assert "id: 'funding'" in js
        assert "id: 'oi'" in js

    def test_fonlama_hem_yillik_hem_8_saatlik_gosterilir(self):
        """Yalnızca yıllığı göstermek hangi sayıya bakıldığını belirsiz
        bırakır; yalnızca 8 saatliği göstermek okunamaz (%0.0075)."""
        js = self._js()
        nerede = js.index("id: 'funding'")
        blok = js[nerede:nerede + 500]
        assert "annualized_pct" in blok and "rate_8h_pct" in blok

    def test_kartlarda_hukum_kelimesi_yok(self):
        js = self._js()
        nerede = js.index("id: 'funding'")
        blok = js[nerede:js.index("return kartlar;", nerede)]
        for yasak in ("aşırı", "asiri", "kalabalık", "kalabalik",
                      "sinyal", "boğa", "ayı"):
            assert yasak not in blok.lower(), yasak

    def test_yokluk_sifirdan_ayrilir(self):
        js = self._js()
        assert "_yuzdeIsaretli(deger, hane)" in js
        nerede = js.index("_yuzdeIsaretli(deger, hane)")
        blok = js[nerede:nerede + 300]
        assert "'—'" in blok


@pytest.mark.skipif(__import__("shutil").which("node") is None,
                    reason="node yok")
class TestKartlarCalistirilarak:
    """`_yuzdeIsaretli` gerçekten çalıştırılıp denetleniyor."""

    def _cagir(self, deger, hane=2):
        import json as _json
        import os
        import subprocess
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(kok, "app", "static", "app.js"),
                  encoding="utf-8") as f:
            js = f.read()
        bas = js.index("_yuzdeIsaretli(deger, hane) {")
        derinlik, son = 0, bas
        for i in range(js.index("{", bas), len(js)):
            if js[i] == "{":
                derinlik += 1
            elif js[i] == "}":
                derinlik -= 1
                if derinlik == 0:
                    son = i + 1
                    break
        betik = ("const api = {%s};console.log(JSON.stringify("
                 "api._yuzdeIsaretli(%s, %d)));" % (js[bas:son],
                                                    _json.dumps(deger), hane))
        c = subprocess.run(["node", "-e", betik], capture_output=True,
                           text=True, encoding="utf-8",
                           timeout=30)
        assert c.returncode == 0, c.stderr
        return _json.loads(c.stdout.strip())

    def test_pozitif_isaret_alir(self):
        assert self._cagir(8.27) == "+8.27%"

    def test_negatif_oldugu_gibi(self):
        assert self._cagir(-5.30) == "-5.30%"

    def test_veri_yoksa_tire(self):
        """'%0.00' yazmak 'fonlama sıfır' demek olurdu."""
        assert self._cagir(None) == "—"

    def test_sifir_tire_degildir(self):
        """Gerçekten sıfırsa sıfır yazılmalı — yokluk değil."""
        assert self._cagir(0) == "0.00%"
