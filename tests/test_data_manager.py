"""
data_manager.py birim testleri (FAZ C2)

Kapsam: PIN & kurtarma anahtarı, API anahtarı obfuscation, atomik yazma,
konsolidasyon matematiği, FIFO / Konsolide Ortalama satış motoru,
gerçekleşmiş K/Z hesabı ve gerçek veride karşılaşılan edge case'ler.
"""

import os
import copy
import json

import pytest

import data_manager as dm
from conftest import SAHTE_FIYATLAR


# ===========================================================================
# PIN GÜVENLİĞİ & KURTARMA ANAHTARI
# ===========================================================================

def test_hash_pin_ayni_salt_ile_ayni_sonucu_verir():
    h1, salt = dm.hash_pin("1234")
    h2, _ = dm.hash_pin("1234", salt)
    assert h1 == h2
    assert len(h1) == 64          # sha256 hex
    assert len(salt) == 32        # token_hex(16)


def test_hash_pin_her_cagirmada_farkli_salt_uretir():
    _, salt1 = dm.hash_pin("1234")
    _, salt2 = dm.hash_pin("1234")
    assert salt1 != salt2, "Salt rastgele olmalı, aksi halde rainbow table riski doğar"


def test_pin_kurulumu_ve_dogrulama():
    sonuc = dm.set_pin("3072", auto_lock_minutes=5)
    assert sonuc["success"] is True
    assert dm.verify_pin("3072") is True
    assert dm.verify_pin("1379") is False


def test_pin_kapali_iken_her_pin_kabul_edilir():
    """PIN koruması kurulmamışsa uygulama kilitlenmemeli."""
    assert dm.verify_pin("herhangi-bir-sey") is True


def test_set_pin_12_haneli_kurtarma_anahtari_uretir():
    sonuc = dm.set_pin("1111")
    anahtar = sonuc["recovery_key"]
    assert len(anahtar) == 12
    assert anahtar == anahtar.upper()
    assert all(c in "0123456789ABCDEF" for c in anahtar)


def test_kurtarma_anahtari_ile_pin_sifirlama():
    anahtar = dm.set_pin("1111")["recovery_key"]

    assert dm.verify_recovery_key(anahtar) is True
    assert dm.verify_recovery_key("YANLISANAHTAR") is False

    sonuc = dm.reset_pin_with_recovery(anahtar, "9999")
    assert sonuc["success"] is True
    assert dm.verify_pin("9999") is True
    assert dm.verify_pin("1111") is False


def test_kurtarma_anahtari_sifirlamadan_sonra_yenilenir():
    """Kullanılan anahtar tekrar kullanılamamalı."""
    eski = dm.set_pin("1111")["recovery_key"]
    sonuc = dm.reset_pin_with_recovery(eski, "2222")
    yeni = sonuc["recovery_key"]

    assert yeni != eski
    assert dm.verify_recovery_key(eski) is False
    assert dm.verify_recovery_key(yeni) is True


def test_gecersiz_kurtarma_anahtari_pini_degistirmez():
    dm.set_pin("1111")
    sonuc = dm.reset_pin_with_recovery("GECERSIZ00000", "9999")
    assert sonuc["success"] is False
    assert dm.verify_pin("1111") is True, "Başarısız kurtarma mevcut PIN'i bozmamalı"


def test_pin_degistirme_ve_kaldirma():
    dm.set_pin("1111")
    assert dm.change_pin("yanlis", "2222") is False
    assert dm.change_pin("1111", "2222") is True
    assert dm.verify_pin("2222") is True

    assert dm.disable_pin("yanlis") is False
    assert dm.disable_pin("2222") is True
    assert dm.load_settings()["security"]["pin_enabled"] is False


# ===========================================================================
# API ANAHTARI OBFUSCATION (B2)
# ===========================================================================

def test_obfuscation_gidis_donus():
    acik = "AIzaSyD-ornek-gemini-anahtari-1234567890"
    kodlu = dm._obfuscate_key(acik)
    assert kodlu != acik
    assert dm._deobfuscate_key(kodlu) == acik


def test_bos_anahtar_obfuscate_edilmez():
    assert dm._obfuscate_key("") == ""
    assert dm._deobfuscate_key("") == ""


def test_load_settings_modul_sabitini_kirletmez():
    """
    Regresyon testi — testlerin yakaladığı gerçek bug:

    load_settings() sığ kopya (dict()) kullandığında iç içe sözlükler
    DEFAULT_SETTINGS ile paylaşılıyordu. Yeni kurulumda (settings.json henüz
    yokken) ilk set_pin() çağrısı, kullanıcının PIN hash'ini ve salt'ını
    modül seviyesindeki global şablona yazıyordu. Düzeltme: copy.deepcopy.
    """
    varsayilan_once = copy.deepcopy(dm.DEFAULT_SETTINGS)

    # Ayar dosyası YOKKEN doğrudan PIN kur — sızıntının tetiklendiği yol
    assert not os.path.exists(dm.SETTINGS_FILE)
    dm.set_pin("3072")

    assert dm.DEFAULT_SETTINGS == varsayilan_once, (
        "set_pin() modül sabiti DEFAULT_SETTINGS'i değiştirmemeli"
    )
    assert dm.DEFAULT_SETTINGS["security"]["pin_enabled"] is False
    assert dm.DEFAULT_SETTINGS["security"]["pin_hash"] == ""
    assert "recovery_hash" not in dm.DEFAULT_SETTINGS["security"]


def test_load_settings_her_cagirmada_bagimsiz_nesne_dondurur():
    a = dm.load_settings()
    b = dm.load_settings()
    a["security"]["pin_enabled"] = True
    assert b["security"]["pin_enabled"] is False, "Dönen sözlükler paylaşılmamalı"


def test_ayarlar_diske_kodlanmis_yazilir_okurken_cozulur():
    acik = "AIzaSyD-ornek-gemini-anahtari-1234567890"
    ayarlar = dm.load_settings()
    ayarlar["api_keys"]["gemini_api_key"] = acik
    dm.save_settings(ayarlar)

    # Diskteki ham içerik açık metin İÇERMEMELİ
    with open(dm.SETTINGS_FILE, "r", encoding="utf-8") as f:
        ham = f.read()
    assert acik not in ham, "API anahtarı diske açık metin yazılmamalı"

    # load_settings çözerek döndürmeli
    assert dm.load_settings()["api_keys"]["gemini_api_key"] == acik


# ===========================================================================
# ATOMİK YAZMA & YEDEKLEME (Kural #3)
# ===========================================================================

def test_kaydet_yukle_gidis_donusu(ornek_portfoy):
    dm.save_portfolio(ornek_portfoy)
    okunan = dm.load_portfolio()
    assert okunan["next_tx_id"] == 7
    assert len(okunan["transactions"]) == 6


def test_kaydetme_gecici_dosya_birakmaz(ornek_portfoy):
    dm.save_portfolio(ornek_portfoy)
    kalanlar = [f for f in os.listdir(dm.DATA_DIR) if f.endswith(".tmp")]
    assert kalanlar == [], "Atomik yazma sonrası .tmp dosyası kalmamalı"


def test_kaydetme_gunluk_yedek_olusturur(ornek_portfoy):
    dm.save_portfolio(ornek_portfoy)
    yedekler = [f for f in os.listdir(dm.BACKUP_DIR) if f.startswith("portfolio_backup_")]
    assert len(yedekler) == 1


def test_bozuk_json_yedekten_kurtarilir(ornek_portfoy):
    """Kural #6: Dosya bozulursa uygulama çökmemeli, yedekten dönmeli."""
    dm.save_portfolio(ornek_portfoy)          # yedek oluşur
    with open(dm.DATA_FILE, "w", encoding="utf-8") as f:
        f.write("{ bu gecerli json degil ===")

    kurtarilan = dm.load_portfolio()
    assert len(kurtarilan["transactions"]) == 6, "Bozuk dosya yedekten kurtarılmalı"


# ===========================================================================
# KONSOLİDASYON MATEMATİĞİ
# ===========================================================================

def test_ayni_coin_iki_lot_konsolide_edilir(ornek_portfoy):
    m = dm.calculate_portfolio_metrics(ornek_portfoy, SAHTE_FIYATLAR)
    btc = next(c for c in m["consolidated_coins"] if c["pos_key"] == "BTCUSDT@BINANCE")

    assert btc["dca_count"] == 2
    assert btc["total_qty"] == pytest.approx(0.02)
    assert btc["total_invested"] == pytest.approx(1700.0)   # 800 + 900
    assert btc["avg_cost"] == pytest.approx(85000.0)        # 1700 / 0.02
    assert btc["current_value"] == pytest.approx(2000.0)    # 0.02 * 100000
    assert btc["pnl_usd"] == pytest.approx(300.0)
    assert btc["pnl_pct"] == pytest.approx(300.0 / 1700.0 * 100.0)


def test_zararda_pozisyon_basabas_yukselisi(ornek_portfoy):
    m = dm.calculate_portfolio_metrics(ornek_portfoy, SAHTE_FIYATLAR)
    eth = next(c for c in m["consolidated_coins"] if c["pos_key"] == "ETHUSDT@BINANCE")

    assert eth["pnl_usd"] == pytest.approx(-500.0)          # 2000 - 2500
    # 2500'e dönmek için 2000'den +%25 gerekir
    assert eth["breakeven_req_rise_pct"] == pytest.approx(25.0)
    assert eth["profit_margin_pct"] == 0.0


def test_farkli_borsalar_ayri_pozisyon_olur(ornek_portfoy):
    """XAUT@MEXC ile XAUT@BINANCE karışmamalı — pos_key borsayı içerir."""
    ornek_portfoy["transactions"].append(
        {"id": 99, "date": "2026-04-01", "coin": "BTCUSDT", "exchange": "MEXC",
         "qty": 0.005, "cost": 95000.0, "status": "Aktif", "notes": "", "category": "Majör / L1"}
    )
    m = dm.calculate_portfolio_metrics(ornek_portfoy, SAHTE_FIYATLAR)
    anahtarlar = {c["pos_key"] for c in m["consolidated_coins"]}

    assert "BTCUSDT@BINANCE" in anahtarlar
    assert "BTCUSDT@MEXC" in anahtarlar


def test_borsa_bazli_kasa_kirilimi(ornek_portfoy):
    m = dm.calculate_portfolio_metrics(ornek_portfoy, SAHTE_FIYATLAR)
    kpis = m["exchange_kpis"]

    assert kpis["BINANCE"]["spot_invested"] == pytest.approx(4200.0)   # 1700 + 2500 + 0
    assert kpis["BINANCE"]["usdt_cash"] == pytest.approx(800.0)
    assert kpis["DEX"]["spot_invested"] == pytest.approx(27.0)         # CPL
    # Toplam kasa = spot değer + tüm nakit
    assert kpis["ALL"]["total_kasa"] == pytest.approx(4005.4 + 1000.0)


def test_portfoy_paylari_yuzde_yuz_eder(ornek_portfoy):
    m = dm.calculate_portfolio_metrics(ornek_portfoy, SAHTE_FIYATLAR)
    toplam_pay = sum(c["portfolio_share_pct"] for c in m["consolidated_coins"])
    assert toplam_pay == pytest.approx(100.0)


# ===========================================================================
# EDGE CASE'LER (gerçek veriden)
# ===========================================================================

def test_sifir_miktarli_aktif_islem_cokmez(ornek_portfoy):
    """Gerçek veride id 35 (EIGENUSDT) ve id 41 (MAVUSDT) böyle — sıfıra bölme riski."""
    m = dm.calculate_portfolio_metrics(ornek_portfoy, SAHTE_FIYATLAR)
    sol = next(c for c in m["consolidated_coins"] if c["pos_key"] == "SOLUSDT@BINANCE")

    assert sol["total_qty"] == 0.0
    assert sol["avg_cost"] == 0.0, "Sıfıra bölme yerine 0 dönmeli"
    assert sol["pnl_pct"] == 0.0


def test_nano_fiyatli_token_hassasiyeti(ornek_portfoy):
    """CPL gibi 1e-08 maliyetli tokenlarda hassasiyet kaybolmamalı."""
    m = dm.calculate_portfolio_metrics(ornek_portfoy, SAHTE_FIYATLAR)
    cpl = next(c for c in m["consolidated_coins"] if c["pos_key"] == "CPLUSDT@DEX")

    assert cpl["total_invested"] == pytest.approx(27.0)
    assert cpl["current_value"] == pytest.approx(5.4)
    assert cpl["avg_cost"] == pytest.approx(1.0e-08)
    assert cpl["is_dex"] is True


def test_bos_portfoy_cokmez():
    bos = {"wallets": {"usdt_cash": 0.0}, "transactions": [], "next_tx_id": 1}
    m = dm.calculate_portfolio_metrics(bos, SAHTE_FIYATLAR)

    assert m["consolidated_coins"] == []
    assert m["kpis"]["net_pnl_pct"] == 0.0
    assert m["kpis"]["total_kasa"] == 0.0


def test_fiyati_bulunamayan_coin_maliyetine_duser(ornek_portfoy):
    """Kural #6: Fiyat yoksa maliyet kullanılır, pozisyon kaybolmaz."""
    ornek_portfoy["transactions"].append(
        {"id": 98, "date": "2026-04-01", "coin": "BILINMEYENUSDT", "exchange": "BINANCE",
         "qty": 10.0, "cost": 5.0, "status": "Aktif", "notes": "", "category": "Altcoin"}
    )
    m = dm.calculate_portfolio_metrics(ornek_portfoy, SAHTE_FIYATLAR)
    bilinmeyen = next(c for c in m["consolidated_coins"] if "BILINMEYEN" in c["pos_key"])

    assert bilinmeyen["live_price"] == pytest.approx(5.0)
    assert bilinmeyen["pnl_usd"] == pytest.approx(0.0)


# ===========================================================================
# SATIŞ MOTORU — KONSOLİDE ORTALAMA (varsayılan, Kural #4)
# ===========================================================================

def test_konsolide_ortalama_kismi_satis(kayitli_portfoy):
    sonuc = dm.execute_target_sale(
        "BTCUSDT@BINANCE", sell_price=100000.0, sell_qty=0.01,
        cost_method="Konsolide Ortalama"
    )

    assert sonuc["cost_method"] == "Konsolide Ortalama"
    assert sonuc["qty_sold"] == pytest.approx(0.01)
    assert sonuc["proceeds"] == pytest.approx(1000.0)

    data = dm.load_portfolio()
    aktifler = [t for t in data["transactions"]
                if t["coin"] == "BTCUSDT" and t["status"] == "Aktif"]
    # Her iki lot da orantılı yarıya iner (0.01 → 0.005)
    assert len(aktifler) == 2
    assert all(t["qty"] == pytest.approx(0.005) for t in aktifler)

    kapanan = next(t for t in data["transactions"]
                   if t["coin"] == "BTCUSDT" and t["status"] == "Kapandı / İzleme")
    assert kapanan["cost"] == pytest.approx(85000.0)          # ortalama maliyet
    assert kapanan["realized_pnl_usd"] == pytest.approx(150.0)  # (100000-85000)*0.01


def test_konsolide_ortalama_tam_satis_lotlari_kapatir(kayitli_portfoy):
    dm.execute_target_sale("BTCUSDT@BINANCE", sell_price=100000.0, sell_qty=0.02)

    data = dm.load_portfolio()
    aktifler = [t for t in data["transactions"]
                if t["coin"] == "BTCUSDT" and t["status"] == "Aktif"]
    assert aktifler == [], "Tam satışta tüm lotlar kapanmalı"


def test_satis_nakdi_dogru_borsaya_eklenir(kayitli_portfoy):
    onceki = dm.load_portfolio()["wallets"]["exchange_cash"]["BINANCE"]
    dm.execute_target_sale("BTCUSDT@BINANCE", sell_price=100000.0, sell_qty=0.01)

    cuzdan = dm.load_portfolio()["wallets"]
    assert cuzdan["exchange_cash"]["BINANCE"] == pytest.approx(onceki + 1000.0)
    # usdt_cash borsa kasalarının toplamı olmalı
    assert cuzdan["usdt_cash"] == pytest.approx(sum(cuzdan["exchange_cash"].values()))


def test_komisyon_nakitten_dusulur(kayitli_portfoy):
    onceki = dm.load_portfolio()["wallets"]["exchange_cash"]["BINANCE"]
    sonuc = dm.execute_target_sale(
        "BTCUSDT@BINANCE", sell_price=100000.0, sell_qty=0.01,
        fee_amount=5.0, fee_asset="USDT", fee_usd=5.0
    )

    assert sonuc["cash_added"] == pytest.approx(995.0)   # 1000 - 5
    cuzdan = dm.load_portfolio()["wallets"]
    assert cuzdan["exchange_cash"]["BINANCE"] == pytest.approx(onceki + 995.0)


# ===========================================================================
# SATIŞ MOTORU — FIFO (A3 düzeltmesi: orantılı komisyon dağıtımı)
# ===========================================================================

def test_fifo_lotlari_sirayla_tuketir(kayitli_portfoy):
    """İlk giren ilk çıkar: 80.000 maliyetli lot önce tüketilmeli."""
    dm.execute_target_sale(
        "BTCUSDT@BINANCE", sell_price=100000.0, sell_qty=0.01, cost_method="FIFO"
    )

    data = dm.load_portfolio()
    lot1 = next(t for t in data["transactions"] if t["id"] == 1)
    lot2 = next(t for t in data["transactions"] if t["id"] == 2)

    assert lot1["status"] == "Kapandı / İzleme", "Eski lot (80.000) önce tüketilmeli"
    assert lot1["cost_method"] == "FIFO"
    assert lot2["status"] == "Aktif", "Yeni lot (90.000) dokunulmadan kalmalı"
    assert lot1["realized_pnl_usd"] == pytest.approx(200.0)   # (100000-80000)*0.01


def test_fifo_komisyonu_lotlara_orantili_dagitir(kayitli_portfoy):
    """
    FAZ A3 düzeltmesinin regresyon testi:
      lot_fee = fee_val_usd * (lot_exit_value / total_proceeds)

    İki eşit büyüklükte lot satıldığında 20$ komisyon 10$ + 10$ olarak bölünmeli.
    """
    dm.execute_target_sale(
        "BTCUSDT@BINANCE", sell_price=100000.0, sell_qty=0.02,
        fee_amount=20.0, fee_asset="USDT", fee_usd=20.0, cost_method="FIFO"
    )

    data = dm.load_portfolio()
    lot1 = next(t for t in data["transactions"] if t["id"] == 1)
    lot2 = next(t for t in data["transactions"] if t["id"] == 2)

    assert lot1["fee_usd"] == pytest.approx(10.0)
    assert lot2["fee_usd"] == pytest.approx(10.0)
    # Komisyonların toplamı orijinal komisyonu aşmamalı (çift sayım hatası)
    assert lot1["fee_usd"] + lot2["fee_usd"] == pytest.approx(20.0)

    # Net K/Z komisyon düşülmüş olmalı
    assert lot1["realized_pnl_usd"] == pytest.approx(190.0)   # 200 - 10
    assert lot2["realized_pnl_usd"] == pytest.approx(90.0)    # 100 - 10


def test_fifo_kismi_lot_bolunmesi(kayitli_portfoy):
    """0.015 satışta ilk lot tamamen, ikinci lot kısmen tüketilir."""
    dm.execute_target_sale(
        "BTCUSDT@BINANCE", sell_price=100000.0, sell_qty=0.015, cost_method="FIFO"
    )

    data = dm.load_portfolio()
    lot1 = next(t for t in data["transactions"] if t["id"] == 1)
    lot2 = next(t for t in data["transactions"] if t["id"] == 2)

    assert lot1["status"] == "Kapandı / İzleme"      # 0.01 tamamen tüketildi
    assert lot2["status"] == "Aktif"
    assert lot2["qty"] == pytest.approx(0.005), "Kalan miktar lotta durmalı"

    # İkinci lottan kopan 0.005'lik parça için yeni kapanış kaydı oluşmalı
    yeni_kayitlar = [t for t in data["transactions"]
                     if t["id"] > 6 and t["status"] == "Kapandı / İzleme"]
    assert len(yeni_kayitlar) == 1
    assert yeni_kayitlar[0]["qty"] == pytest.approx(0.005)
    assert yeni_kayitlar[0]["cost"] == pytest.approx(90000.0)

    # Satılan toplam miktar korunmalı: 0.01 (lot1) + 0.005 (lot2'den kopan)
    satilan = lot1["qty"] + yeni_kayitlar[0]["qty"]
    assert satilan == pytest.approx(0.015)


def test_aktif_islemi_olmayan_pozisyon_hata_verir(kayitli_portfoy):
    with pytest.raises(ValueError, match="aktif işlem bulunamadı"):
        dm.execute_target_sale("YOKUSDT@BINANCE", sell_price=1.0, sell_qty=1.0)


def test_tam_satis_hedefi_siler(kayitli_portfoy):
    dm.save_target("BTCUSDT@BINANCE", 100000.0, 100.0, "test hedefi")
    assert "BTCUSDT@BINANCE" in dm.load_portfolio()["targets"]

    dm.execute_target_sale("BTCUSDT@BINANCE", sell_price=100000.0, sell_qty=0.02)
    assert "BTCUSDT@BINANCE" not in dm.load_portfolio().get("targets", {})


# ===========================================================================
# HEDEF YÖNETİMİ
# ===========================================================================

def test_hedef_kaydet_ve_sil(kayitli_portfoy):
    dm.save_target("ETHUSDT@BINANCE", 3000.0, 50.0, "kısmi kâr al")
    hedef = dm.load_portfolio()["targets"]["ETHUSDT@BINANCE"]

    assert hedef["target_price"] == 3000.0
    assert hedef["target_sell_pct"] == 50.0

    assert dm.delete_target("ETHUSDT@BINANCE") is True
    assert dm.delete_target("ETHUSDT@BINANCE") is False, "İkinci silme False dönmeli"


def test_hedef_metriklere_ilerleme_ile_yansir(ornek_portfoy):
    ornek_portfoy["targets"] = {
        "ETHUSDT@BINANCE": {"target_price": 4000.0, "target_sell_pct": 50.0, "notes": ""}
    }
    m = dm.calculate_portfolio_metrics(ornek_portfoy, SAHTE_FIYATLAR)
    eth = next(c for c in m["consolidated_coins"] if c["pos_key"] == "ETHUSDT@BINANCE")

    assert eth["target"] is not None
    assert eth["target"]["sell_qty"] == pytest.approx(0.5)          # 1.0 * %50
    assert eth["target"]["cash_return"] == pytest.approx(2000.0)    # 0.5 * 4000
    assert eth["target"]["req_rise_pct"] == pytest.approx(100.0)    # 2000 → 4000
    assert eth["target"]["progress_pct"] == pytest.approx(50.0)
    assert eth["target"]["reached"] is False


# ===========================================================================
# GERÇEKLEŞMİŞ KÂR/ZARAR
# ===========================================================================

def test_gerceklesmis_kz_sadece_satilan_islemleri_sayar(ornek_portfoy):
    r = dm.calculate_realized_metrics(ornek_portfoy)

    assert r["closed_tx_count"] == 1, "Sadece exit_price/realized_pnl olan işlem sayılmalı"
    assert r["total_realized_pnl_usd"] == pytest.approx(48.0)
    assert r["winning_tx_count"] == 1
    assert r["win_rate_pct"] == 100.0
    assert r["total_fees_usd"] == pytest.approx(2.0)


def test_gerceklesmis_kz_aylik_kirilim(ornek_portfoy):
    r = dm.calculate_realized_metrics(ornek_portfoy)
    aylar = {m["month"] for m in r["monthly_breakdown"]}
    assert "2026-02" in aylar, "Aylık kırılım exit_date'e göre gruplanmalı"


def test_gerceklesmis_kz_bos_portfoyde_cokmez():
    r = dm.calculate_realized_metrics({"transactions": []})
    assert r["closed_tx_count"] == 0
    assert r["total_realized_pnl_usd"] == 0.0
    assert r["profit_factor"] == 0.0
    assert r["best_trade"] is None
