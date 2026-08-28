r"""
CoinTakip — FAZ F5 Testleri: Mutabakat Düzeltmesi

En kritik güvenceler:

1. **Öneri üretmek deftere hiçbir şey yazmaz.** F3'ün salt okunurluğu F5 ile
   bozulmadı; yazma yalnızca `apply_rebuild` çağrıldığında olur.

2. **Kapsamı kanıtlanamayan pozisyon için öneri verilmez.** Yanlış bir maliyet
   tabanı, eksik olandan zararlıdır: kullanıcı ona güvenir.

3. **Geçmiş satışların gerçekleşmiş K/Z'si kaybolmaz.** FIFO'da hayatta kalan
   lotlar en son (ve düşen bir coinde en ucuz) alımlardır. Yalnızca açık lotları
   düzeltirsek pozisyon ucuzlar ve sistem gerçekte olduğundan kârlı görünür.

4. **Her düzeltme birebir geri alınabilir.** Uygula → geri al turundan sonra
   defter, miktarına ve gerçekleşmiş K/Z'sine kadar başladığı yerde olmalı.

Testler sentetik dosyalar üretir; `izole_veri` fixture'ı sayesinde gerçek
portföye dokunmaz.
"""

import csv
import os

import pytest

import data_manager as dm
import reconcile as rc


# =====================================================================
# Yardımcılar
# =====================================================================
def _trades(dizin, satirlar):
    """Binance spot işlem dosyası üretir. Satır: (zaman, çift, yön, fiyat, dolan, tutar, komisyon)"""
    yol = os.path.join(dizin, "Binance-Spot-Trade-History-test-part1-of1.csv")
    with open(yol, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Time", "Pair", "Side", "Price", "Executed", "Amount", "Fee"])
        w.writerows(satirlar)
    return yol


def _withdraw(dizin, satirlar):
    yol = os.path.join(dizin, "Binance-Withdraw-History-test-part1-of1.csv")
    with open(yol, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Time", "Coin", "Network", "Amount", "Fee", "Address", "TXID", "Status"])
        w.writerows(satirlar)
    return yol


def _deposit(dizin, satirlar):
    yol = os.path.join(dizin, "Binance-Deposit-History-test-part1-of1.csv")
    with open(yol, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Time", "Coin", "Network", "Amount", "Address", "TXID", "Status"])
        w.writerows(satirlar)
    return yol


def _defter(lotlar, coin="ABCUSDT", exchange="BINANCE"):
    """Kullanıcının elle girdiği defter — tıpkı gerçeğindeki gibi satış kaydı YOK."""
    data = dm.load_portfolio()
    data["transactions"] = []
    for i, (tarih, qty, cost) in enumerate(lotlar, start=1):
        data["transactions"].append({
            "id": i, "date": tarih, "coin": coin, "exchange": exchange,
            "qty": qty, "cost": cost, "status": dm.ACTIVE_STATUS,
            "category": "Altcoin", "cost_method": "Konsolide Ortalama",
        })
    dm.save_portfolio(data)
    return dm.load_portfolio()


def _satir(plan, pos_key):
    return next(r for r in plan["rows"] if r["pos_key"] == pos_key)


@pytest.fixture
def dizin(tmp_path):
    d = tmp_path / "borsa_exports"
    d.mkdir(parents=True)
    return str(d)


# =====================================================================
# BÖLÜM 1 — FIFO YENİDEN KURULUMU
# =====================================================================
class TestFifoKurulumu:

    def test_satilmamis_alimlar_lot_olarak_kalir(self):
        olaylar = [
            rc._olay("BINANCE", "2024-01-01T10:00:00", "TRADE", "ABC", 100.0,
                     usd_value=200.0, usd_known=True, price=2.0),
            rc._olay("BINANCE", "2024-02-01T10:00:00", "TRADE", "ABC", 50.0,
                     usd_value=50.0, usd_known=True, price=1.0),
        ]
        lotlar, tani = rc.fifo_rebuild(olaylar)
        assert len(lotlar) == 2
        assert lotlar[0]["qty"] == 100.0 and lotlar[0]["cost"] == 2.0
        assert lotlar[1]["qty"] == 50.0 and lotlar[1]["cost"] == 1.0
        assert tani["oversold_qty"] == 0.0

    def test_fifo_once_eski_lotu_tuketir(self):
        """Hayatta kalan lot en SON alım olmalı — F5'in tüm mantığı buna dayanır."""
        olaylar = [
            rc._olay("BINANCE", "2024-01-01T10:00:00", "TRADE", "ABC", 100.0,
                     usd_value=1000.0, usd_known=True, price=10.0),
            rc._olay("BINANCE", "2024-06-01T10:00:00", "TRADE", "ABC", 100.0,
                     usd_value=100.0, usd_known=True, price=1.0),
            rc._olay("BINANCE", "2024-07-01T10:00:00", "TRADE", "ABC", -100.0,
                     usd_value=150.0, usd_known=True, price=1.5),
        ]
        lotlar, tani = rc.fifo_rebuild(olaylar)
        assert len(lotlar) == 1
        assert lotlar[0]["date"] == "2024-06-01"
        assert lotlar[0]["cost"] == 1.0

    def test_birim_maliyet_net_miktardan_hesaplanir(self):
        """Komisyon coin'in kendisinden alındıysa ödenen para daha az tokene bölünür."""
        olay = rc._olay("BINANCE", "2024-01-01T10:00:00", "TRADE", "ABC", 99.0,
                        usd_value=100.0, usd_known=True, price=1.0)
        maliyet, bilinir = rc._birim_maliyet(olay)
        assert bilinir is True
        assert maliyet == pytest.approx(100.0 / 99.0)

    def test_dolara_sabitli_olmayan_kotasyonda_maliyet_bilinmez(self):
        olay = rc._olay("BINANCE", "2024-01-01T10:00:00", "TRADE", "ABC", 10.0,
                        usd_known=False, price=0.001, quote_asset="BTC")
        maliyet, bilinir = rc._birim_maliyet(olay)
        assert bilinir is False and maliyet == 0.0

    def test_karsiliksiz_satis_fazla_satis_olarak_isaretlenir(self):
        """Alım penceresinden önce yapılmışsa dosyada karşılığı yoktur."""
        olaylar = [
            rc._olay("BINANCE", "2024-01-01T10:00:00", "TRADE", "ABC", -50.0,
                     usd_value=100.0, usd_known=True, price=2.0),
        ]
        lotlar, tani = rc.fifo_rebuild(olaylar)
        assert lotlar == []
        assert tani["oversold_qty"] == pytest.approx(50.0)

    def test_yatirma_maliyeti_bilinmeyen_lot_uretir(self):
        olaylar = [
            rc._olay("BINANCE", "2024-01-01T10:00:00", "DEPOSIT", "ABC", 100.0),
        ]
        lotlar, tani = rc.fifo_rebuild(olaylar)
        assert lotlar[0]["cost_known"] is False
        assert tani["unknown_cost_qty"] == pytest.approx(100.0)

    def test_ayni_gun_once_alim_sonra_satim_islenir(self):
        """Ters sıra sahte açığa satış üretir ve kapsam boşluğu sanılırdı."""
        olaylar = [
            rc._olay("BINANCE", "2024-01-01T00:00:00", "TRADE", "ABC", -60.0,
                     usd_value=120.0, usd_known=True, price=2.0),
            rc._olay("BINANCE", "2024-01-01T00:00:00", "TRADE", "ABC", 100.0,
                     usd_value=100.0, usd_known=True, price=1.0),
        ]
        lotlar, tani = rc.fifo_rebuild(olaylar)
        assert tani["oversold_qty"] == 0.0
        assert lotlar[0]["qty"] == pytest.approx(40.0)

    def test_imza_lotlar_degisince_degisir(self):
        a = [{"date": "2024-01-01", "qty": 10.0, "cost": 1.0}]
        b = [{"date": "2024-01-01", "qty": 10.0, "cost": 2.0}]
        assert rc.lot_signature(a) == rc.lot_signature(a)
        assert rc.lot_signature(a) != rc.lot_signature(b)


# =====================================================================
# BÖLÜM 2 — GERÇEKLEŞMİŞ K/Z
# =====================================================================
class TestGerceklesmisKz:

    def test_kapanmis_tur_islemin_kz_si_hesaplanir(self):
        olaylar = [
            rc._olay("BINANCE", "2024-01-01T10:00:00", "TRADE", "ABC", 100.0,
                     usd_value=1000.0, usd_known=True, price=10.0),
            rc._olay("BINANCE", "2024-07-01T10:00:00", "TRADE", "ABC", -100.0,
                     usd_value=400.0, usd_known=True, price=4.0),
        ]
        _, tani = rc.fifo_rebuild(olaylar)
        assert tani["realized_qty"] == pytest.approx(100.0)
        assert tani["realized_cost_usd"] == pytest.approx(1000.0)
        assert tani["realized_proceeds_usd"] == pytest.approx(400.0)
        assert tani["realized_pnl_usd"] == pytest.approx(-600.0)
        assert tani["realized_known"] is True

    def test_cekilen_miktar_kz_uretmez(self):
        """Çekim satış değildir — coin yer değiştirdi, kaybedilmedi."""
        olaylar = [
            rc._olay("BINANCE", "2024-01-01T10:00:00", "TRADE", "ABC", 100.0,
                     usd_value=1000.0, usd_known=True, price=10.0),
            rc._olay("BINANCE", "2024-07-01T10:00:00", "WITHDRAW", "ABC", -100.0),
        ]
        _, tani = rc.fifo_rebuild(olaylar)
        assert tani["realized_qty"] == 0.0
        assert tani["realized_pnl_usd"] == 0.0
        assert tani["withdrawn_qty"] == pytest.approx(100.0)
        # Çekilen coinlerin maliyeti kullanıcıya bildirilir; başka konumda duruyor.
        assert tani["withdrawn_cost_usd"] == pytest.approx(1000.0)

    def test_dolara_cevrilemeyen_satis_kz_yi_guvenilmez_yapar(self):
        olaylar = [
            rc._olay("BINANCE", "2024-01-01T10:00:00", "TRADE", "ABC", 100.0,
                     usd_value=1000.0, usd_known=True, price=10.0),
            rc._olay("BINANCE", "2024-07-01T10:00:00", "TRADE", "ABC", -100.0,
                     usd_known=False, price=0.001, quote_asset="BTC"),
        ]
        _, tani = rc.fifo_rebuild(olaylar)
        assert tani["realized_known"] is False
        assert tani["realized_unknown_trades"] == 1


# =====================================================================
# BÖLÜM 3 — PLAN ÜRETİMİ
# =====================================================================
class TestPlanUretimi:

    def test_plan_deftere_hicbir_sey_yazmaz(self, dizin):
        _trades(dizin, [
            ["2024-01-01 10:00:00", "ABCUSDT", "BUY", "1.0", "100ABC", "100USDT", "0USDT"],
        ])
        data = _defter([("2026-01-01", 100.0, 5.0)])
        once = dm.load_portfolio()
        rc.build_rebuild_plan(data, dizin)
        assert dm.load_portfolio() == once

    def test_plan_read_only_bayragi_tasir(self, dizin):
        _trades(dizin, [["2024-01-01 10:00:00", "ABCUSDT", "BUY", "1.0", "100ABC", "100USDT", "0USDT"]])
        plan = rc.build_rebuild_plan(_defter([("2026-01-01", 100.0, 5.0)]), dizin)
        assert plan["read_only"] is True

    def test_hayatta_kalan_lotlar_gercek_tarih_ve_fiyatla_onerilir(self, dizin):
        _trades(dizin, [
            ["2024-01-01 10:00:00", "ABCUSDT", "BUY",  "10.0", "100ABC", "1000USDT", "0USDT"],
            ["2024-06-01 10:00:00", "ABCUSDT", "BUY",  "1.0",  "100ABC", "100USDT",  "0USDT"],
            ["2024-07-01 10:00:00", "ABCUSDT", "SELL", "4.0",  "100ABC", "400USDT",  "0USDT"],
        ])
        # Kullanıcı 100 adedi ortalama 5.5'ten girmiş (yanlış).
        plan = rc.build_rebuild_plan(_defter([("2026-01-01", 100.0, 5.5)]), dizin)
        r = _satir(plan, "ABCUSDT@BINANCE")
        assert r["proposed_qty"] == pytest.approx(100.0)
        assert r["proposed_lots"][0]["date"] == "2024-06-01"
        assert r["proposed_lots"][0]["cost"] == pytest.approx(1.0)
        assert r["proposed_invested"] == pytest.approx(100.0)

    def test_stablecoin_icin_oneri_uretilmez(self, dizin):
        _trades(dizin, [["2024-01-01 10:00:00", "ABCUSDT", "BUY", "1.0", "100ABC", "100USDT", "0USDT"]])
        plan = rc.build_rebuild_plan(_defter([("2026-01-01", 100.0, 1.0)]), dizin)
        assert not any(r["asset"] in rc.STABLE_QUOTES for r in plan["rows"])

    def test_borsalar_ayri_pozisyon_olarak_ele_alinir(self, dizin):
        """BINANCE'teki ABC ile MEXC'teki ABC ayrı maliyet tabanı taşır."""
        _trades(dizin, [["2024-01-01 10:00:00", "ABCUSDT", "BUY", "1.0", "100ABC", "100USDT", "0USDT"]])
        data = dm.load_portfolio()
        data["transactions"] = [
            {"id": 1, "date": "2026-01-01", "coin": "ABCUSDT", "exchange": "BINANCE",
             "qty": 100.0, "cost": 5.0, "status": dm.ACTIVE_STATUS},
            {"id": 2, "date": "2026-01-01", "coin": "ABCUSDT", "exchange": "MEXC",
             "qty": 50.0, "cost": 3.0, "status": dm.ACTIVE_STATUS},
        ]
        dm.save_portfolio(data)
        plan = rc.build_rebuild_plan(dm.load_portfolio(), dizin)
        anahtarlar = [r["pos_key"] for r in plan["rows"]]
        assert "ABCUSDT@BINANCE" in anahtarlar
        # MEXC için dosya yok → kapsanmayan konum, öneri üretilmez.
        assert "ABCUSDT@MEXC" not in anahtarlar


class TestEngeller:

    def test_karsiliksiz_satis_oneriyi_engeller(self, dizin):
        _trades(dizin, [
            ["2024-01-01 10:00:00", "ABCUSDT", "BUY",  "1.0", "50ABC",  "50USDT",  "0USDT"],
            ["2024-02-01 10:00:00", "ABCUSDT", "SELL", "2.0", "200ABC", "400USDT", "0USDT"],
        ])
        plan = rc.build_rebuild_plan(_defter([("2026-01-01", 100.0, 1.0)]), dizin)
        r = _satir(plan, "ABCUSDT@BINANCE")
        assert r["status"] == "blocked"
        assert any("karşılıksız çıkış" in b for b in r["blockers"])

    def test_maliyeti_bilinmeyen_yatirma_oneriyi_engeller(self, dizin):
        _trades(dizin, [["2024-01-01 10:00:00", "XYZUSDT", "BUY", "1.0", "1XYZ", "1USDT", "0USDT"]])
        _deposit(dizin, [["2024-02-01 10:00:00", "ABC", "BSC", "100", "0xaaa", "0xbbb", "Completed"]])
        plan = rc.build_rebuild_plan(_defter([("2026-01-01", 100.0, 1.0)]), dizin)
        r = _satir(plan, "ABCUSDT@BINANCE")
        assert r["status"] == "blocked"
        assert any("maliyetini bilmiyor" in b for b in r["blockers"])

    def test_defter_dosyadan_eskiyse_engellenir(self, dizin):
        _trades(dizin, [["2024-06-01 10:00:00", "ABCUSDT", "BUY", "1.0", "100ABC", "100USDT", "0USDT"]])
        # Kullanıcı 2023'te aldığını söylüyor; dosya 2024-06'da başlıyor.
        plan = rc.build_rebuild_plan(_defter([("2023-01-01", 100.0, 5.0)]), dizin)
        r = _satir(plan, "ABCUSDT@BINANCE")
        assert r["status"] == "blocked"
        assert any("dosya ise" in b for b in r["blockers"])

    def test_engellenen_pozisyon_uygulanamaz(self, dizin):
        _trades(dizin, [
            ["2024-01-01 10:00:00", "ABCUSDT", "BUY",  "1.0", "50ABC",  "50USDT",  "0USDT"],
            ["2024-02-01 10:00:00", "ABCUSDT", "SELL", "2.0", "200ABC", "400USDT", "0USDT"],
        ])
        _defter([("2026-01-01", 100.0, 1.0)])
        with pytest.raises(ValueError, match="düzeltilemez"):
            dm.apply_rebuild("ABCUSDT@BINANCE", root=dizin)


class TestIkazlar:

    def test_cekim_ikaz_uretir_ama_engellemez(self, dizin):
        _trades(dizin, [
            ["2024-01-01 10:00:00", "ABCUSDT", "BUY", "1.0", "200ABC", "200USDT", "0USDT"],
        ])
        _withdraw(dizin, [["2024-03-01 10:00:00", "ABC", "BSC", "100", "0", "0xaaa", "0xbbb", "Completed"]])
        plan = rc.build_rebuild_plan(_defter([("2026-01-01", 200.0, 1.0)]), dizin)
        r = _satir(plan, "ABCUSDT@BINANCE")
        assert r["status"] == "caution"
        assert any("çekilmiş" in w for w in r["warnings"])
        assert r["proposed_qty"] == pytest.approx(100.0)

    def test_kz_yazimi_ikaz_degil_etkidir(self, dizin):
        """'Şu olacak' bir uyarı değildir; ikisi ayrı listede durmalı."""
        _trades(dizin, [
            ["2024-01-01 10:00:00", "ABCUSDT", "BUY",  "10.0", "100ABC", "1000USDT", "0USDT"],
            ["2024-06-01 10:00:00", "ABCUSDT", "BUY",  "1.0",  "100ABC", "100USDT",  "0USDT"],
            ["2024-07-01 10:00:00", "ABCUSDT", "SELL", "4.0",  "100ABC", "400USDT",  "0USDT"],
        ])
        plan = rc.build_rebuild_plan(_defter([("2026-01-01", 100.0, 5.5)]), dizin)
        r = _satir(plan, "ABCUSDT@BINANCE")
        assert r["status"] == "ready"
        assert r["will_book_realized"] is True
        assert any("gerçekleşmiş" in e for e in r["effects"])
        assert r["warnings"] == []

    def test_defterde_satis_varsa_kz_yazilmaz(self, dizin):
        """Mükerrer K/Z, eksik K/Z'den daha zararlıdır."""
        _trades(dizin, [
            ["2024-01-01 10:00:00", "ABCUSDT", "BUY",  "10.0", "100ABC", "1000USDT", "0USDT"],
            ["2024-06-01 10:00:00", "ABCUSDT", "BUY",  "1.0",  "100ABC", "100USDT",  "0USDT"],
            ["2024-07-01 10:00:00", "ABCUSDT", "SELL", "4.0",  "100ABC", "400USDT",  "0USDT"],
        ])
        data = _defter([("2026-01-01", 100.0, 5.5)])
        data["transactions"].append({
            "id": 99, "date": "2026-01-05", "coin": "ABCUSDT", "exchange": "BINANCE",
            "qty": 10.0, "cost": 5.0, "status": dm.CLOSED_STATUS,
            "exit_price": 4.0, "exit_date": "2026-02-01", "realized_pnl_usd": -10.0,
        })
        dm.save_portfolio(data)
        plan = rc.build_rebuild_plan(dm.load_portfolio(), dizin)
        r = _satir(plan, "ABCUSDT@BINANCE")
        assert r["will_book_realized"] is False
        assert any("YAZILMAYACAK" in w for w in r["warnings"])


# =====================================================================
# BÖLÜM 4 — UYGULAMA
# =====================================================================
class TestUygulama:

    @pytest.fixture
    def hazir(self, dizin):
        """100 pahalı + 100 ucuz alım, 100 satış. Defterde tek yanlış lot var."""
        _trades(dizin, [
            ["2024-01-01 10:00:00", "ABCUSDT", "BUY",  "10.0", "100ABC", "1000USDT", "0USDT"],
            ["2024-06-01 10:00:00", "ABCUSDT", "BUY",  "1.0",  "100ABC", "100USDT",  "0USDT"],
            ["2024-07-01 10:00:00", "ABCUSDT", "SELL", "4.0",  "100ABC", "400USDT",  "0USDT"],
        ])
        _defter([("2026-01-01", 100.0, 5.5)])
        return dizin

    def test_lotlar_gercek_tarih_ve_maliyetle_yeniden_kurulur(self, hazir):
        dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir)
        data = dm.load_portfolio()
        aktif = [t for t in data["transactions"] if t.get("status") == dm.ACTIVE_STATUS]
        assert len(aktif) == 1
        assert aktif[0]["date"] == "2024-06-01"
        assert aktif[0]["cost"] == pytest.approx(1.0)
        assert aktif[0]["qty"] == pytest.approx(100.0)
        assert aktif[0]["type"] == "DÜZELTME"

    def test_eski_lotlar_silinmez_kapatilir(self, hazir):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir)
        data = dm.load_portfolio()
        eski = next(t for t in data["transactions"] if int(t["id"]) == 1)
        assert eski["status"] == dm.CLOSED_STATUS
        assert eski["rebuild_out_id"] == kayit["id"]
        assert eski["close_reason"] == "rebuild"

    def test_kapatilan_lot_sahte_kz_uretmez(self, hazir):
        """Düzeltme ekonomik bir olay değil, kayıt düzeltmesidir."""
        dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir)
        data = dm.load_portfolio()
        eski = next(t for t in data["transactions"] if int(t["id"]) == 1)
        assert eski.get("exit_price") is None
        assert eski.get("realized_pnl_usd") is None

    def test_gecmis_satisin_kz_si_deftere_gecer(self, hazir):
        """Bu yazılmazsa pozisyon ucuzlar ve tablo olduğundan iyi görünür."""
        once = dm.calculate_realized_metrics(dm.load_portfolio())["total_realized_pnl_usd"]
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir)
        sonra = dm.calculate_realized_metrics(dm.load_portfolio())["total_realized_pnl_usd"]
        # 100 adet 10$'dan alınıp 4$'dan satıldı → 600$ zarar.
        assert kayit["realized"]["booked"] is True
        assert kayit["realized"]["pnl_usd"] == pytest.approx(-600.0)
        assert (sonra - once) == pytest.approx(-600.0)

    def test_kapatilan_lotlar_izlenen_pozisyon_listesinde_gorunmez(self, hazir):
        """Aynı varlığı iki kez saydırırdı."""
        dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir)
        data = dm.load_portfolio()
        eski = next(t for t in data["transactions"] if int(t["id"]) == 1)
        assert dm._defter_artigi_mi(eski) is True

    def test_nakit_bakiyesi_degismez(self, hazir):
        once = dm.load_portfolio().get("wallets", {})
        dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir)
        assert dm.load_portfolio().get("wallets", {}) == once

    def test_denetim_kaydi_oncesi_ve_sonrasi_tasir(self, hazir):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, note="test notu")
        assert kayit["before"]["qty"] == pytest.approx(100.0)
        assert kayit["before"]["invested"] == pytest.approx(550.0)
        assert kayit["after"]["invested"] == pytest.approx(100.0)
        assert kayit["note"] == "test notu"
        assert kayit["pos_key"] == "ABCUSDT@BINANCE"
        assert len(dm.list_rebuilds()) == 1

    def test_imza_uyusmazsa_reddedilir(self, hazir):
        with pytest.raises(ValueError, match="Öneri değişmiş"):
            dm.apply_rebuild("ABCUSDT@BINANCE", signature="sahte", root=hazir)

    def test_dogru_imza_kabul_edilir(self, hazir):
        plan = rc.build_rebuild_plan(dm.load_portfolio(), hazir)
        r = _satir(plan, "ABCUSDT@BINANCE")
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", signature=r["signature"], root=hazir)
        assert kayit["signature"] == r["signature"]

    def test_bilinmeyen_pozisyon_hata_verir(self, hazir):
        with pytest.raises(ValueError, match="önerisi yok"):
            dm.apply_rebuild("YOKUSDT@BINANCE", root=hazir)

    def test_zaten_uyumlu_pozisyon_uygulanamaz(self, dizin):
        _trades(dizin, [["2024-01-01 10:00:00", "ABCUSDT", "BUY", "1.0", "100ABC", "100USDT", "0USDT"]])
        _defter([("2026-01-01", 100.0, 1.0)])
        with pytest.raises(ValueError, match="zaten borsa kayıtlarıyla aynı"):
            dm.apply_rebuild("ABCUSDT@BINANCE", root=dizin)

    def test_borsada_kalmayan_pozisyon_kapatilir(self, dizin):
        _trades(dizin, [
            ["2024-01-01 10:00:00", "ABCUSDT", "BUY",  "1.0", "100ABC", "100USDT", "0USDT"],
            ["2024-02-01 10:00:00", "ABCUSDT", "SELL", "2.0", "100ABC", "200USDT", "0USDT"],
        ])
        _defter([("2026-01-01", 100.0, 1.0)])
        dm.apply_rebuild("ABCUSDT@BINANCE", root=dizin)
        data = dm.load_portfolio()
        assert [t for t in data["transactions"] if t.get("status") == dm.ACTIVE_STATUS] == []


# =====================================================================
# BÖLÜM 5 — GERİ ALMA
# =====================================================================
class TestGeriAlma:

    @pytest.fixture
    def hazir(self, dizin):
        _trades(dizin, [
            ["2024-01-01 10:00:00", "ABCUSDT", "BUY",  "10.0", "100ABC", "1000USDT", "0USDT"],
            ["2024-06-01 10:00:00", "ABCUSDT", "BUY",  "1.0",  "100ABC", "100USDT",  "0USDT"],
            ["2024-07-01 10:00:00", "ABCUSDT", "SELL", "4.0",  "100ABC", "400USDT",  "0USDT"],
        ])
        _defter([("2026-01-01", 100.0, 5.5)])
        return dizin

    def test_uygula_geri_al_turu_defteri_aynen_birakir(self, hazir):
        once = dm.load_portfolio()
        once_islem = sorted(once["transactions"], key=lambda t: int(t["id"]))
        once_kz = dm.calculate_realized_metrics(once)["total_realized_pnl_usd"]

        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir)
        dm.undo_rebuild(kayit["id"])

        sonra = dm.load_portfolio()
        sonra_islem = sorted(sonra["transactions"], key=lambda t: int(t["id"]))
        assert len(sonra_islem) == len(once_islem)
        for a, b in zip(once_islem, sonra_islem):
            assert a["id"] == b["id"]
            assert a["qty"] == pytest.approx(b["qty"])
            assert a["cost"] == pytest.approx(b["cost"])
            assert a["status"] == b["status"]
        assert dm.calculate_realized_metrics(sonra)["total_realized_pnl_usd"] == pytest.approx(once_kz)
        assert sonra["rebuilds"] == []

    def test_geri_alma_kz_ozetini_de_siler(self, hazir):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir)
        kz_id = kayit["realized"]["tx_id"]
        assert kz_id is not None
        dm.undo_rebuild(kayit["id"])
        data = dm.load_portfolio()
        assert not any(int(t["id"]) == int(kz_id) for t in data["transactions"])

    def test_geri_alma_eski_lotu_aktife_dondurur(self, hazir):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir)
        dm.undo_rebuild(kayit["id"])
        eski = next(t for t in dm.load_portfolio()["transactions"] if int(t["id"]) == 1)
        assert eski["status"] == dm.ACTIVE_STATUS
        assert "rebuild_out_id" not in eski
        assert "close_reason" not in eski

    def test_olusan_lot_satildiysa_geri_alinamaz(self, hazir):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir)
        data = dm.load_portfolio()
        yeni = next(t for t in data["transactions"]
                    if int(t["id"]) == int(kayit["created_tx_ids"][0]))
        yeni["status"] = dm.CLOSED_STATUS
        dm.save_portfolio(data)
        with pytest.raises(ValueError, match="satılmış veya kapatılmış"):
            dm.undo_rebuild(kayit["id"])

    def test_olusan_lot_silindiyse_geri_alinamaz(self, hazir):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir)
        data = dm.load_portfolio()
        hedef = int(kayit["created_tx_ids"][0])
        data["transactions"] = [t for t in data["transactions"] if int(t["id"]) != hedef]
        dm.save_portfolio(data)
        with pytest.raises(ValueError, match="silinmiş"):
            dm.undo_rebuild(kayit["id"])

    def test_olmayan_kayit_hata_verir(self):
        with pytest.raises(ValueError, match="bulunamadı"):
            dm.undo_rebuild(9999)


# =====================================================================
# BÖLÜM 6 — ŞEMA VE API
# =====================================================================
class TestSemaVeApi:

    def test_eski_portfoy_dosyasina_rebuilds_eklenir(self):
        data = dm._ensure_schema({"transactions": []})
        assert data["rebuilds"] == []
        assert data["next_rebuild_id"] == 1

    def test_mevcut_kayitlar_id_sayacini_bozmaz(self):
        data = dm._ensure_schema({"transactions": [], "rebuilds": [{"id": 7}]})
        assert data["next_rebuild_id"] == 8

    def test_api_plan_ucu_calisir(self, client):
        r = client.get("/api/reconcile/rebuild")
        assert r.status_code == 200
        govde = r.json()
        assert govde["read_only"] is True
        assert "rows" in govde and "status_counts" in govde

    def test_api_rebuilds_listesi_bos_baslar(self, client):
        r = client.get("/api/rebuilds")
        assert r.status_code == 200
        assert r.json()["rebuilds"] == []

    def test_api_bilinmeyen_pozisyon_404(self, client):
        r = client.post("/api/reconcile/rebuild/YOKUSDT@BINANCE", json={})
        assert r.status_code == 404

    def test_api_olmayan_kayit_geri_alinamaz(self, client):
        r = client.post("/api/rebuilds/9999/undo")
        assert r.status_code == 404
