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


def _hesap_defteri(dizin, satirlar):
    """
    Binance hesap defteri (Transaction History) üretir.
    Satır: (zaman, hesap, işlem, coin, değişim) — 'Remark' boş bırakılır.
    """
    yol = os.path.join(dizin, "Binance-Transaction-History-test-part1-of1.csv")
    with open(yol, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["User ID", "Time", "Account", "Operation", "Coin", "Change", "Remark"])
        for zaman, hesap, islem, coin, degisim in satirlar:
            w.writerow(["1", zaman, hesap, islem, coin, degisim, ""])
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
        assert r["status"] == "needs_check"
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
        dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, verified_qty=100.0)
        data = dm.load_portfolio()
        aktif = [t for t in data["transactions"] if t.get("status") == dm.ACTIVE_STATUS]
        assert len(aktif) == 1
        assert aktif[0]["date"] == "2024-06-01"
        assert aktif[0]["cost"] == pytest.approx(1.0)
        assert aktif[0]["qty"] == pytest.approx(100.0)
        assert aktif[0]["type"] == "DÜZELTME"

    def test_eski_lotlar_silinmez_kapatilir(self, hazir):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, verified_qty=100.0)
        data = dm.load_portfolio()
        eski = next(t for t in data["transactions"] if int(t["id"]) == 1)
        assert eski["status"] == dm.CLOSED_STATUS
        assert eski["rebuild_out_id"] == kayit["id"]
        assert eski["close_reason"] == "rebuild"

    def test_kapatilan_lot_sahte_kz_uretmez(self, hazir):
        """Düzeltme ekonomik bir olay değil, kayıt düzeltmesidir."""
        dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, verified_qty=100.0)
        data = dm.load_portfolio()
        eski = next(t for t in data["transactions"] if int(t["id"]) == 1)
        assert eski.get("exit_price") is None
        assert eski.get("realized_pnl_usd") is None

    def test_gecmis_satisin_kz_si_deftere_gecer(self, hazir):
        """Bu yazılmazsa pozisyon ucuzlar ve tablo olduğundan iyi görünür."""
        once = dm.calculate_realized_metrics(dm.load_portfolio())["total_realized_pnl_usd"]
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, verified_qty=100.0)
        sonra = dm.calculate_realized_metrics(dm.load_portfolio())["total_realized_pnl_usd"]
        # 100 adet 10$'dan alınıp 4$'dan satıldı → 600$ zarar.
        assert kayit["realized"]["booked"] is True
        assert kayit["realized"]["pnl_usd"] == pytest.approx(-600.0)
        assert (sonra - once) == pytest.approx(-600.0)

    def test_kapatilan_lotlar_izlenen_pozisyon_listesinde_gorunmez(self, hazir):
        """Aynı varlığı iki kez saydırırdı."""
        dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, verified_qty=100.0)
        data = dm.load_portfolio()
        eski = next(t for t in data["transactions"] if int(t["id"]) == 1)
        assert dm._defter_artigi_mi(eski) is True

    def test_nakit_bakiyesi_degismez(self, hazir):
        once = dm.load_portfolio().get("wallets", {})
        dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, verified_qty=100.0)
        assert dm.load_portfolio().get("wallets", {}) == once

    def test_denetim_kaydi_oncesi_ve_sonrasi_tasir(self, hazir):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, note="test notu",
                                 verified_qty=100.0)
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
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", signature=r["signature"], root=hazir,
                                 verified_qty=100.0)
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
        dm.apply_rebuild("ABCUSDT@BINANCE", root=dizin, verified_qty=0.0)
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

        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, verified_qty=100.0)
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
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, verified_qty=100.0)
        kz_id = kayit["realized"]["tx_id"]
        assert kz_id is not None
        dm.undo_rebuild(kayit["id"])
        data = dm.load_portfolio()
        assert not any(int(t["id"]) == int(kz_id) for t in data["transactions"])

    def test_geri_alma_eski_lotu_aktife_dondurur(self, hazir):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, verified_qty=100.0)
        dm.undo_rebuild(kayit["id"])
        eski = next(t for t in dm.load_portfolio()["transactions"] if int(t["id"]) == 1)
        assert eski["status"] == dm.ACTIVE_STATUS
        assert "rebuild_out_id" not in eski
        assert "close_reason" not in eski

    def test_olusan_lot_satildiysa_geri_alinamaz(self, hazir):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, verified_qty=100.0)
        data = dm.load_portfolio()
        yeni = next(t for t in data["transactions"]
                    if int(t["id"]) == int(kayit["created_tx_ids"][0]))
        yeni["status"] = dm.CLOSED_STATUS
        dm.save_portfolio(data)
        with pytest.raises(ValueError, match="satılmış veya kapatılmış"):
            dm.undo_rebuild(kayit["id"])

    def test_olusan_lot_silindiyse_geri_alinamaz(self, hazir):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=hazir, verified_qty=100.0)
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


# =====================================================================
# BÖLÜM 7 — FAZ F5b: HESAP DEFTERİ VE DOĞRULANMIŞ BAKİYE
# =====================================================================
"""
F5'in kapsam kanıtı tek yönlüydü ve gerçek veride 21 önerinin 10'unu yanlış
üretti. İki kök sebep vardı: alım-satım dosyası hesabın tamamı değil, ve
"bakiye eksiye düşmüyor" bir kapsam kanıtı değil. Bu bölüm ikisini de kilitler.
"""


class TestHesapDefteriAyristirici:

    def test_airdrop_bakiyeyi_artirir_ve_maliyeti_sifirdir(self, dizin):
        """
        Kullanıcının APT'si tam olarak böyle eksik çıkmıştı: Earn airdrop'ları
        alım-satım dosyasında yok, bu yüzden 44.4345 yerine 44.1400 görünüyordu.
        """
        _hesap_defteri(dizin, [
            ["2025-10-22 06:22:04", "Spot", "Earn - Airdrop Distribution", "ABC", "0.30"],
        ])
        olaylar, uyarilar = rc.load_binance_transaction_history(
            os.path.join(dizin, "Binance-Transaction-History-test-part1-of1.csv"))
        assert uyarilar == []
        assert len(olaylar) == 1
        assert olaylar[0]["kind"] == "REWARD"
        assert olaylar[0]["qty"] == pytest.approx(0.30)
        # Bedelsiz gelen bir coinin maliyeti SIFIRDIR ve bu bilinen bir sıfırdır.
        assert rc._birim_maliyet(olaylar[0]) == (0.0, True)

    def test_bedelsiz_lot_oneriyi_engellemez(self, dizin):
        """
        'Maliyeti sıfır' ile 'maliyeti bilinmiyor' farklı şeylerdir. İkisi
        karıştırılırsa airdrop alan her pozisyon boş yere bloke olur.
        """
        _trades(dizin, [["2024-01-01 10:00:00", "ABCUSDT", "BUY", "1.0", "100ABC", "100USDT", "0USDT"]])
        _hesap_defteri(dizin, [
            ["2024-02-01 10:00:00", "Spot", "Earn - Airdrop Distribution", "ABC", "10"],
        ])
        plan = rc.build_rebuild_plan(_defter([("2026-01-01", 100.0, 1.0)]), dizin)
        r = _satir(plan, "ABCUSDT@BINANCE")
        assert r["status"] != "blocked"
        assert r["proposed_qty"] == pytest.approx(110.0)
        assert r["zero_cost_qty"] == pytest.approx(10.0)
        assert any("bedelsiz" in w for w in r["warnings"])

    def test_convert_iki_bacagi_eslestirilir(self, dizin):
        """BTC tam olarak böyle şişmişti: Convert ile giden 0.0046 görünmüyordu."""
        _hesap_defteri(dizin, [
            ["2024-03-01 12:00:00", "Spot", "Binance Convert", "USDT", "-200"],
            ["2024-03-01 12:00:00", "Spot", "Binance Convert", "ABC", "100"],
        ])
        olaylar, _ = rc.load_binance_transaction_history(
            os.path.join(dizin, "Binance-Transaction-History-test-part1-of1.csv"))
        abc = next(o for o in olaylar if o["asset"] == "ABC")
        assert abc["qty"] == pytest.approx(100.0)
        assert abc["usd_known"] is True
        assert abc["usd_value"] == pytest.approx(200.0)

    def test_toz_eritme_pozisyonu_sifirlar(self, dizin):
        """
        Kullanıcının SNX/CHR/DOGE/LPT'si 'Small Assets Exchange BNB' ile
        eritilmişti; dosya okunmadığı için sistem hâlâ toz duruyor sanıyordu.
        """
        _trades(dizin, [["2024-01-01 10:00:00", "ABCUSDT", "BUY", "1.0", "100ABC", "100USDT", "0USDT"]])
        _hesap_defteri(dizin, [
            ["2024-05-01 09:00:00", "Spot", "Small Assets Exchange BNB", "ABC", "-100"],
            ["2024-05-01 09:00:00", "Spot", "Small Assets Exchange BNB", "BNB", "0.002"],
        ])
        plan = rc.build_rebuild_plan(_defter([("2026-01-01", 100.0, 1.0)]), dizin)
        r = _satir(plan, "ABCUSDT@BINANCE")
        assert r["proposed_qty"] == pytest.approx(0.0)

    def test_vadeli_hesap_satirlari_spot_bakiyeyi_etkilemez(self, dizin):
        _hesap_defteri(dizin, [
            ["2024-04-01 10:00:00", "USD-M Futures", "Realized Profit and Loss", "USDT", "-50"],
            ["2024-04-01 10:00:00", "USD-M Futures", "Fee", "USDT", "-1"],
            ["2024-04-02 10:00:00", "Spot", "Earn - Airdrop Distribution", "ABC", "5"],
        ])
        olaylar, _ = rc.load_binance_transaction_history(
            os.path.join(dizin, "Binance-Transaction-History-test-part1-of1.csv"))
        assert [o["asset"] for o in olaylar] == ["ABC"]

    def test_alim_satim_dosyasi_varsa_islemler_iki_kez_sayilmaz(self, dizin):
        """
        Hesap defteri spot dolumları da içerir. Kendi dosyası varken ikisini
        birden almak her alımı iki kez saydırırdı — F5b'nin en büyük riski bu.
        """
        _trades(dizin, [["2024-01-01 10:00:00", "ABCUSDT", "BUY", "1.0", "100ABC", "100USDT", "0USDT"]])
        _hesap_defteri(dizin, [
            ["2024-01-01 10:00:00", "Spot", "Transaction Buy", "ABC", "100"],
            ["2024-01-01 10:00:00", "Spot", "Transaction Spend", "USDT", "-100"],
        ])
        olaylar, _, _ = rc.load_all_events(dizin)
        abc = [o for o in olaylar if o["asset"] == "ABC"]
        assert len(abc) == 1
        assert sum(o["qty"] for o in abc) == pytest.approx(100.0)

    def test_alim_satim_dosyasi_yoksa_islemler_hesap_defterinden_gelir(self, dizin):
        """Kullanıcı yalnızca hesap defterini indirmişse mutabakat yine çalışmalı."""
        _hesap_defteri(dizin, [
            ["2024-01-01 10:00:00", "Spot", "Transaction Buy", "ABC", "100"],
            ["2024-01-01 10:00:00", "Spot", "Transaction Spend", "USDT", "-250"],
        ])
        olaylar, _, _ = rc.load_all_events(dizin)
        abc = next(o for o in olaylar if o["asset"] == "ABC")
        assert abc["qty"] == pytest.approx(100.0)
        assert abc["usd_value"] == pytest.approx(250.0)
        assert abc["usd_known"] is True

    def test_bnb_komisyonu_bakiyeden_dusulur(self, dizin):
        """
        Komisyon başka bir coinden ödendiyse o coinin bakiyesi azalır. Yalnızca
        alım-satım satırına bakmak BNB'yi olduğundan yüksek gösterirdi.
        """
        _trades(dizin, [
            ["2024-01-01 10:00:00", "BNBUSDT", "BUY", "100", "1BNB", "100USDT", "0USDT"],
            ["2024-02-01 10:00:00", "ABCUSDT", "BUY", "1.0", "100ABC", "100USDT", "0.01BNB"],
        ])
        olaylar, _ = rc.load_binance_trades(
            os.path.join(dizin, "Binance-Spot-Trade-History-test-part1-of1.csv"))
        bnb = [o for o in olaylar if o["asset"] == "BNB"]
        assert sum(o["qty"] for o in bnb) == pytest.approx(0.99)
        assert any(o["kind"] == "FEE" for o in bnb)

    def test_komisyon_cekim_ikazi_uretmez(self, dizin):
        """Komisyon bir transfer değildir; kullanıcıya olmayan bir çekim denmez."""
        _trades(dizin, [
            ["2024-01-01 10:00:00", "BNBUSDT", "BUY", "100", "1BNB", "100USDT", "0USDT"],
            ["2024-02-01 10:00:00", "ABCUSDT", "BUY", "1.0", "100ABC", "100USDT", "0.01BNB"],
        ])
        plan = rc.build_rebuild_plan(_defter([("2026-01-01", 1.0, 100.0)], coin="BNBUSDT"), dizin)
        r = _satir(plan, "BNBUSDT@BINANCE")
        assert r["fee_qty"] == pytest.approx(0.01)
        assert not any("çekilmiş" in w for w in r["warnings"])

    def test_taninmayan_islem_sessizce_atlanmaz(self, dizin):
        """Sessiz atlama, F5b'de düzeltilen hatanın ta kendisiydi."""
        _hesap_defteri(dizin, [
            ["2024-01-01 10:00:00", "Spot", "Yepyeni Bir Kanal", "ABC", "42"],
        ])
        olaylar, uyarilar = rc.load_binance_transaction_history(
            os.path.join(dizin, "Binance-Transaction-History-test-part1-of1.csv"))
        assert olaylar == []
        assert any("Yepyeni Bir Kanal" in u for u in uyarilar)


class TestDogrulanmisBakiye:

    @pytest.fixture
    def eksik_dosya(self, dizin):
        """
        Kullanıcının BCCOIN'inin birebir kurgusu: defterde 150, dosyada yalnızca
        50'lik bir alım var. Aradaki 100 dosya penceresinden önce alınmış ve hiç
        satılmamış — yani hiçbir yerde iz bırakmıyor.
        """
        _trades(dizin, [["2024-10-03 10:00:00", "ABCUSDT", "BUY", "1.0", "50ABC", "50USDT", "0USDT"]])
        _defter([("2026-01-01", 150.0, 1.0)])
        return dizin

    def test_hicbir_satir_ready_olmaz(self, eksik_dosya):
        """Yeşil rozet artık kanıt ister; kanıtsız 'uygulanabilir' yoktur."""
        plan = rc.build_rebuild_plan(dm.load_portfolio(), eksik_dosya)
        assert all(r["status"] != "ready" for r in plan["rows"])
        r = _satir(plan, "ABCUSDT@BINANCE")
        assert r["verify_required"] is True
        assert r["verify_prompt"]

    def test_kucultme_onerisi_ikaz_uretir(self, eksik_dosya):
        plan = rc.build_rebuild_plan(dm.load_portfolio(), eksik_dosya)
        r = _satir(plan, "ABCUSDT@BINANCE")
        assert r["status"] == "caution"
        assert any("KÜÇÜLTÜYOR" in w for w in r["warnings"])

    def test_bakiye_girilmeden_uygulanamaz(self, eksik_dosya):
        with pytest.raises(ValueError, match="gerçek bakiye girilmelidir"):
            dm.apply_rebuild("ABCUSDT@BINANCE", root=eksik_dosya)

    def test_gercek_bakiye_defterle_uyusuyorsa_deftere_dokunulmaz(self, eksik_dosya):
        """
        Kullanıcının bildirdiği hatanın tam senaryosu: borsada gerçekten 150 var,
        sistem 50'ye düşürmek istiyordu. Doğru cevap 'dosya eksik, dokunma'.
        """
        once = dm.load_portfolio()["transactions"]
        with pytest.raises(ValueError, match="defteriniz doğru"):
            dm.apply_rebuild("ABCUSDT@BINANCE", root=eksik_dosya, verified_qty=150.0)
        assert dm.load_portfolio()["transactions"] == once
        assert dm.load_portfolio()["rebuilds"] == []

    def test_gercek_bakiye_oneriyle_uyusuyorsa_uygulanir(self, eksik_dosya):
        kayit = dm.apply_rebuild("ABCUSDT@BINANCE", root=eksik_dosya, verified_qty=50.0)
        assert kayit["after"]["qty"] == pytest.approx(50.0)
        assert kayit["verified_qty"] == pytest.approx(50.0)

    def test_hicbiriyle_uyusmayan_bakiye_reddedilir(self, eksik_dosya):
        with pytest.raises(ValueError, match="Üçüncü bir kaynak"):
            dm.apply_rebuild("ABCUSDT@BINANCE", root=eksik_dosya, verified_qty=90.0)

    def test_olcut_hangisine_daha_yakin_oldugudur(self):
        """
        Kullanıcı borsa ekranındaki rakamı yuvarlayarak girebilir; birebir
        eşitlik aramak doğrulamayı kullanılamaz kılardı. Ölçüt bu yüzden
        'girilen bakiye hangi adaya daha yakın' olmalı — ve yakınlık yetmez,
        kazanan adayla arasındaki fark tolerans içinde de kalmalı.
        """
        satir = {"asset": "ABC", "proposed_qty": 1100.0, "ledger_qty": 1000.0,
                 "coverage_start": "2024-01-01"}
        assert rc.evaluate_verified_qty(satir, 1100.0)["verdict"] == "matches_proposal"
        assert rc.evaluate_verified_qty(satir, 1000.0)["verdict"] == "matches_ledger"
        assert rc.evaluate_verified_qty(satir, 1002.0)["verdict"] == "matches_ledger"

    def test_miktarlar_zaten_ortusuyorsa_dogrulama_miktari_teyit_eder(self):
        """
        Defter 2772, öneri 2772.495: fark %0.02, yani kullanıcının borsa
        ekranından ayırt edebileceği bir şey değil. Burada düzeltilen miktar
        değil MALİYET TABANIDIR; doğrulama da yalnızca 'miktar gerçekten bu mu'
        sorusunu sorar. Bu bir boşluk değil, ölçüm sınırının dürüstçe kabulüdür:
        gizlenebilecek fark pozisyonun %0.5'inden küçüktür.
        """
        satir = {"asset": "MAV", "proposed_qty": 2772.495, "ledger_qty": 2772.0,
                 "coverage_start": "2024-01-01"}
        assert rc.evaluate_verified_qty(satir, 2772.0)["ok"] is True
        assert rc.evaluate_verified_qty(satir, 2772.495)["ok"] is True
        # Ama üçüncü bir rakam yine reddedilir.
        assert rc.evaluate_verified_qty(satir, 3500.0)["ok"] is False

    def test_negatif_bakiye_reddedilir(self, eksik_dosya):
        plan = rc.build_rebuild_plan(dm.load_portfolio(), eksik_dosya)
        sonuc = rc.evaluate_verified_qty(_satir(plan, "ABCUSDT@BINANCE"), -5)
        assert sonuc["ok"] is False and sonuc["verdict"] == "invalid"

    def test_api_bakiyesiz_istek_400_doner(self, client):
        r = client.post("/api/reconcile/rebuild/ABCUSDT@BINANCE", json={})
        # Öneri yoksa 404, varsa doğrulama eksikliğinden 400 — ikisi de "uygulanmadı".
        assert r.status_code in (400, 404)
