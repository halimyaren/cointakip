"""
Hedge / Kaldıraçlı Pozisyon Katmanı testleri (FAZ E)

Kapsam bilinçli olarak dardır: yön, miktar, giriş fiyatı, kaldıraç ve
mark-to-market K/Z. Fonlama birikimi, likidasyon fiyatı ve çapraz marj
kapsam dışıdır — bu testler o sınırı da korur.

En kritik kavram: **kaldıraç USD cinsinden K/Z'yi değiştirmez.**
K/Z = fiyat farkı × miktar. Kaldıraç yalnızca bağlanan marjı ve dolayısıyla
ROE'yi belirler. Bu karıştırılması çok kolay olduğu için ayrı testi var.
"""

import pytest

import data_manager


# ===========================================================================
# ŞEMA GERİYE DÖNÜK UYUMLULUK
# ===========================================================================

def test_eski_portfoy_dosyasi_hedge_alanlarini_kazanir(ornek_portfoy):
    """Hedge alanları olmayan eski dosyalar okunabilmeli."""
    assert "hedges" not in ornek_portfoy
    data_manager.save_portfolio(ornek_portfoy)

    yuklenen = data_manager.load_portfolio()
    assert yuklenen["hedges"] == []
    assert yuklenen["next_hedge_id"] == 1
    # İşlemler bozulmamalı
    assert len(yuklenen["transactions"]) == len(ornek_portfoy["transactions"])


def test_mevcut_hedge_kayitlari_varsa_next_id_dogru_hesaplanir():
    data_manager.save_portfolio({
        "wallets": {"usdt_cash": 0.0}, "transactions": [], "next_tx_id": 1,
        "hedges": [{"id": 7}, {"id": 3}],
    })
    assert data_manager.load_portfolio()["next_hedge_id"] == 8


# ===========================================================================
# KÂR / ZARAR MATEMATİĞİ
# ===========================================================================

def test_short_fiyat_dusunce_kazanir():
    # 80000'den short, 72000'e düştü, 0.05 adet → (80000-72000)*0.05 = 400
    assert data_manager.hedge_pnl("SHORT", 0.05, 80000.0, 72000.0) == pytest.approx(400.0)


def test_short_fiyat_yukselince_kaybeder():
    assert data_manager.hedge_pnl("SHORT", 0.05, 80000.0, 88000.0) == pytest.approx(-400.0)


def test_long_fiyat_yukselince_kazanir():
    assert data_manager.hedge_pnl("LONG", 0.05, 80000.0, 88000.0) == pytest.approx(400.0)


def test_kaldirac_usd_kar_zarari_degistirmez():
    """
    En kolay karıştırılan nokta: 2X ile açılan pozisyon, aynı miktardaki 1X
    pozisyonla AYNI doları kazanır. Kaldıraç yalnızca teminatı yarıya indirir,
    kârı ikiye katlamaz. Bu testin amacı o yanılgının koda sızmasını önlemek.
    """
    data = {
        "wallets": {"usdt_cash": 0.0}, "transactions": [], "next_tx_id": 1,
        "hedges": [
            {"id": 1, "coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
             "entry_price": 80000.0, "leverage": 1.0, "status": "Açık"},
            {"id": 2, "coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
             "entry_price": 80000.0, "leverage": 2.0, "status": "Açık"},
        ],
        "next_hedge_id": 3,
    }
    fiyatlar = {"BTCUSDT": {"price": 72000.0, "source": "TEST"}}
    sonuc = data_manager.calculate_hedge_metrics(data, fiyatlar)
    bir_x = next(h for h in sonuc["hedges"] if h["id"] == 1)
    iki_x = next(h for h in sonuc["hedges"] if h["id"] == 2)

    assert bir_x["unrealized_pnl_usd"] == pytest.approx(iki_x["unrealized_pnl_usd"]), \
        "Kaldıraç USD K/Z'yi değiştirmemeli"
    assert iki_x["margin_usd"] == pytest.approx(bir_x["margin_usd"] / 2), \
        "2X yarı marj bağlamalı"
    assert iki_x["roe_pct"] == pytest.approx(bir_x["roe_pct"] * 2), \
        "Aynı K/Z, yarı marj → iki kat ROE"


def test_roe_marja_gore_hesaplanir():
    data = {
        "wallets": {}, "transactions": [], "next_tx_id": 1,
        "hedges": [{"id": 1, "coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
                    "entry_price": 80000.0, "leverage": 2.0, "status": "Açık"}],
        "next_hedge_id": 2,
    }
    h = data_manager.calculate_hedge_metrics(
        data, {"BTCUSDT": {"price": 72000.0}})["hedges"][0]
    # nominal 4000, marj 2000, K/Z 400 → ROE %20
    assert h["notional_usd"] == pytest.approx(4000.0)
    assert h["margin_usd"] == pytest.approx(2000.0)
    assert h["roe_pct"] == pytest.approx(20.0)


def test_komisyon_kar_zarardan_dusulur():
    data = {
        "wallets": {}, "transactions": [], "next_tx_id": 1,
        "hedges": [{"id": 1, "coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
                    "entry_price": 80000.0, "leverage": 1.0, "fee_usd": 25.0,
                    "status": "Açık"}],
        "next_hedge_id": 2,
    }
    h = data_manager.calculate_hedge_metrics(
        data, {"BTCUSDT": {"price": 72000.0}})["hedges"][0]
    assert h["unrealized_pnl_usd"] == pytest.approx(375.0)


# ===========================================================================
# NET MARUZİYET
# ===========================================================================

def _spot_ve_hedge():
    return {
        "wallets": {"usdt_cash": 1000.0, "futures_balance": 500.0},
        "transactions": [
            {"id": 1, "date": "2026-01-01", "coin": "BTCUSDT", "exchange": "BINANCE",
             "qty": 0.1, "cost": 70000.0, "status": "Aktif"},
        ],
        "next_tx_id": 2,
        "hedges": [
            {"id": 1, "coin": "BTCUSDT", "exchange": "BINANCE", "direction": "SHORT",
             "qty": 0.05, "entry_price": 80000.0, "leverage": 2.0, "status": "Açık"},
        ],
        "next_hedge_id": 2,
    }


def test_net_maruziyet_ve_korunma_orani():
    data = _spot_ve_hedge()
    fiyatlar = {"BTCUSDT": {"price": 72000.0, "open_price": 78000.0,
                            "change_pct": -7.7, "source": "BINANCE"}}
    m = data_manager.calculate_portfolio_metrics(data, fiyatlar)
    e = next(x for x in m["exposures"] if x["display_name"] == "BTC")

    assert e["spot_qty"] == pytest.approx(0.1)
    assert e["short_qty"] == pytest.approx(0.05)
    assert e["net_qty"] == pytest.approx(0.05)
    assert e["coverage_pct"] == pytest.approx(50.0)
    assert e["net_value_usd"] == pytest.approx(0.05 * 72000.0)


def test_hedgesiz_coin_maruziyet_listesinde_yer_almaz():
    data = _spot_ve_hedge()
    data["transactions"].append({
        "id": 2, "date": "2026-01-02", "coin": "ETHUSDT", "exchange": "BINANCE",
        "qty": 1.0, "cost": 2000.0, "status": "Aktif"})
    m = data_manager.calculate_portfolio_metrics(
        data, {"BTCUSDT": {"price": 72000.0}, "ETHUSDT": {"price": 2500.0}})
    semboller = [e["display_name"] for e in m["exposures"]]
    assert "BTC" in semboller
    assert "ETH" not in semboller, "Hedge'i olmayan coin maruziyet tablosunu şişirmemeli"


def test_hedge_kar_zarari_toplam_kasaya_eklenir():
    data = _spot_ve_hedge()
    fiyatlar = {"BTCUSDT": {"price": 72000.0, "open_price": 72000.0, "change_pct": 0.0}}
    m = data_manager.calculate_portfolio_metrics(data, fiyatlar)
    k = m["kpis"]
    # spot 7200 + nakit 1000 + vadeli 500 + hedge 400
    assert k["hedge_unrealized_pnl_usd"] == pytest.approx(400.0)
    assert k["total_kasa"] == pytest.approx(9100.0)
    assert k["hedge_margin_usd"] == pytest.approx(2000.0)
    assert k["open_hedge_count"] == 1


def test_hedge_yokken_toplam_kasa_degismez(kayitli_portfoy):
    """Regresyon: hedge katmanı, hedge'i olmayan portföyü etkilememeli."""
    fiyatlar = {"BTCUSDT": {"price": 100000.0, "open_price": 98000.0, "change_pct": 2.0}}
    m = data_manager.calculate_portfolio_metrics(kayitli_portfoy, fiyatlar)
    assert m["kpis"]["hedge_unrealized_pnl_usd"] == 0.0
    assert m["hedges"] == []
    assert m["exposures"] == []


# ===========================================================================
# DOĞRULAMA
# ===========================================================================

@pytest.mark.parametrize("bozuk,beklenen", [
    ({"coin": "", "qty": 1, "entry_price": 1}, "coin"),
    ({"coin": "BTC", "qty": 0, "entry_price": 1}, "miktar"),
    ({"coin": "BTC", "qty": 1, "entry_price": 0}, "giriş"),
    ({"coin": "BTC", "qty": 1, "entry_price": 1, "leverage": 0}, "kaldıraç"),
    ({"coin": "BTC", "qty": 1, "entry_price": 1, "leverage": 200}, "kaldıraç"),
    ({"coin": "BTC", "qty": 1, "entry_price": 1, "direction": "YANLIS"}, "yön"),
])
def test_gecersiz_hedge_reddedilir(bozuk, beklenen):
    temiz, hata = data_manager.validate_hedge_payload(bozuk)
    assert temiz is None
    assert beklenen in hata.lower()


def test_teminattan_miktar_turetilir():
    """
    Kullanıcı pozisyonu "100$ teminatla 2X" diye düşünür, coin miktarı diye
    değil. Miktar verilmediğinde teminattan türetilmeli:
      nominal = 100 × 2 = 200 ; miktar = 200 / 80000 = 0.0025
    """
    temiz, hata = data_manager.validate_hedge_payload({
        "coin": "BTCUSDT", "direction": "SHORT",
        "margin_usd": 100.0, "entry_price": 80000.0, "leverage": 2.0
    })
    assert hata is None
    assert temiz["qty"] == pytest.approx(0.0025)


def test_teminattan_turetilen_pozisyonun_marji_girilen_teminata_esittir():
    """Tur kapanışı: 100$ teminatla açılan pozisyonun marjı yine 100$ olmalı."""
    temiz, _ = data_manager.validate_hedge_payload({
        "coin": "BTCUSDT", "margin_usd": 100.0, "entry_price": 80000.0, "leverage": 2.0})
    data = {"wallets": {}, "transactions": [], "next_tx_id": 1,
            "hedges": [{"id": 1, "status": "Açık", **temiz}], "next_hedge_id": 2}
    h = data_manager.calculate_hedge_metrics(data, {"BTCUSDT": {"price": 80000.0}})["hedges"][0]
    assert h["margin_usd"] == pytest.approx(100.0)
    assert h["notional_usd"] == pytest.approx(200.0)


def test_miktar_verilirse_teminat_yok_sayilir():
    temiz, hata = data_manager.validate_hedge_payload({
        "coin": "BTCUSDT", "qty": 0.05, "margin_usd": 999999.0,
        "entry_price": 80000.0, "leverage": 2.0})
    assert hata is None
    assert temiz["qty"] == pytest.approx(0.05)


def test_sifir_teminat_reddedilir():
    temiz, hata = data_manager.validate_hedge_payload({
        "coin": "BTCUSDT", "margin_usd": 0, "entry_price": 80000.0, "leverage": 2.0})
    assert temiz is None
    assert "teminat" in hata.lower() or "miktar" in hata.lower()


def test_ne_miktar_ne_teminat_verilirse_reddedilir():
    temiz, hata = data_manager.validate_hedge_payload({
        "coin": "BTCUSDT", "entry_price": 80000.0, "leverage": 2.0})
    assert temiz is None


def test_acik_hedge_silinebilir_ve_bakiyeye_dokunmaz(kayitli_portfoy):
    """
    Yanlış girilen bir kaydı düzeltmenin tek temiz yolu silmektir.
    Açık pozisyon silmek hiçbir cüzdan değerini değiştirmemeli.
    """
    data_manager.open_hedge({"coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
                             "entry_price": 80000.0, "leverage": 2.0})
    once = float(data_manager.load_portfolio()["wallets"].get("futures_balance", 0.0))

    assert data_manager.delete_hedge(1) is True

    sonra = data_manager.load_portfolio()
    assert sonra["hedges"] == []
    assert float(sonra["wallets"].get("futures_balance", 0.0)) == pytest.approx(once)


def test_teminat_ucu_uzerinden_hedge_acilir(client):
    r = client.post("/api/hedges", json={
        "coin": "BTCUSDT", "direction": "SHORT",
        "margin_usd": 100.0, "entry_price": 80000.0, "leverage": 2.0})
    assert r.status_code == 200
    h = r.json()["hedges"][0]
    assert h["qty"] == pytest.approx(0.0025)
    assert h["margin_usd"] == pytest.approx(100.0)


def test_gecerli_hedge_normalize_edilir():
    temiz, hata = data_manager.validate_hedge_payload({
        "coin": "btcusdt", "direction": "short", "qty": "0.05",
        "entry_price": "80000", "leverage": "2"
    })
    assert hata is None
    assert temiz["coin"] == "BTCUSDT"
    assert temiz["direction"] == "SHORT"
    assert temiz["qty"] == 0.05


# ===========================================================================
# AÇMA / KAPATMA AKIŞI
# ===========================================================================

def test_hedge_acilir_ve_id_artar(kayitli_portfoy):
    kayit, hata = data_manager.open_hedge({
        "coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
        "entry_price": 80000.0, "leverage": 2.0})
    assert hata is None
    assert kayit["id"] == 1
    assert kayit["status"] == "Açık"
    assert data_manager.load_portfolio()["next_hedge_id"] == 2


def test_hedge_kapaninca_gerceklesmis_kz_vadeli_bakiyeye_islenir(kayitli_portfoy):
    data_manager.open_hedge({"coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
                             "entry_price": 80000.0, "leverage": 2.0})
    once = float(data_manager.load_portfolio()["wallets"].get("futures_balance", 0.0))

    kapali, hata = data_manager.close_hedge(1, 72000.0)
    assert hata is None
    assert kapali["status"] == "Kapandı"
    assert kapali["realized_pnl_usd"] == pytest.approx(400.0)

    sonra = float(data_manager.load_portfolio()["wallets"]["futures_balance"])
    assert sonra == pytest.approx(once + 400.0)


def test_kapali_hedge_tekrar_kapatilamaz(kayitli_portfoy):
    data_manager.open_hedge({"coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
                             "entry_price": 80000.0, "leverage": 1.0})
    data_manager.close_hedge(1, 72000.0)
    _, hata = data_manager.close_hedge(1, 70000.0)
    assert "zaten kapatıl" in hata.lower()


def test_kapanan_hedge_gerceklesmemis_kz_uretmez(kayitli_portfoy):
    """Çift sayma olmamalı: kapanınca tutar bakiyeye geçer, K/Z sıfırlanır."""
    data_manager.open_hedge({"coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
                             "entry_price": 80000.0, "leverage": 1.0})
    data_manager.close_hedge(1, 72000.0)

    data = data_manager.load_portfolio()
    m = data_manager.calculate_portfolio_metrics(data, {"BTCUSDT": {"price": 72000.0}})
    assert m["kpis"]["hedge_unrealized_pnl_usd"] == 0.0
    assert m["hedge_kpis"]["realized_pnl_usd"] == pytest.approx(400.0)
    assert m["hedge_kpis"]["open_count"] == 0


def test_olmayan_hedge_kapatilamaz(kayitli_portfoy):
    _, hata = data_manager.close_hedge(999, 100.0)
    assert "bulunamadı" in hata.lower()


def test_gecersiz_kapanis_fiyati_reddedilir(kayitli_portfoy):
    data_manager.open_hedge({"coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
                             "entry_price": 80000.0, "leverage": 1.0})
    for kotu in (0, -5, "abc"):
        _, hata = data_manager.close_hedge(1, kotu)
        assert hata


def test_hedge_silinir(kayitli_portfoy):
    data_manager.open_hedge({"coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
                             "entry_price": 80000.0, "leverage": 1.0})
    assert data_manager.delete_hedge(1) is True
    assert data_manager.delete_hedge(1) is False


def test_hedge_islemleri_spot_defterini_bozmaz(kayitli_portfoy):
    """
    Kural #2: hedge katmanı 73 işlemlik spot defterine dokunmamalı.
    Aç, kapat, sil — üçünde de işlem sayısı ve next_tx_id sabit kalmalı.
    """
    once = data_manager.load_portfolio()
    tx_sayisi, next_id = len(once["transactions"]), once["next_tx_id"]

    data_manager.open_hedge({"coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
                             "entry_price": 80000.0, "leverage": 2.0})
    data_manager.close_hedge(1, 72000.0)
    data_manager.delete_hedge(1)

    sonra = data_manager.load_portfolio()
    assert len(sonra["transactions"]) == tx_sayisi
    assert sonra["next_tx_id"] == next_id


# ===========================================================================
# SENARYO
# ===========================================================================

def test_senaryo_spot_ve_hedge_etkisini_ayirir():
    data = _spot_ve_hedge()
    fiyatlar = {"BTCUSDT": {"price": 72000.0}}
    m = data_manager.calculate_portfolio_metrics(data, fiyatlar)
    s = data_manager.hedge_scenario(data, fiyatlar, m["consolidated_coins"], -20.0)

    # BTC 72000 → 57600. Spot 0.1 adet: -1440. Short 0.05 adet: +720.
    assert s["total_spot_delta_usd"] == pytest.approx(-1440.0)
    assert s["total_hedge_delta_usd"] == pytest.approx(720.0)
    assert s["total_net_delta_usd"] == pytest.approx(-720.0)


def test_tam_korunmus_pozisyonda_net_etki_sifirdir():
    data = _spot_ve_hedge()
    data["hedges"][0]["qty"] = 0.1   # spot ile birebir
    fiyatlar = {"BTCUSDT": {"price": 72000.0}}
    m = data_manager.calculate_portfolio_metrics(data, fiyatlar)
    s = data_manager.hedge_scenario(data, fiyatlar, m["consolidated_coins"], -25.0)
    assert s["total_net_delta_usd"] == pytest.approx(0.0)


# ===========================================================================
# API UÇLARI
# ===========================================================================

def test_hedge_listesi_ucu(client):
    r = client.get("/api/hedges")
    assert r.status_code == 200
    assert r.json()["hedges"] == []


def test_hedge_acma_ucu(client):
    r = client.post("/api/hedges", json={
        "coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
        "entry_price": 80000.0, "leverage": 2.0})
    assert r.status_code == 200
    assert r.json()["hedge"]["id"] == 1
    assert len(r.json()["hedges"]) == 1


def test_gecersiz_hedge_acma_400_doner(client):
    r = client.post("/api/hedges", json={"coin": "BTCUSDT", "qty": -1, "entry_price": 100})
    assert r.status_code == 400


def test_hedge_kapatma_ucu(client):
    client.post("/api/hedges", json={
        "coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
        "entry_price": 80000.0, "leverage": 2.0})
    r = client.post("/api/hedges/1/close", json={"close_price": 72000.0})
    assert r.status_code == 200
    assert r.json()["realized_pnl_usd"] == pytest.approx(400.0)


def test_hedge_silme_ucu(client):
    client.post("/api/hedges", json={
        "coin": "BTCUSDT", "direction": "SHORT", "qty": 0.05,
        "entry_price": 80000.0, "leverage": 1.0})
    assert client.delete("/api/hedges/1").status_code == 200
    assert client.delete("/api/hedges/1").status_code == 404


def test_senaryo_ucu(client):
    client.post("/api/hedges", json={
        "coin": "BTCUSDT", "direction": "SHORT", "qty": 0.005,
        "entry_price": 100000.0, "leverage": 2.0})
    r = client.get("/api/hedges/scenario?move_pct=-20")
    assert r.status_code == 200
    veri = r.json()
    assert veri["move_pct"] == -20.0
    assert veri["total_hedge_delta_usd"] > 0, "Düşüşte short kazanmalı"
    assert veri["total_spot_delta_usd"] < 0, "Düşüşte spot kaybetmeli"


def test_portfoy_ucu_hedge_alanlarini_dondurur(client):
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    veri = r.json()
    assert "hedges" in veri and "exposures" in veri and "hedge_kpis" in veri
