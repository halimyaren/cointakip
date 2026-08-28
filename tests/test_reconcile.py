r"""
CoinTakip — FAZ F3 Testleri: Dosya Tabanlı Borsa Mutabakatı

En kritik güvence: **mutabakat deftere HİÇBİR ŞEY YAZMAZ.** Maliyet tabanı
kullanıcının elle girdiği hâliyle kalır; borsa onu asla ezmez.

İkinci güvence: rapor "uyuşmuyor" ile "dosya o kadar geriye gitmiyor"u
BİRBİRİNDEN AYIRIR. Kapsam dışındaki bir pozisyonu "fark var" diye göstermek,
kullanıcıyı olmayan bir hatayı kovalamaya iter.

Testler sentetik dosyalar üretir — kullanıcının gerçek borsa dosyalarına
bağımlı değildir ve `izole_veri` fixture'ı sayesinde gerçek portföye dokunmaz.
"""

import csv
import os

import pytest

import data_manager as dm
import reconcile as rc


# =====================================================================
# Sentetik dosya üreticileri
# =====================================================================
def _binance_trades(dizin, satirlar):
    yol = os.path.join(dizin, "Binance-Spot-Trade-History-test-part1-of1.csv")
    with open(yol, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Time", "Pair", "Side", "Price", "Executed", "Amount", "Fee"])
        w.writerows(satirlar)
    return yol


def _binance_withdraw(dizin, satirlar):
    yol = os.path.join(dizin, "Binance-Withdraw-History-test-part1-of1.csv")
    with open(yol, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Time", "Coin", "Network", "Amount", "Fee", "Address", "TXID", "Status"])
        w.writerows(satirlar)
    return yol


def _binance_deposit(dizin, satirlar):
    yol = os.path.join(dizin, "Binance-Deposit-History-test-part1-of1.csv")
    with open(yol, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Time", "Coin", "Network", "Amount", "Address", "TXID", "Status"])
        w.writerows(satirlar)
    return yol


@pytest.fixture
def dizin(tmp_path):
    d = tmp_path / "borsa_exports" / "binance"
    d.mkdir(parents=True)
    return str(d)


# =====================================================================
# BÖLÜM 1 — AYRIŞTIRICILAR
# =====================================================================
class TestAyristirici:

    def test_bitisik_miktar_ve_varlik_ayrilir(self):
        assert rc.parse_amount_with_asset("0.00089BTC") == (0.00089, "BTC")
        assert rc.parse_amount_with_asset("70.31USDT") == (70.31, "USDT")
        assert rc.parse_amount_with_asset("0USDT") == (0.0, "USDT")

    def test_duz_sayi_varliksiz_doner(self):
        assert rc.parse_amount_with_asset("131.63493425") == (131.63493425, "")

    def test_bozuk_deger_patlamaz(self):
        assert rc.parse_amount_with_asset(None) == (0.0, "")
        assert rc.parse_amount_with_asset("") == (0.0, "")
        assert rc.parse_amount_with_asset("abc") == (0.0, "")

    def test_takma_ad_cozulur(self):
        """MEXC Tether Gold'u `GOLD(XAUT)` yazıyor; defterde `XAUT`."""
        assert rc.normalize_asset("GOLD(XAUT)") == "XAUT"
        assert rc.normalize_asset("gold(xaut)") == "XAUT"

    def test_parite_ayrilir(self):
        assert rc.split_pair("BTCUSDT") == ("BTC", "USDT")
        assert rc.split_pair("GOLD(XAUT)_USDT") == ("XAUT", "USDT")
        assert rc.split_pair("RDNT_USDT") == ("RDNT", "USDT")


class TestBinanceOkuyucu:

    def test_alim_satim_isareti(self, dizin):
        _binance_trades(dizin, [
            ["2026-01-10 10:00:00", "BTCUSDT", "BUY", "80000", "0.01BTC", "800USDT", "0.001BNB"],
            ["2026-02-10 10:00:00", "BTCUSDT", "SELL", "90000", "0.004BTC", "360USDT", "0.36USDT"],
        ])
        olaylar, _ = rc.load_binance_trades(
            os.path.join(dizin, "Binance-Spot-Trade-History-test-part1-of1.csv"))
        assert olaylar[0]["qty"] == pytest.approx(0.01)
        assert olaylar[1]["qty"] == pytest.approx(-0.004)
        assert olaylar[0]["usd_known"] is True

    def test_komisyon_coinin_kendisindense_miktardan_dusulur(self, dizin):
        """
        Binance'in 'Executed' sütunu komisyon DÜŞÜLMEDEN önceki dolumdur.
        Komisyon aynı coinden alındıysa eline geçen miktar daha azdır.
        """
        _binance_trades(dizin, [
            ["2026-01-10 10:00:00", "SAGAUSDT", "BUY", "1", "100SAGA", "100USDT", "0.1SAGA"],
        ])
        olaylar, _ = rc.load_binance_trades(
            os.path.join(dizin, "Binance-Spot-Trade-History-test-part1-of1.csv"))
        assert olaylar[0]["qty"] == pytest.approx(99.9), \
            "Coin'den kesilen komisyon miktardan düşülmedi."

    def test_bnb_komisyonu_miktari_etkilemez(self, dizin):
        _binance_trades(dizin, [
            ["2026-01-10 10:00:00", "SAGAUSDT", "BUY", "1", "100SAGA", "100USDT", "0.01BNB"],
        ])
        olaylar, _ = rc.load_binance_trades(
            os.path.join(dizin, "Binance-Spot-Trade-History-test-part1-of1.csv"))
        assert olaylar[0]["qty"] == pytest.approx(100.0)

    def test_cekme_negatif_yatirma_pozitif(self, dizin):
        _binance_withdraw(dizin, [
            ["2026-03-20 13:07:06", "RDNT", "BSC", "19069.886", "4.5", "0xabc", "tx1", "Completed"],
        ])
        _binance_deposit(dizin, [
            ["2025-01-01 11:09:51", "USDT", "BSC", "131.63", "0xabc", "tx2", "Completed"],
        ])
        c, _ = rc.load_binance_withdrawals(
            os.path.join(dizin, "Binance-Withdraw-History-test-part1-of1.csv"))
        y, _ = rc.load_binance_deposits(
            os.path.join(dizin, "Binance-Deposit-History-test-part1-of1.csv"))
        assert c[0]["qty"] == pytest.approx(-19069.886)
        assert y[0]["qty"] == pytest.approx(131.63)

    def test_tamamlanmamis_transfer_atlanir(self, dizin):
        _binance_withdraw(dizin, [
            ["2026-03-20 13:07:06", "RDNT", "BSC", "100", "0", "0xabc", "tx1", "Cancelled"],
            ["2026-03-21 13:07:06", "RDNT", "BSC", "50", "0", "0xabc", "tx2", "Completed"],
        ])
        olaylar, _ = rc.load_binance_withdrawals(
            os.path.join(dizin, "Binance-Withdraw-History-test-part1-of1.csv"))
        assert len(olaylar) == 1
        assert olaylar[0]["qty"] == pytest.approx(-50)


# =====================================================================
# BÖLÜM 2 — MUTABAKAT MANTIĞI
# =====================================================================
def _kur(tmp_path, satirlar, cekme=None):
    d = tmp_path / "borsa_exports" / "binance"
    d.mkdir(parents=True, exist_ok=True)
    _binance_trades(str(d), satirlar)
    if cekme:
        _binance_withdraw(str(d), cekme)
    return str(tmp_path / "borsa_exports")


class TestMutabakat:

    def test_eslesen_pozisyon_match_isaretlenir(self, kayitli_portfoy, tmp_path):
        # Defterde 0.02 BTC var (iki lot). Borsada da 0.02 alınmış.
        kok = _kur(tmp_path, [
            ["2026-01-10 10:00:00", "BTCUSDT", "BUY", "80000", "0.01BTC", "800USDT", "0.001BNB"],
            ["2026-02-15 10:00:00", "BTCUSDT", "BUY", "90000", "0.01BTC", "900USDT", "0.001BNB"],
        ])
        rap = rc.reconcile(dm.load_portfolio(), root=kok)
        btc = next(r for r in rap["rows"] if r["asset"] == "BTC")
        assert btc["status"] == "match"
        assert btc["diff_qty"] == pytest.approx(0.0, abs=1e-9)

    def test_gercek_fark_mismatch_isaretlenir(self, kayitli_portfoy, tmp_path):
        kok = _kur(tmp_path, [
            ["2026-01-10 10:00:00", "BTCUSDT", "BUY", "80000", "0.05BTC", "4000USDT", "0.001BNB"],
        ])
        rap = rc.reconcile(dm.load_portfolio(), root=kok)
        btc = next(r for r in rap["rows"] if r["asset"] == "BTC")
        assert btc["status"] == "mismatch"
        assert btc["diff_qty"] == pytest.approx(0.03)

    def test_negatif_bakiye_KAPSAM_DISI_sayilir(self, kayitli_portfoy, tmp_path):
        """
        En önemli dürüstlük kuralı. Çekilen miktar alınandan fazlaysa alım
        dosyanın başlangıcından öncedir — bu bir 'fark' değil, kapsam eksiği.
        Gerçek örnek: SCM, MEXC'ten 506.072 çekilmiş ama alımı pencerenin dışında.
        """
        kok = _kur(tmp_path, [
            ["2026-01-10 10:00:00", "BTCUSDT", "BUY", "80000", "0.01BTC", "800USDT", "0.001BNB"],
        ], cekme=[
            ["2026-02-01 10:00:00", "ETH", "ETH", "5.0", "0.01", "0xabc", "tx1", "Completed"],
        ])
        rap = rc.reconcile(dm.load_portfolio(), root=kok)
        eth = next(r for r in rap["rows"] if r["asset"] == "ETH")
        assert eth["status"] == "coverage_gap", \
            "Negatif borsa bakiyesi 'fark' olarak gösterildi — kullanıcıyı yanıltır."
        assert "imkânsız" in eth["note"]

    def test_defterdeki_lot_pencereden_eskiyse_kapsam_disi(self, kayitli_portfoy, tmp_path):
        """Defterdeki ETH lotu 2026-03-01; dosya 2026-06'da başlıyor."""
        kok = _kur(tmp_path, [
            ["2026-06-10 10:00:00", "ETHUSDT", "BUY", "2000", "0.5ETH", "1000USDT", "0.001BNB"],
        ])
        rap = rc.reconcile(dm.load_portfolio(), root=kok)
        eth = next(r for r in rap["rows"] if r["asset"] == "ETH")
        assert eth["status"] == "coverage_gap"
        assert eth["coverage_start"] == "2026-06-10"
        assert eth["ledger_first_date"] == "2026-03-01"

    def test_borsadan_cekilmis_pozisyon_ayri_isaretlenir(self, kayitli_portfoy, tmp_path):
        """Coin borsadan çıkmışsa defterdeki miktar cüzdanı yansıtıyor olabilir."""
        kok = _kur(tmp_path, [
            ["2026-01-10 10:00:00", "ETHUSDT", "BUY", "2000", "3.0ETH", "6000USDT", "0.001BNB"],
        ], cekme=[
            ["2026-02-01 10:00:00", "ETH", "ETH", "2.5", "0.01", "0xabc", "tx1", "Completed"],
        ])
        rap = rc.reconcile(dm.load_portfolio(), root=kok)
        eth = next(r for r in rap["rows"] if r["asset"] == "ETH")
        assert eth["status"] == "off_exchange"
        assert eth["withdrawn_qty"] == pytest.approx(2.5)

    def test_kapsanmayan_konum_ayri_isaretlenir(self, kayitli_portfoy, tmp_path):
        """CPL DEX'te; DEX için dışa aktarım dosyası yok — eksiklik değil."""
        kok = _kur(tmp_path, [
            ["2026-01-10 10:00:00", "BTCUSDT", "BUY", "80000", "0.02BTC", "1600USDT", "0.001BNB"],
        ])
        rap = rc.reconcile(dm.load_portfolio(), root=kok)
        cpl = next(r for r in rap["rows"] if r["asset"] == "CPL")
        assert cpl["status"] == "uncovered_location"
        assert "DEX" in cpl["note"]

    def test_defterde_olmayan_borsa_bakiyesi(self, kayitli_portfoy, tmp_path):
        kok = _kur(tmp_path, [
            ["2026-01-10 10:00:00", "DOGEUSDT", "BUY", "0.1", "1000DOGE", "100USDT", "0.001BNB"],
        ])
        rap = rc.reconcile(dm.load_portfolio(), root=kok)
        doge = next(r for r in rap["rows"] if r["asset"] == "DOGE")
        assert doge["status"] == "only_exchange"

    def test_girilip_cikilmis_pozisyon_closed(self, kayitli_portfoy, tmp_path):
        kok = _kur(tmp_path, [
            ["2026-01-10 10:00:00", "DOGEUSDT", "BUY", "0.1", "1000DOGE", "100USDT", "0.001BNB"],
            ["2026-01-20 10:00:00", "DOGEUSDT", "SELL", "0.2", "1000DOGE", "200USDT", "0.2USDT"],
        ])
        rap = rc.reconcile(dm.load_portfolio(), root=kok)
        doge = next(r for r in rap["rows"] if r["asset"] == "DOGE")
        assert doge["status"] == "closed"

    def test_stabilcoin_pozisyon_sayilmaz(self, kayitli_portfoy, tmp_path):
        """USDT nakittir; 'eksik' diye raporlamak gürültüdür."""
        kok = _kur(tmp_path, [
            ["2026-01-10 10:00:00", "BTCUSDT", "BUY", "80000", "0.02BTC", "1600USDT", "0.001BNB"],
        ])
        rap = rc.reconcile(dm.load_portfolio(), root=kok)
        usdt = [r for r in rap["rows"] if r["asset"] == "USDT"]
        if usdt:
            assert usdt[0]["status"] == "stablecoin"

    def test_borsa_ortalama_maliyeti_hesaplanir(self, kayitli_portfoy, tmp_path):
        kok = _kur(tmp_path, [
            ["2026-01-10 10:00:00", "BTCUSDT", "BUY", "80000", "0.01BTC", "800USDT", "0.001BNB"],
            ["2026-02-15 10:00:00", "BTCUSDT", "BUY", "90000", "0.01BTC", "900USDT", "0.001BNB"],
        ])
        rap = rc.reconcile(dm.load_portfolio(), root=kok)
        btc = next(r for r in rap["rows"] if r["asset"] == "BTC")
        assert btc["exchange_avg_cost"] == pytest.approx(85000.0)
        assert btc["ledger_avg_cost"] == pytest.approx(85000.0)

    def test_kapsam_penceresi_raporlanir(self, kayitli_portfoy, tmp_path):
        kok = _kur(tmp_path, [
            ["2023-05-01 10:00:00", "BTCUSDT", "BUY", "80000", "0.01BTC", "800USDT", "0.001BNB"],
            ["2026-02-15 10:00:00", "BTCUSDT", "BUY", "90000", "0.01BTC", "900USDT", "0.001BNB"],
        ])
        rap = rc.reconcile(dm.load_portfolio(), root=kok)
        assert rap["coverage"]["BINANCE"]["first"] == "2023-05-01"
        assert rap["coverage"]["BINANCE"]["last"] == "2026-02-15"

    def test_dosya_yoksa_rapor_patlamaz(self, kayitli_portfoy, tmp_path):
        rap = rc.reconcile(dm.load_portfolio(), root=str(tmp_path / "olmayan"))
        assert rap["files_found"] == 0
        assert rap["event_count"] == 0
        # Defterdeki varlıklar yine listelenmeli
        assert any(r["asset"] == "BTC" for r in rap["rows"])


# =====================================================================
# BÖLÜM 3 — SALT OKUNURLUK (EN KRİTİK GÜVENCE)
# =====================================================================
class TestSaltOkunur:

    def test_mutabakat_defteri_DEGISTIRMEZ(self, kayitli_portfoy, tmp_path):
        import json
        with open(dm.DATA_FILE, encoding="utf-8") as f:
            once = json.load(f)

        kok = _kur(tmp_path, [
            ["2026-01-10 10:00:00", "BTCUSDT", "BUY", "80000", "0.5BTC", "40000USDT", "0.001BNB"],
            ["2026-01-11 10:00:00", "DOGEUSDT", "BUY", "0.1", "9999DOGE", "999USDT", "0.1USDT"],
        ], cekme=[
            ["2026-02-01 10:00:00", "ETH", "ETH", "5.0", "0.01", "0xabc", "tx1", "Completed"],
        ])
        rc.reconcile(dm.load_portfolio(), root=kok)

        with open(dm.DATA_FILE, encoding="utf-8") as f:
            sonra = json.load(f)
        assert once == sonra, \
            "Mutabakat defteri değiştirdi — maliyet tabanı borsa tarafından ezilemez."

    def test_rapor_salt_okunur_bayragi_tasir(self, kayitli_portfoy, tmp_path):
        rap = rc.reconcile(dm.load_portfolio(), root=str(tmp_path))
        assert rap["read_only"] is True

    def test_bozuk_dosya_raporu_dusurmez(self, kayitli_portfoy, tmp_path):
        d = tmp_path / "borsa_exports" / "binance"
        d.mkdir(parents=True)
        yol = d / "Binance-Spot-Trade-History-bozuk-part1-of1.csv"
        yol.write_text("bu bir csv degil\x00\x01bozuk", encoding="utf-8")
        rap = rc.reconcile(dm.load_portfolio(), root=str(tmp_path / "borsa_exports"))
        assert "rows" in rap   # patlamadı


# =====================================================================
# BÖLÜM 4 — API UÇLARI
# =====================================================================
class TestApiUclari:

    def test_dosya_listeleme_ucu(self, client):
        r = client.get("/api/reconcile/files")
        assert r.status_code == 200
        assert "root" in r.json() and "files" in r.json()

    def test_mutabakat_ucu_calisir(self, client):
        r = client.get("/api/reconcile")
        assert r.status_code == 200
        body = r.json()
        assert body["read_only"] is True
        assert "rows" in body and "coverage" in body

    def test_mutabakat_ucu_defteri_degistirmez(self, client):
        once = client.get("/api/portfolio").json()["kpis"]["total_kasa"]
        client.get("/api/reconcile")
        sonra = client.get("/api/portfolio").json()["kpis"]["total_kasa"]
        assert once == pytest.approx(sonra)
