r"""
CoinTakip — FAZ F1c Testleri: Konum (Borsa / Cüzdan) Yönetimi

Transfer özelliği kullanıcının kendi konumunu yaratmasına izin veriyor
(METAMASK, LEDGER, TRUST WALLET…). Ama sistemin geri kalanı dört sabit isim
biliyordu: BINANCE, MEXC, GATE.IO, DEX. Sonuç: varlık METAMASK'a taşınıyor,
kayıt doğru oluyor, ama Kasa ekranında hiç görünmüyordu — kullanıcı
"cüzdanım kayboldu" diyordu.

Daha sessiz ve daha tehlikeli olan ikinci hata: METAMASK'tan yapılan bir satışın
geliri **Binance'in nakit bakiyesine** yazılıyordu, çünkü bilinmeyen her konum
varsayılana düşürülüyordu.

Bu testler ikisini de kalıcı olarak kapatır.
"""

import pytest

import data_manager as dm


def _metrics(data=None):
    from conftest import SAHTE_FIYATLAR
    if data is None:
        data = dm.load_portfolio()
    return dm.calculate_portfolio_metrics(data, dict(SAHTE_FIYATLAR))


class TestKonumNormalizasyonu:

    def test_zincir_ustu_adlar_dex_kovasinda_toplanir(self, kayitli_portfoy):
        for ad in ("DEX", "dex", "DEX (On-Chain)", "PANCAKESWAP", "Uniswap V3"):
            assert dm.normalize_location(ad) == "DEX", f"{ad} DEX'e eşlenmeliydi."

    def test_kullanici_konumlari_oldugu_gibi_korunur(self, kayitli_portfoy):
        """En kritik kural: bilinmeyeni varsayılana düşürmek veri kaybıdır."""
        for ad in ("METAMASK", "Ledger", "trust wallet", "WHITEBIT", "KRAKEN"):
            assert dm.normalize_location(ad) == ad.upper().strip()

    def test_bos_ad_binance_olur(self, kayitli_portfoy):
        assert dm.normalize_location("") == "BINANCE"
        assert dm.normalize_location(None) == "BINANCE"

    def test_uni_harfleri_yanlislikla_dex_yapmaz(self, kayitli_portfoy):
        """
        Eski kural `"UNI" in ad` idi ve içinde bu üç harf geçen her konumu
        DEX sanıyordu. Regresyon testi.
        """
        assert dm.normalize_location("UNITED WALLET") == "UNITED WALLET"
        assert dm.normalize_location("COMMUNITY") == "COMMUNITY"


class TestBilinenKonumlar:

    def test_varsayilanlar_her_zaman_listede(self, kayitli_portfoy):
        konumlar = dm.known_locations()
        for v in ("BINANCE", "MEXC", "GATE.IO", "DEX"):
            assert v in konumlar

    def test_transfer_hedefi_listeye_girer(self, kayitli_portfoy):
        assert "METAMASK" not in dm.known_locations()
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "METAMASK", "qty": 1.0,
        })
        assert "METAMASK" in dm.known_locations(), \
            "Transfer edilen konum bilinen konumlar listesine girmedi."

    def test_aktif_pozisyonun_konumu_listeye_girer(self, kayitli_portfoy):
        data = dm.load_portfolio()
        data["transactions"].append({
            "id": 99, "date": "2026-05-01", "coin": "BTCUSDT", "exchange": "LEDGER",
            "qty": 0.1, "cost": 90000.0, "status": "Aktif", "notes": "", "category": "Majör / L1",
        })
        dm.save_portfolio(data)
        assert "LEDGER" in dm.known_locations()

    def test_nakit_bakiyesi_olan_konum_listeye_girer(self, kayitli_portfoy):
        data = dm.load_portfolio()
        data["wallets"]["exchange_cash"]["KRAKEN"] = 250.0
        dm.save_portfolio(data)
        assert "KRAKEN" in dm.known_locations()

    def test_varsayilanlar_once_kullanici_konumlari_sonra(self, kayitli_portfoy):
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "METAMASK", "qty": 1.0,
        })
        konumlar = dm.known_locations()
        assert konumlar[:4] == ["BINANCE", "MEXC", "GATE.IO", "DEX"]
        assert konumlar[-1] == "METAMASK"


class TestKpiUretimi:

    def test_kullanici_konumu_kendi_kpi_sini_alir(self, kayitli_portfoy):
        """Asıl kullanıcı şikayeti: 'MetaMask cüzdanım görünmüyor'."""
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "METAMASK", "qty": 1.0,
        })
        metrics = _metrics()
        assert "METAMASK" in metrics["exchange_kpis"], \
            "Kullanıcının kendi konumu KPI üretmedi — Kasa ekranında görünmez."
        kpi = metrics["exchange_kpis"]["METAMASK"]
        assert kpi["active_coins_count"] == 1
        assert kpi["spot_current_value"] == pytest.approx(2000.0)  # 1 ETH × 2000

    def test_konum_listesi_metriklerle_birlikte_doner(self, kayitli_portfoy):
        metrics = _metrics()
        assert "locations" in metrics
        assert "BINANCE" in metrics["locations"]

    def test_konum_pozisyon_listesinde_ayri_gorunur(self, kayitli_portfoy):
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "METAMASK", "qty": 1.0,
        })
        anahtarlar = [c["pos_key"] for c in _metrics()["consolidated_coins"]]
        assert "ETHUSDT@METAMASK" in anahtarlar


class TestSatisNakitYonlendirmesi:
    """
    En sessiz hata buradaydı: bilinmeyen konumdan yapılan satışın geliri
    Binance'e yazılıyordu ve kullanıcı bunu fark edemezdi.
    """

    def test_kullanici_konumundan_satis_dogru_kasaya_yazilir(self, kayitli_portfoy):
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "METAMASK", "qty": 1.0,
        })
        binance_once = float(dm.load_portfolio()["wallets"]["exchange_cash"]["BINANCE"])

        dm.execute_target_sale("ETHUSDT@METAMASK", sell_price=2000.0, sell_qty=1.0)

        nakit = dm.load_portfolio()["wallets"]["exchange_cash"]
        assert nakit.get("METAMASK", 0) == pytest.approx(2000.0), \
            "Satış geliri kendi konumuna yazılmadı."
        assert float(nakit["BINANCE"]) == pytest.approx(binance_once), \
            "Satış geliri yanlışlıkla Binance'e yazıldı — eski hatanın tekrarı."

    def test_bilinen_borsadan_satis_eskisi_gibi_calisir(self, kayitli_portfoy):
        """Regresyon: mevcut davranış bozulmamalı."""
        mexc_once = float(dm.load_portfolio()["wallets"]["exchange_cash"]["MEXC"])
        data = dm.load_portfolio()
        data["transactions"].append({
            "id": 99, "date": "2026-05-01", "coin": "SOLUSDT", "exchange": "MEXC",
            "qty": 2.0, "cost": 100.0, "status": "Aktif", "notes": "", "category": "Majör / L1",
        })
        dm.save_portfolio(data)

        dm.execute_target_sale("SOLUSDT@MEXC", sell_price=150.0, sell_qty=2.0)
        nakit = dm.load_portfolio()["wallets"]["exchange_cash"]
        assert float(nakit["MEXC"]) == pytest.approx(mexc_once + 300.0)

    def test_dex_varyantindan_satis_dex_kasasina_yazilir(self, kayitli_portfoy):
        """CPL DEX'te; 'PANCAKESWAP' gibi adlar tek DEX kovasında toplanmalı."""
        dm.execute_target_sale("CPLUSDT@DEX", sell_price=2.0e-09, sell_qty=2_700_000_000.0)
        nakit = dm.load_portfolio()["wallets"]["exchange_cash"]
        assert float(nakit.get("DEX", 0)) == pytest.approx(5.4, abs=0.01)


class TestApiUclari:

    def test_portfoy_ucu_konum_listesi_doner(self, client):
        r = client.get("/api/portfolio")
        assert r.status_code == 200
        assert "BINANCE" in r.json()["locations"]

    def test_transfer_sonrasi_konum_ucta_gorunur(self, client):
        client.post("/api/transfers", json={
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "METAMASK", "qty": 1.0,
        })
        body = client.get("/api/portfolio").json()
        assert "METAMASK" in body["locations"]
        assert "METAMASK" in body["exchange_kpis"]

    def test_cuzdan_ucu_yeni_konum_kabul_eder(self, client):
        r = client.post("/api/wallets", json={
            "exchange_cash": {"BINANCE": 100.0, "MEXC": 50.0, "METAMASK": 25.0},
            "futures_balance": 0.0, "margin_balance": 0.0,
        })
        assert r.status_code == 200
        assert r.json()["wallets"]["exchange_cash"]["METAMASK"] == pytest.approx(25.0)
        assert r.json()["wallets"]["usdt_cash"] == pytest.approx(175.0)
