r"""
CoinTakip — FAZ F2 Testleri: Arşiv Deposu

Arşivin varlık sebebi: borsaların geçmiş penceresi KAYIYOR (Binance ~2 yıl,
MEXC 1 ay), yani bugün alınmayan veri yarın alınamıyor. Arşiv "bir kez
gördüğümüzü bir daha bırakmama" katmanıdır.

Bu testler üç şeyi güvence altına alır:

  1. Arşiv doğru veriyi yazıyor ve doğru okuyor.
  2. **Arşiv uygulamayı ASLA düşürmüyor.** Kritik yol değil, konfor katmanı.
     Disk dolsa, dosya bozulsa, izin olmasa bile portföy çalışmaya devam eder.
  3. Eksik günler gizlenmiyor — sessizce eksik veriyle devam etmek, hiç veri
     olmamasından kötüdür.

conftest.py'deki `izole_veri` fixture'ı DATA_DIR'i geçici dizine çevirdiği ve
archive.archive_path() bunu ÇAĞRI ANINDA okuduğu için hiçbir test gerçek
data/archive.db dosyasına dokunmaz.
"""

import os
import sqlite3
from datetime import datetime, timedelta

import pytest

import archive
import data_manager as dm


def _metrics(data=None):
    from conftest import SAHTE_FIYATLAR
    if data is None:
        data = dm.load_portfolio()
    return dm.calculate_portfolio_metrics(data, dict(SAHTE_FIYATLAR))


def _fiyatlar():
    from conftest import SAHTE_FIYATLAR
    return dict(SAHTE_FIYATLAR)


def _gun_ekle(gun, **alanlar):
    """Test için belirli bir tarihe doğrudan kayıt basar."""
    archive.init_archive()
    with archive._connect() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO snapshots
                (taken_date, taken_at, taken_ts, source, total_equity_usd)
            VALUES (?,?,?,?,?)
        """, (gun, gun + "T12:00:00", 0.0, "test",
              alanlar.get("total_equity_usd", 1000.0)))


class TestSemaVeYol:

    def test_arsiv_izole_dizinde_olusur(self, kayitli_portfoy):
        """Gerçek data/archive.db'ye yazılmadığının kanıtı."""
        archive.init_archive()
        yol = archive.archive_path()
        assert os.path.exists(yol)
        assert "Claude_Projects" not in yol or "data\\archive.db" not in yol.replace("/", "\\")[-20:] \
            or yol != os.path.join("D:\\Claude_Projects\\CoinTakip", "data", "archive.db")

    def test_sema_idempotent(self, kayitli_portfoy):
        assert archive.init_archive() is True
        assert archive.init_archive() is True   # ikinci çağrı patlamamalı

    def test_beklenen_tablolar_var(self, kayitli_portfoy):
        archive.init_archive()
        with archive._connect() as conn:
            tablolar = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert {"snapshots", "snapshot_positions", "snapshot_locations", "meta"} <= tablolar

    def test_defter_json_olarak_KALIR(self, kayitli_portfoy):
        """
        Mimari sözleşme: arşiv SQLite'a gitti ama defter JSON kalmalı.
        README'de 'düz JSON dosyalarında saklanır' sözü verildi.
        """
        archive.write_snapshot(_metrics(), wallets={})
        assert os.path.exists(dm.DATA_FILE), "portfolio.json kayboldu."
        import json
        with open(dm.DATA_FILE, encoding="utf-8") as f:
            veri = json.load(f)
        assert len(veri["transactions"]) == 6, "Defter arşivden etkilendi."


class TestFotografYazma:

    def test_fotograf_toplam_kasayi_kaydeder(self, kayitli_portfoy):
        m = _metrics()
        sid = archive.write_snapshot(m, wallets=dm.load_portfolio()["wallets"])
        assert sid is not None

        seri = archive.net_worth_series()
        assert len(seri) == 1
        assert seri[0]["total_equity_usd"] == pytest.approx(m["kpis"]["total_kasa"], abs=0.01)

    def test_pozisyon_detayi_kaydedilir(self, kayitli_portfoy):
        archive.write_snapshot(_metrics(), wallets={})
        with archive._connect() as conn:
            satirlar = conn.execute(
                "SELECT symbol, qty, price, no_source FROM snapshot_positions").fetchall()
        semboller = {r["symbol"] for r in satirlar}
        assert "BTCUSDT" in semboller
        btc = next(r for r in satirlar if r["symbol"] == "BTCUSDT")
        assert btc["qty"] == pytest.approx(0.02)
        assert btc["price"] == pytest.approx(100000.0)

    def test_konum_kirilimi_kaydedilir(self, kayitli_portfoy):
        archive.write_snapshot(_metrics(), wallets={})
        with archive._connect() as conn:
            konumlar = {r["location"] for r in conn.execute(
                "SELECT location FROM snapshot_locations").fetchall()}
        assert "BINANCE" in konumlar
        assert "ALL" not in konumlar, "'ALL' bir konum değil, toplam satırı."

    def test_ayni_gun_ikinci_kayit_UZERINE_yazar(self, kayitli_portfoy):
        """Gün başına tek satır — eğri günde bir noktadan oluşmalı."""
        archive.write_snapshot(_metrics(), wallets={})
        archive.write_snapshot(_metrics(), wallets={})
        assert len(archive.net_worth_series()) == 1

    def test_tazeleme_eski_pozisyon_satirlarini_birakmaz(self, kayitli_portfoy):
        archive.write_snapshot(_metrics(), wallets={})
        with archive._connect() as conn:
            once = conn.execute("SELECT COUNT(*) c FROM snapshot_positions").fetchone()["c"]

        # Bir pozisyonu kapat, tekrar fotoğrafla
        dm.write_off_position("ETHUSDT@BINANCE")
        archive.write_snapshot(_metrics(), wallets={})
        with archive._connect() as conn:
            sonra = conn.execute("SELECT COUNT(*) c FROM snapshot_positions").fetchone()["c"]
        assert sonra == once - 1, "Eski pozisyon satırı arşivde hayalet olarak kaldı."

    def test_gerceklesmis_kz_kaydedilir(self, kayitli_portfoy):
        realize = dm.calculate_realized_metrics(dm.load_portfolio())
        archive.write_snapshot(_metrics(), wallets={},
                               realized_pnl_usd=realize["total_realized_pnl_usd"])
        seri = archive.net_worth_series()
        assert seri[0]["realized_pnl_usd"] == pytest.approx(
            realize["total_realized_pnl_usd"], abs=0.01)


class TestGunlukTetikleyici:

    def test_fiyat_yoksa_fotograf_ALINMAZ(self, kayitli_portfoy):
        """
        Uygulama yeni açıldığında fiyatlar henüz gelmemiş olur. O anda kayıt
        almak portföyü 'her şey kaynaksız' hâlde dondurup eğriyi bozardı.
        """
        sonuc = archive.maybe_write_daily_snapshot(_metrics(), live_prices={})
        assert sonuc is None
        assert archive.net_worth_series() == []

    def test_ilk_cagri_fotograf_alir(self, kayitli_portfoy):
        sid = archive.maybe_write_daily_snapshot(_metrics(), _fiyatlar())
        assert sid is not None
        assert len(archive.net_worth_series()) == 1

    def test_ttl_dolmadan_tekrar_yazmaz(self, kayitli_portfoy):
        archive.maybe_write_daily_snapshot(_metrics(), _fiyatlar())
        ikinci = archive.maybe_write_daily_snapshot(_metrics(), _fiyatlar())
        assert ikinci is None, "TTL dolmadan tekrar yazdı — gereksiz disk trafiği."

    def test_ttl_dolunca_ayni_gunu_tazeler(self, kayitli_portfoy, monkeypatch):
        archive.maybe_write_daily_snapshot(_metrics(), _fiyatlar())
        # Saati ileri al: TTL dolmuş say
        gercek = archive.time.time
        monkeypatch.setattr(archive.time, "time",
                            lambda: gercek() + archive.SNAPSHOT_REFRESH_TTL + 10)
        sid = archive.maybe_write_daily_snapshot(_metrics(), _fiyatlar())
        assert sid is not None
        assert len(archive.net_worth_series()) == 1, "Tazeleme yeni gün satırı açtı."


class TestOkumaSorgulari:

    def test_sembol_fiyat_gecmisi(self, kayitli_portfoy):
        """
        Arşivin asıl vaadi: delist olmuş bir coinin geçmiş fiyatını hiçbir API
        geri vermez, ama bizde kalır.
        """
        archive.write_snapshot(_metrics(), wallets={})
        gecmis = archive.symbol_price_history("BTCUSDT")
        assert len(gecmis) == 1
        assert gecmis[0]["price"] == pytest.approx(100000.0)

    def test_sembol_gecmisi_buyuk_kucuk_harf_duyarsiz(self, kayitli_portfoy):
        archive.write_snapshot(_metrics(), wallets={})
        assert len(archive.symbol_price_history("btcusdt")) == 1

    def test_olmayan_sembol_bos_liste_doner(self, kayitli_portfoy):
        archive.write_snapshot(_metrics(), wallets={})
        assert archive.symbol_price_history("YOKBOYLECOIN") == []

    def test_konum_serisi(self, kayitli_portfoy):
        archive.write_snapshot(_metrics(), wallets={})
        seri = archive.location_series()
        assert any(r["location"] == "BINANCE" for r in seri)

    def test_gun_filtresi_eski_kayitlari_eler(self, kayitli_portfoy):
        _gun_ekle((datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d"))
        _gun_ekle(datetime.now().strftime("%Y-%m-%d"))
        assert len(archive.net_worth_series()) == 2
        assert len(archive.net_worth_series(days=30)) == 1

    def test_seri_eskiden_yeniye_siralanir(self, kayitli_portfoy):
        _gun_ekle("2026-08-20")
        _gun_ekle("2026-08-25")
        _gun_ekle("2026-08-22")
        tarihler = [r["taken_date"] for r in archive.net_worth_series()]
        assert tarihler == sorted(tarihler)


class TestBoslukTespiti:
    """Uygulama kapalıyken kayıt oluşmaz. Bu gizlenmemeli."""

    def test_kesintisiz_gunlerde_bosluk_yok(self, kayitli_portfoy):
        for i in range(3):
            _gun_ekle((datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"))
        assert archive.find_gaps() == []

    def test_eksik_gunler_bulunur(self, kayitli_portfoy):
        _gun_ekle("2026-08-01")
        _gun_ekle("2026-08-05")
        bosluklar = archive.find_gaps()
        assert len(bosluklar) == 1
        assert bosluklar[0]["from"] == "2026-08-02"
        assert bosluklar[0]["to"] == "2026-08-04"
        assert bosluklar[0]["missing_days"] == 3

    def test_tek_kayitla_bosluk_hesaplanmaz(self, kayitli_portfoy):
        _gun_ekle("2026-08-01")
        assert archive.find_gaps() == []

    def test_durum_ozeti_boslugu_raporlar(self, kayitli_portfoy):
        _gun_ekle("2026-08-01")
        _gun_ekle("2026-08-10")
        durum = archive.archive_status()
        assert durum["snapshot_count"] == 2
        assert durum["first_date"] == "2026-08-01"
        assert durum["last_date"] == "2026-08-10"
        assert durum["gap_count"] == 1
        assert durum["missing_days_total"] == 8

    def test_bos_arsiv_durumu_patlamaz(self, kayitli_portfoy):
        durum = archive.archive_status()
        assert durum["snapshot_count"] == 0
        assert durum["gaps"] == []


class TestArsivUygulamayiDUSURMEZ:
    """
    En önemli bölüm. Arşiv konfor katmanıdır; bozulursa portföy, fiyatlar ve
    KPI'lar çalışmaya DEVAM etmeli.
    """

    def test_yazma_hatasi_yutulur(self, kayitli_portfoy, monkeypatch):
        def patlat(*a, **k):
            raise sqlite3.OperationalError("disk dolu")
        monkeypatch.setattr(archive, "_connect", patlat)
        assert archive.write_snapshot(_metrics(), wallets={}) is None

    def test_okuma_hatasi_bos_liste_doner(self, kayitli_portfoy, monkeypatch):
        def patlat(*a, **k):
            raise sqlite3.DatabaseError("dosya bozuk")
        monkeypatch.setattr(archive, "_connect", patlat)
        assert archive.net_worth_series() == []
        assert archive.symbol_price_history("BTCUSDT") == []
        assert archive.location_series() == []
        assert archive.find_gaps() == []

    def test_bozuk_arsivde_durum_enabled_false_doner(self, kayitli_portfoy, monkeypatch):
        monkeypatch.setattr(archive, "init_archive", lambda: False)

        def patlat(*a, **k):
            raise sqlite3.DatabaseError("bozuk")
        monkeypatch.setattr(archive, "_connect", patlat)
        durum = archive.archive_status()
        assert durum["enabled"] is False

    def test_gunluk_tetikleyici_hatayi_yutar(self, kayitli_portfoy, monkeypatch):
        def patlat(*a, **k):
            raise OSError("izin yok")
        monkeypatch.setattr(archive, "son_kayit_bilgisi", patlat)
        assert archive.maybe_write_daily_snapshot(_metrics(), _fiyatlar()) is None

    def test_arsiv_bozukken_portfoy_ucu_calisir(self, client, monkeypatch):
        """Asıl güvence: arşiv çökse bile kullanıcı portföyünü görebilmeli."""
        def patlat(*a, **k):
            raise sqlite3.OperationalError("disk dolu")
        monkeypatch.setattr(archive, "_connect", patlat)

        r = client.get("/api/portfolio")
        assert r.status_code == 200
        assert r.json()["kpis"]["total_kasa"] > 0


class TestApiUclari:

    def test_durum_ucu_calisir(self, client):
        r = client.get("/api/archive/status")
        assert r.status_code == 200
        assert "snapshot_count" in r.json()

    def test_portfoy_ucu_otomatik_fotograf_alir(self, client):
        client.get("/api/portfolio")
        r = client.get("/api/archive/status")
        assert r.json()["snapshot_count"] == 1, \
            "Portföy görüntülendiği hâlde arşive kayıt düşmedi."

    def test_networth_ucu_seri_doner(self, client):
        client.get("/api/portfolio")
        r = client.get("/api/archive/networth")
        assert r.status_code == 200
        assert len(r.json()["series"]) == 1

    def test_elle_fotograf_ucu_calisir(self, client):
        r = client.post("/api/archive/snapshot")
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_fiyat_yokken_elle_fotograf_400_doner(self, client, monkeypatch):
        import price_service as ps
        monkeypatch.setattr(ps.price_service, "prices", {})
        r = client.post("/api/archive/snapshot")
        assert r.status_code == 400
        assert "Canlı fiyat yok" in r.json()["detail"]

    def test_fiyat_gecmisi_ucu_calisir(self, client):
        client.get("/api/portfolio")
        r = client.get("/api/archive/price-history/BTCUSDT")
        assert r.status_code == 200
        assert r.json()["symbol"] == "BTCUSDT"
        assert len(r.json()["history"]) == 1

    def test_konum_serisi_ucu_calisir(self, client):
        client.get("/api/portfolio")
        r = client.get("/api/archive/locations")
        assert r.status_code == 200
        assert any(x["location"] == "BINANCE" for x in r.json()["series"])
