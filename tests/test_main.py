"""
main.py endpoint testleri (FAZ C2)

╔══════════════════════════════════════════════════════════════════════════╗
║  /api/ai/analyze UCUNA KASITLI OLARAK TEST YAZILMAMIŞTIR.                ║
║  Bu uç Gemini API'ye gerçek çağrı yapar ve kullanıcının günlük ~20       ║
║  çağrılık kotasını tüketir. (Çalışma Kuralı #1: sıfır kota israfı.)      ║
╚══════════════════════════════════════════════════════════════════════════╝

Tüm testler geçici veri dizininde çalışır — gerçek portfolio.json korunur.
"""

import json

import pytest

import data_manager as dm


# ===========================================================================
# PORTFÖY & İŞLEM UÇLARI
# ===========================================================================

def test_portfoy_ucu_calisir(client):
    y = client.get("/api/portfolio")
    assert y.status_code == 200

    veri = y.json()
    assert "kpis" in veri
    assert "consolidated_coins" in veri
    assert "exchange_kpis" in veri
    assert veri["kpis"]["total_kasa"] > 0


def test_islemler_ucu_zenginlestirilmis_liste_doner(client):
    y = client.get("/api/transactions")
    assert y.status_code == 200

    islemler = y.json()
    assert len(islemler) == 6
    # Zenginleştirilmiş alanlar hesaplanmış olmalı
    assert all("pnl_usd" in t and "cur_val" in t for t in islemler)


def test_islem_ekleme(client):
    y = client.post("/api/transactions", json={
        "coin": "SOL", "exchange": "BINANCE", "qty": 2.0, "cost": 140.0
    })
    assert y.status_code == 200

    tx = y.json()["transaction"]
    assert tx["coin"] == "SOLUSDT", "CEX işlemlerinde USDT soneki eklenmeli"
    assert tx["id"] == 7
    assert tx["status"] == "Aktif"

    # Diske yazılmış olmalı ve sayaç ilerlemeli
    veri = dm.load_portfolio()
    assert veri["next_tx_id"] == 8
    assert len(veri["transactions"]) == 7


def test_dex_isleminde_usdt_soneki_eklenmez(client):
    y = client.post("/api/transactions", json={
        "coin": "CPL/WBNB", "exchange": "DEX", "qty": 1000.0, "cost": 1.0e-08
    })
    assert y.status_code == 200
    assert y.json()["transaction"]["coin"] == "CPL/WBNB"


def test_islem_guncelleme(client):
    y = client.put("/api/transactions/3", json={"qty": 2.0, "notes": "güncellendi"})
    assert y.status_code == 200

    tx = next(t for t in dm.load_portfolio()["transactions"] if t["id"] == 3)
    assert tx["qty"] == 2.0
    assert tx["notes"] == "güncellendi"


def test_olmayan_islem_guncellenemez(client):
    assert client.put("/api/transactions/9999", json={"qty": 1.0}).status_code == 404


def test_islem_silme(client):
    assert client.delete("/api/transactions/3").status_code == 200
    assert len(dm.load_portfolio()["transactions"]) == 5
    assert client.delete("/api/transactions/9999").status_code == 404


def test_durum_degistirme(client):
    y = client.patch("/api/transactions/1/status")
    assert y.status_code == 200
    assert y.json()["new_status"] == "Kapandı / İzleme"

    # Tekrar çevir
    assert client.patch("/api/transactions/1/status").json()["new_status"] == "Aktif"


# ===========================================================================
# SATIŞ UCU
# ===========================================================================

def test_islem_satisi_nakde_donusur(client):
    onceki = dm.load_portfolio()["wallets"]["usdt_cash"]

    y = client.post("/api/transactions/3/sell", json={
        "sell_qty": 1.0, "sell_price": 2000.0
    })
    assert y.status_code == 200

    sonuc = y.json()
    assert sonuc["cash_added"] == pytest.approx(2000.0)
    assert sonuc["realized_pnl"] == pytest.approx(-500.0)   # (2000-2500)*1.0
    assert dm.load_portfolio()["wallets"]["usdt_cash"] == pytest.approx(onceki + 2000.0)


def test_gecersiz_satis_miktari_reddedilir(client):
    y = client.post("/api/transactions/3/sell", json={"sell_qty": 0, "sell_price": 2000.0})
    assert y.status_code == 400


def test_olmayan_islem_satilamaz(client):
    y = client.post("/api/transactions/9999/sell", json={"sell_qty": 1.0, "sell_price": 1.0})
    assert y.status_code == 404


# ===========================================================================
# HEDEF UÇLARI
# ===========================================================================

def test_hedef_kaydetme_ve_silme(client):
    y = client.post("/api/targets", json={
        "pos_key": "BTCUSDT@BINANCE", "target_price": 120000.0, "target_sell_pct": 50.0
    })
    assert y.status_code == 200
    assert y.json()["target"]["target_price"] == 120000.0

    assert client.delete("/api/targets/BTCUSDT@BINANCE").status_code == 200


def test_gecersiz_hedef_fiyati_reddedilir(client):
    y = client.post("/api/targets", json={"pos_key": "BTCUSDT@BINANCE", "target_price": 0})
    assert y.status_code == 400


def test_hedef_satisi_yurutulur(client):
    client.post("/api/targets", json={
        "pos_key": "BTCUSDT@BINANCE", "target_price": 100000.0, "target_sell_pct": 100.0
    })
    y = client.post("/api/targets/BTCUSDT@BINANCE/execute", json={
        "sell_price": 100000.0, "sell_qty": 0.02, "cost_method": "Konsolide Ortalama"
    })
    assert y.status_code == 200
    assert y.json()["proceeds"] == pytest.approx(2000.0)


# ===========================================================================
# CÜZDAN & DCA
# ===========================================================================

def test_cuzdan_guncelleme(client):
    y = client.post("/api/wallets", json={
        "exchange_cash": {"BINANCE": 500.0, "MEXC": 300.0, "GATE.IO": 0.0, "DEX": 0.0}
    })
    assert y.status_code == 200
    assert y.json()["wallets"]["usdt_cash"] == pytest.approx(800.0), \
        "Toplam nakit borsa kasalarının toplamı olmalı"


def test_dca_alimi_nakitten_duser(client):
    onceki = dm.load_portfolio()["wallets"]["exchange_cash"]["BINANCE"]

    y = client.post("/api/dca/execute", json={
        "coin": "ETH", "exchange": "BINANCE", "buy_qty": 0.05,
        "buy_price": 2000.0, "invest_amount": 100.0, "deduct_cash": True
    })
    assert y.status_code == 200

    kasa = dm.load_portfolio()["wallets"]["exchange_cash"]["BINANCE"]
    assert kasa == pytest.approx(onceki - 100.0)


def test_dca_nakit_dusmeden_de_calisir(client):
    onceki = dm.load_portfolio()["wallets"]["exchange_cash"]["BINANCE"]

    client.post("/api/dca/execute", json={
        "coin": "ETH", "exchange": "BINANCE", "buy_qty": 0.05,
        "buy_price": 2000.0, "invest_amount": 100.0, "deduct_cash": False
    })
    assert dm.load_portfolio()["wallets"]["exchange_cash"]["BINANCE"] == pytest.approx(onceki)


# ===========================================================================
# GÜVENLİK UÇLARI
# ===========================================================================

def test_auth_durumu(client):
    y = client.get("/api/auth/status")
    assert y.status_code == 200
    assert y.json()["pin_enabled"] is False


def test_pin_kurulumu_kurtarma_anahtari_dondurur(client):
    y = client.post("/api/auth/setup", json={"new_pin": "3072", "auto_lock_minutes": 5})
    assert y.status_code == 200

    anahtar = y.json()["recovery_key"]
    assert len(anahtar) == 12
    assert client.get("/api/auth/status").json()["pin_enabled"] is True


def test_kisa_pin_reddedilir(client):
    assert client.post("/api/auth/setup", json={"new_pin": "12"}).status_code == 400


def test_pin_dogrulama_ve_oturum_anahtari(client):
    client.post("/api/auth/setup", json={"new_pin": "3072"})

    y = client.post("/api/auth/verify", json={"pin": "3072"})
    assert y.status_code == 200
    assert len(y.json()["session_token"]) > 20

    assert client.post("/api/auth/verify", json={"pin": "0000"}).status_code == 401


def test_kurtarma_anahtari_ile_pin_sifirlama(client):
    anahtar = client.post("/api/auth/setup", json={"new_pin": "1111"}).json()["recovery_key"]

    y = client.post("/api/auth/recover", json={"recovery_key": anahtar, "new_pin": "2222"})
    assert y.status_code == 200
    assert client.post("/api/auth/verify", json={"pin": "2222"}).status_code == 200

    # Yanlış anahtar reddedilmeli
    assert client.post("/api/auth/recover",
                       json={"recovery_key": "YANLIS000000", "new_pin": "3333"}).status_code == 401


def test_pin_kaldirma(client):
    client.post("/api/auth/setup", json={"new_pin": "1111"})
    assert client.post("/api/auth/disable", json={"current_pin": "0000"}).status_code == 401
    assert client.post("/api/auth/disable", json={"current_pin": "1111"}).status_code == 200
    assert client.get("/api/auth/status").json()["pin_enabled"] is False


def test_guvenlik_ayarlari_guncellenir(client):
    y = client.post("/api/auth/settings", json={"auto_lock_minutes": 30, "privacy_mode": True})
    assert y.status_code == 200
    assert y.json()["security"]["auto_lock_minutes"] == 30
    assert y.json()["security"]["privacy_mode"] is True


# ===========================================================================
# AYARLAR, RAPORLAMA & YEDEKLEME
# ===========================================================================

def test_ayarlar_okunur_ve_yazilir(client):
    assert client.get("/api/settings").status_code == 200

    ayarlar = client.get("/api/settings").json()
    ayarlar["preferences"]["refresh_interval_sec"] = 10
    assert client.post("/api/settings", json=ayarlar).status_code == 200
    assert dm.load_settings()["preferences"]["refresh_interval_sec"] == 10


def test_api_anahtari_diske_kodlanmis_yazilir(client):
    """B2 obfuscation'ının uçtan uca doğrulaması."""
    acik = "AIzaSyD-ornek-anahtar-test-1234567890"
    ayarlar = client.get("/api/settings").json()
    ayarlar["api_keys"]["gemini_api_key"] = acik
    client.post("/api/settings", json=ayarlar)

    with open(dm.SETTINGS_FILE, "r", encoding="utf-8") as f:
        assert acik not in f.read(), "Anahtar diske açık metin yazılmamalı"


def test_gerceklesmis_kz_ucu(client):
    y = client.get("/api/realized-pnl")
    assert y.status_code == 200
    assert y.json()["closed_tx_count"] == 1


def test_excel_disa_aktarim(client):
    y = client.get("/api/export/excel")
    assert y.status_code == 200
    assert y.content[:2] == b"PK", "Geçerli bir .xlsx (zip) dosyası olmalı"
    assert len(y.content) > 5000
    assert "attachment" in y.headers["content-disposition"]


def test_excel_toplam_varlik_sifir_degil(client):
    """
    Regresyon testi — E1 düzeltmesi:
    Rapor kpis['total_equity'] okuyordu ama motorun ürettiği anahtar
    'total_kasa'. Başlıkta Toplam Varlık hep $0.00 çıkıyordu.
    """
    import io
    import openpyxl

    y = client.get("/api/export/excel")
    wb = openpyxl.load_workbook(io.BytesIO(y.content))
    baslik = wb["Konsolide Portfoy"]["A2"].value

    assert "Toplam Varlik: $0.00" not in baslik
    assert "5,005" in baslik or "5005" in baslik, f"Beklenen toplam görünmüyor: {baslik}"


def test_yedek_indirme(client):
    y = client.get("/api/backup/download")
    assert y.status_code == 200
    assert len(json.loads(y.content)["transactions"]) == 6


def test_yedek_geri_yukleme(client, ornek_portfoy):
    yedek = dict(ornek_portfoy)
    yedek["transactions"] = yedek["transactions"][:2]

    y = client.post("/api/backup/restore", json=yedek)
    assert y.status_code == 200
    assert len(dm.load_portfolio()["transactions"]) == 2


def test_gecersiz_yedek_reddedilir(client):
    assert client.post("/api/backup/restore", json={"gecersiz": True}).status_code == 400


# ===========================================================================
# STATİK SUNUM & ARAMA
# ===========================================================================

def test_ana_sayfa_sunulur(client):
    y = client.get("/")
    assert y.status_code == 200


def test_arama_ucu(client):
    y = client.get("/api/search", params={"q": "BTC"})
    assert y.status_code == 200
    assert isinstance(y.json(), list)


def test_canli_fiyat_ucu(client):
    y = client.get("/api/live-price/BTCUSDT")
    assert y.status_code == 200
    assert y.json()["price"] == pytest.approx(100000.0)
