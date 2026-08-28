r"""
CoinTakip — FAZ F1 Testleri: Değer Kaybı Yazımı ve Transfer

Bu dosyanın tek bir amacı var: **defterin bozulmadığını kanıtlamak.**

İki olay birbirine karıştırılırsa portföy matematiği sessizce yanlışlanır:

  - Transfer satış sayılırsa → olmayan bir kâr/zarar ve olmayan bir nakit doğar.
  - Yazım satış sayılırsa    → ölmüş coinden nakit geldiği sanılır.

Aşağıdaki testler bu iki hatayı da yakalamak için yazılmıştır. Ayrıca
"toplam kasa" gibi kullanıcının gerçek para kararları verdiği rakamların
her işlemden sonra tutarlı kaldığı doğrulanır.

Not: conftest.py'deki `izole_veri` autouse fixture'ı sayesinde hiçbir test
gerçek data/portfolio.json dosyasına dokunmaz ve hiçbir ağ çağrısı yapılmaz.
"""

import pytest

import data_manager as dm


# =====================================================================
# Yardımcılar
# =====================================================================
def _metrics(data=None):
    from conftest import SAHTE_FIYATLAR
    if data is None:
        data = dm.load_portfolio()
    return dm.calculate_portfolio_metrics(data, dict(SAHTE_FIYATLAR))


def _pozisyon(metrics, pos_key):
    return next((c for c in metrics["consolidated_coins"] if c["pos_key"] == pos_key), None)


def _nakit(data=None):
    if data is None:
        data = dm.load_portfolio()
    return float(data.get("wallets", {}).get("usdt_cash", 0.0))


# =====================================================================
# BÖLÜM 1 — DEĞER KAYBI YAZIMI (MEZARLIK KAPANIŞI)
# =====================================================================
class TestDegerKaybiYazimi:

    def test_yazim_pozisyonu_aktiflikten_cikarir(self, kayitli_portfoy):
        onces = _metrics()
        assert _pozisyon(onces, "ETHUSDT@BINANCE") is not None

        dm.write_off_position("ETHUSDT@BINANCE", reason="rug")

        sonra = _metrics()
        assert _pozisyon(sonra, "ETHUSDT@BINANCE") is None, \
            "Yazılan pozisyon hâlâ aktif pozisyonlar arasında görünüyor."

    def test_yazim_toplam_kasayi_pozisyon_degeri_kadar_dusurur(self, kayitli_portfoy):
        onces = _metrics()
        eth_deger = _pozisyon(onces, "ETHUSDT@BINANCE")["current_value"]
        kasa_once = onces["kpis"]["total_kasa"]

        dm.write_off_position("ETHUSDT@BINANCE", reason="worthless")

        kasa_sonra = _metrics()["kpis"]["total_kasa"]
        assert kasa_sonra == pytest.approx(kasa_once - eth_deger, abs=0.01), \
            "Yazım sonrası toplam kasa, silinen pozisyonun değeri kadar düşmeliydi."

    def test_yazim_kasaya_nakit_EKLEMEZ(self, kayitli_portfoy):
        """En kritik kural: yazım satış değildir, gelir yoktur."""
        nakit_once = _nakit()
        dm.write_off_position("ETHUSDT@BINANCE")
        assert _nakit() == pytest.approx(nakit_once), \
            "Yazım nakit bakiyeyi değiştirdi — bu bir satış sanılıyor demektir."

    def test_yazim_tum_maliyeti_zarar_yazar(self, kayitli_portfoy):
        sonuc = dm.write_off_position("ETHUSDT@BINANCE", reason="delist")
        # ETH: 1.0 adet × 2500 maliyet
        assert sonuc["realized_loss_usd"] == pytest.approx(2500.0)

        realize = dm.calculate_realized_metrics(dm.load_portfolio())
        yazim = next(t for t in realize["closed_transactions"]
                     if t.get("close_reason") == "write_off")
        assert yazim["realized_pnl_usd"] == pytest.approx(-2500.0)
        assert yazim["exit_price"] == 0.0

    def test_yazim_gercek_satistan_ayri_raporlanir(self, kayitli_portfoy):
        realize_once = dm.calculate_realized_metrics(dm.load_portfolio())
        ticaret_once = realize_once["total_realized_pnl_usd"]

        dm.write_off_position("ETHUSDT@BINANCE")

        realize = dm.calculate_realized_metrics(dm.load_portfolio())
        assert realize["write_off_count"] == 1
        assert realize["total_write_off_usd"] == pytest.approx(-2500.0)
        # Yazım toplam gerçekleşmiş K/Z'ye dahildir...
        assert realize["total_realized_pnl_usd"] == pytest.approx(ticaret_once - 2500.0, abs=0.01)
        # ...ama alım-satım performansı ayrı okunabilir olmalı.
        assert realize["trading_realized_pnl_usd"] == pytest.approx(ticaret_once, abs=0.01)

    def test_yazilan_lotlar_simulasyon_listesinde_cift_sayilmaz(self, kayitli_portfoy):
        dm.write_off_position("CPLUSDT@DEX", reason="rug")
        metrics = _metrics()
        cpl_kayitlari = [s for s in metrics["simulations"] if s["coin"].startswith("CPL")]
        assert cpl_kayitlari == [], \
            "Yazılan pozisyon 'izlenen eski pozisyon' listesinde görünüyor — çift sayım riski."

    def test_yazim_coklu_lotu_tek_kayitta_toplar(self, kayitli_portfoy):
        # BTC'nin BINANCE'te iki lotu var (0.01@80000 + 0.01@90000 = 1700 maliyet)
        sonuc = dm.write_off_position("BTCUSDT@BINANCE", reason="lost")
        assert sonuc["lot_count"] == 2
        assert sonuc["qty"] == pytest.approx(0.02)
        assert sonuc["realized_loss_usd"] == pytest.approx(1700.0)

    def test_yazim_hedef_fiyat_kaydini_siler(self, kayitli_portfoy):
        dm.save_target("ETHUSDT@BINANCE", 3000.0, 50.0, "test")
        assert "ETHUSDT@BINANCE" in dm.load_portfolio().get("targets", {})

        dm.write_off_position("ETHUSDT@BINANCE")
        assert "ETHUSDT@BINANCE" not in dm.load_portfolio().get("targets", {}), \
            "Silinen pozisyonun hedef fiyatı defterde kaldı."

    def test_olmayan_pozisyon_yazimi_hata_verir(self, kayitli_portfoy):
        with pytest.raises(ValueError, match="aktif işlem bulunamadı"):
            dm.write_off_position("YOKUSDT@BINANCE")

    def test_gecersiz_gerekce_digere_dusulur(self, kayitli_portfoy):
        sonuc = dm.write_off_position("ETHUSDT@BINANCE", reason="uydurma_sebep")
        assert sonuc["reason"] == "other"

    def test_yazim_geri_alinabilir(self, kayitli_portfoy):
        kasa_once = _metrics()["kpis"]["total_kasa"]
        nakit_once = _nakit()

        sonuc = dm.write_off_position("ETHUSDT@BINANCE", reason="delist")
        geri = dm.undo_write_off(sonuc["write_off_id"])

        assert geri["restored_lots"] == 1
        metrics = _metrics()
        assert _pozisyon(metrics, "ETHUSDT@BINANCE") is not None
        assert metrics["kpis"]["total_kasa"] == pytest.approx(kasa_once, abs=0.01)
        assert _nakit() == pytest.approx(nakit_once)
        # Özet kayıt tamamen kalkmalı, yoksa hayalet bir zarar kalır.
        realize = dm.calculate_realized_metrics(dm.load_portfolio())
        assert realize["write_off_count"] == 0

    def test_olmayan_yazim_geri_alinamaz(self, kayitli_portfoy):
        with pytest.raises(ValueError, match="bulunamadı"):
            dm.undo_write_off(9999)

    def test_yazim_listesi_kayitlari_dondurur(self, kayitli_portfoy):
        dm.write_off_position("ETHUSDT@BINANCE", reason="rug", note="proje kapandı")
        kayitlar = dm.list_write_offs()
        assert len(kayitlar) == 1
        assert kayitlar[0]["write_off_reason"] == "rug"
        assert "proje kapandı" in kayitlar[0]["notes"]


# =====================================================================
# BÖLÜM 2 — TRANSFER
# =====================================================================
class TestTransfer:

    def test_transfer_maliyet_tabanini_korur(self, kayitli_portfoy):
        """Transferin varlık sebebi bu: taşınan coin maliyetini yanında götürür."""
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 1.0,
        })
        metrics = _metrics()
        hedef = _pozisyon(metrics, "ETHUSDT@DEX")
        assert hedef is not None, "Transfer edilen varlık hedefte görünmüyor."
        assert hedef["avg_cost"] == pytest.approx(2500.0), \
            "Maliyet tabanı transferde kayboldu — gelecekteki tüm K/Z yanlış olur."
        assert hedef["total_qty"] == pytest.approx(1.0)

    def test_transfer_nakit_hareketi_YARATMAZ(self, kayitli_portfoy):
        nakit_once = _nakit()
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 1.0,
        })
        assert _nakit() == pytest.approx(nakit_once), \
            "Transfer nakit üretti — satış sanılıyor demektir."

    def test_transfer_gerceklesmis_kz_YARATMAZ(self, kayitli_portfoy):
        realize_once = dm.calculate_realized_metrics(dm.load_portfolio())
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 1.0,
        })
        realize_sonra = dm.calculate_realized_metrics(dm.load_portfolio())
        assert realize_sonra["total_realized_pnl_usd"] == pytest.approx(
            realize_once["total_realized_pnl_usd"]), \
            "Transfer sahte bir gerçekleşmiş K/Z üretti."
        assert realize_sonra["closed_tx_count"] == realize_once["closed_tx_count"]

    def test_transfer_toplam_kasayi_degistirmez(self, kayitli_portfoy):
        kasa_once = _metrics()["kpis"]["total_kasa"]
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 1.0,
        })
        kasa_sonra = _metrics()["kpis"]["total_kasa"]
        assert kasa_sonra == pytest.approx(kasa_once, abs=0.01), \
            "Para yer değiştirdi diye toplam varlık değişemez."

    def test_kismi_transfer_kaynakta_kalani_birakir(self, kayitli_portfoy):
        # BTC: BINANCE'te 0.02 var, 0.005'ini taşı
        dm.transfer_position({
            "pos_key": "BTCUSDT@BINANCE", "to_exchange": "MEXC", "qty": 0.005,
        })
        metrics = _metrics()
        kaynak = _pozisyon(metrics, "BTCUSDT@BINANCE")
        hedef = _pozisyon(metrics, "BTCUSDT@MEXC")
        assert kaynak["total_qty"] == pytest.approx(0.015)
        assert hedef["total_qty"] == pytest.approx(0.005)

    def test_transfer_FIFO_sirasiyla_tuketir(self, kayitli_portfoy):
        """En eski lot (0.01 @ 80000) önce gitmeli."""
        kayit = dm.transfer_position({
            "pos_key": "BTCUSDT@BINANCE", "to_exchange": "MEXC", "qty": 0.01,
        })
        assert len(kayit["consumed"]) == 1
        assert kayit["consumed"][0]["cost"] == pytest.approx(80000.0), \
            "FIFO bozuldu: eski lot yerine yeni lot tüketildi."

        metrics = _metrics()
        assert _pozisyon(metrics, "BTCUSDT@MEXC")["avg_cost"] == pytest.approx(80000.0)
        assert _pozisyon(metrics, "BTCUSDT@BINANCE")["avg_cost"] == pytest.approx(90000.0)

    def test_coklu_lot_transferinde_her_lot_kendi_maliyetiyle_tasinir(self, kayitli_portfoy):
        """İki lot birden taşınırsa hedefte ağırlıklı ortalama doğru olmalı."""
        dm.transfer_position({
            "pos_key": "BTCUSDT@BINANCE", "to_exchange": "MEXC", "qty": 0.02,
        })
        hedef = _pozisyon(_metrics(), "BTCUSDT@MEXC")
        assert hedef["total_qty"] == pytest.approx(0.02)
        assert hedef["avg_cost"] == pytest.approx(85000.0)  # (800+900)/0.02
        assert hedef["dca_count"] == 2, "Lotlar tek kayda ezilmiş — FIFO granülaritesi kayboldu."

    def test_transfer_edilen_lot_simulasyonda_gorunmez(self, kayitli_portfoy):
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 1.0,
        })
        metrics = _metrics()
        eth_sim = [s for s in metrics["simulations"] if s["coin"].startswith("ETH")]
        assert eth_sim == [], \
            "Taşınan varlık hem hedefte hem 'eski pozisyon' listesinde — çift sayım."

    def test_transfer_orijinal_alim_tarihini_korur(self, kayitli_portfoy):
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 1.0,
        })
        yeni = [t for t in dm.load_portfolio()["transactions"]
                if t.get("transfer_in_id")]
        assert yeni[0]["date"] == "2026-03-01", \
            "Transfer yeni bir alım gibi tarihlendi — elde tutma süresi sıfırlandı."


class TestTransferAgUcreti:

    def test_ucret_varan_miktari_azaltir(self, kayitli_portfoy):
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX",
            "qty": 1.0, "fee_qty": 0.01,
        })
        hedef = _pozisyon(_metrics(), "ETHUSDT@DEX")
        assert hedef["total_qty"] == pytest.approx(0.99)

    def test_ucret_zarar_olarak_yazilir(self, kayitli_portfoy):
        """Yanan coin gerçekten kaybedilmiştir; maliyeti zarara geçmeli."""
        realize_once = dm.calculate_realized_metrics(dm.load_portfolio())
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX",
            "qty": 1.0, "fee_qty": 0.01,
        })
        realize = dm.calculate_realized_metrics(dm.load_portfolio())
        fark = realize["total_realized_pnl_usd"] - realize_once["total_realized_pnl_usd"]
        assert fark == pytest.approx(-25.0, abs=0.01)  # 0.01 × 2500

    def test_ucret_maliyet_tabanini_bozmaz(self, kayitli_portfoy):
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX",
            "qty": 1.0, "fee_qty": 0.01,
        })
        hedef = _pozisyon(_metrics(), "ETHUSDT@DEX")
        assert hedef["avg_cost"] == pytest.approx(2500.0), \
            "Ağ ücreti kalan coinlerin birim maliyetini değiştirmemeli."


class TestTransferDogrulama:

    def test_ayni_konuma_transfer_reddedilir(self, kayitli_portfoy):
        with pytest.raises(ValueError, match="aynı olamaz"):
            dm.transfer_position({
                "pos_key": "ETHUSDT@BINANCE", "to_exchange": "BINANCE", "qty": 1.0,
            })

    def test_bakiyeden_fazla_transfer_reddedilir(self, kayitli_portfoy):
        with pytest.raises(ValueError, match="Yetersiz bakiye"):
            dm.transfer_position({
                "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 5.0,
            })

    def test_sifir_miktar_reddedilir(self, kayitli_portfoy):
        with pytest.raises(ValueError, match="sıfırdan büyük"):
            dm.transfer_position({
                "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 0,
            })

    def test_negatif_ucret_reddedilir(self, kayitli_portfoy):
        with pytest.raises(ValueError, match="negatif olamaz"):
            dm.transfer_position({
                "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX",
                "qty": 1.0, "fee_qty": -0.5,
            })

    def test_miktardan_buyuk_ucret_reddedilir(self, kayitli_portfoy):
        with pytest.raises(ValueError, match="küçük olmalı"):
            dm.transfer_position({
                "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX",
                "qty": 1.0, "fee_qty": 1.0,
            })

    def test_olmayan_pozisyon_reddedilir(self, kayitli_portfoy):
        with pytest.raises(ValueError, match="aktif işlem bulunamadı"):
            dm.transfer_position({
                "pos_key": "YOKUSDT@BINANCE", "to_exchange": "DEX", "qty": 1.0,
            })

    def test_hedef_konum_bos_olamaz(self, kayitli_portfoy):
        with pytest.raises(ValueError, match="Hedef konum"):
            dm.transfer_position({
                "pos_key": "ETHUSDT@BINANCE", "to_exchange": "", "qty": 1.0,
            })


class TestTransferGeriAlma:

    def test_transfer_geri_alinabilir(self, kayitli_portfoy):
        kasa_once = _metrics()["kpis"]["total_kasa"]
        kayit = dm.transfer_position({
            "pos_key": "BTCUSDT@BINANCE", "to_exchange": "MEXC", "qty": 0.015,
        })
        dm.undo_transfer(kayit["id"])

        metrics = _metrics()
        kaynak = _pozisyon(metrics, "BTCUSDT@BINANCE")
        assert _pozisyon(metrics, "BTCUSDT@MEXC") is None
        assert kaynak["total_qty"] == pytest.approx(0.02)
        assert kaynak["avg_cost"] == pytest.approx(85000.0)
        assert metrics["kpis"]["total_kasa"] == pytest.approx(kasa_once, abs=0.01)

    def test_geri_alma_ucret_yazimini_da_siler(self, kayitli_portfoy):
        realize_once = dm.calculate_realized_metrics(dm.load_portfolio())
        kayit = dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX",
            "qty": 1.0, "fee_qty": 0.01,
        })
        dm.undo_transfer(kayit["id"])
        realize = dm.calculate_realized_metrics(dm.load_portfolio())
        assert realize["total_realized_pnl_usd"] == pytest.approx(
            realize_once["total_realized_pnl_usd"], abs=0.01)
        assert realize["write_off_count"] == realize_once["write_off_count"]

    def test_hedefte_satildiysa_geri_alma_engellenir(self, kayitli_portfoy):
        """Sessizce bozuk veri üretmektense açık hata vermek doğrudur."""
        kayit = dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 1.0,
        })
        dm.execute_target_sale("ETHUSDT@DEX", sell_price=2000.0, sell_qty=1.0)
        with pytest.raises(ValueError, match="geri alınamaz"):
            dm.undo_transfer(kayit["id"])

    def test_olmayan_transfer_geri_alinamaz(self, kayitli_portfoy):
        with pytest.raises(ValueError, match="bulunamadı"):
            dm.undo_transfer(9999)

    def test_transfer_listesi_yeniden_eskiye_siralanir(self, kayitli_portfoy):
        dm.transfer_position({"pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 0.5})
        dm.transfer_position({"pos_key": "BTCUSDT@BINANCE", "to_exchange": "MEXC", "qty": 0.005})
        kayitlar = dm.list_transfers()
        assert [k["id"] for k in kayitlar] == [2, 1]


# =====================================================================
# BÖLÜM 3 — İKİSİ BİRLİKTE / ŞEMA
# =====================================================================
class TestSemaVeBirlikteCalisma:

    def test_eski_portfoy_dosyasina_transfer_alanlari_eklenir(self, kayitli_portfoy):
        """Geriye dönük uyumluluk: mevcut 73 işlemlik dosya bozulmamalı."""
        eski = {"wallets": {"usdt_cash": 100.0}, "transactions": [], "next_tx_id": 1}
        yeni = dm._ensure_schema(eski)
        assert yeni["transfers"] == []
        assert yeni["next_transfer_id"] == 1
        assert yeni["next_tx_id"] == 1, "Mevcut alanlar korunmalı."

    def test_transfer_sonrasi_yazim_dogru_zarari_hesaplar(self, kayitli_portfoy):
        """Önce taşı, sonra öldüğünü fark et — sık gerçek senaryo."""
        dm.transfer_position({
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 1.0,
        })
        sonuc = dm.write_off_position("ETHUSDT@DEX", reason="rug")
        assert sonuc["realized_loss_usd"] == pytest.approx(2500.0), \
            "Taşınan varlığın yazımı orijinal maliyeti zarar yazmalı."

    def test_kaynagi_olmayan_pozisyonun_degeri_kpi_de_raporlanir(self, kayitli_portfoy):
        """Kullanıcı toplamının ne kadarının varsayım olduğunu görebilmeli."""
        kpis = _metrics()["kpis"]
        assert "no_source_value_usd" in kpis
        # SOLUSDT test fiyatlarında var, ama qty=0 → değer 0.
        # Fiyatı hiç olmayan bir coin ekleyelim:
        data = dm.load_portfolio()
        data["transactions"].append({
            "id": 99, "date": "2026-04-01", "coin": "OLUUSDT", "exchange": "MEXC",
            "qty": 10.0, "cost": 5.0, "status": "Aktif", "notes": "", "category": "Altcoin",
        })
        dm.save_portfolio(data)

        kpis = _metrics()["kpis"]
        assert kpis["no_source_count"] >= 1
        assert kpis["no_source_value_usd"] == pytest.approx(50.0), \
            "Kaynağı olmayan pozisyonun maliyet üzerinden değeri raporlanmalı."

    def test_yazim_kaynagi_olmayan_pozisyonu_kasadan_cikarir(self, kayitli_portfoy):
        """FAZ F1'in asıl vaadi: şişirilmiş toplam düzelir."""
        data = dm.load_portfolio()
        data["transactions"].append({
            "id": 99, "date": "2026-04-01", "coin": "OLUUSDT", "exchange": "MEXC",
            "qty": 10.0, "cost": 5.0, "status": "Aktif", "notes": "", "category": "Altcoin",
        })
        dm.save_portfolio(data)

        kasa_once = _metrics()["kpis"]["total_kasa"]
        dm.write_off_position("OLUUSDT@MEXC", reason="delist")
        kpis = _metrics()["kpis"]

        assert kpis["total_kasa"] == pytest.approx(kasa_once - 50.0, abs=0.01)
        assert kpis["no_source_value_usd"] == pytest.approx(0.0, abs=0.01)


# =====================================================================
# BÖLÜM 4 — API UÇLARI
# =====================================================================
class TestApiUclari:

    def test_yazim_ucu_calisir(self, client):
        r = client.post("/api/positions/ETHUSDT@BINANCE/write-off",
                        json={"reason": "delist", "note": "Binance'ten çıkarıldı"})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["result"]["realized_loss_usd"] == pytest.approx(2500.0)
        assert all(c["pos_key"] != "ETHUSDT@BINANCE" for c in body["consolidated_coins"])

    def test_olmayan_pozisyon_yazimi_400_doner(self, client):
        r = client.post("/api/positions/YOKUSDT@BINANCE/write-off", json={})
        assert r.status_code == 400

    def test_yazim_geri_alma_ucu_calisir(self, client):
        r = client.post("/api/positions/ETHUSDT@BINANCE/write-off", json={"reason": "rug"})
        wid = r.json()["result"]["write_off_id"]

        r2 = client.post(f"/api/write-offs/{wid}/undo")
        assert r2.status_code == 200
        assert any(c["pos_key"] == "ETHUSDT@BINANCE"
                   for c in r2.json()["consolidated_coins"])

    def test_yazim_gerekce_listesi_doner(self, client):
        r = client.get("/api/write-offs")
        assert r.status_code == 200
        anahtarlar = {x["key"] for x in r.json()["reasons"]}
        assert {"delist", "rug", "lost", "worthless", "other"} <= anahtarlar

    def test_transfer_ucu_calisir(self, client):
        r = client.post("/api/transfers", json={
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "METAMASK", "qty": 1.0,
            "note": "cüzdana çektim",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["transfer"]["to_exchange"] == "METAMASK"
        hedef = next(c for c in body["consolidated_coins"] if c["pos_key"] == "ETHUSDT@METAMASK")
        assert hedef["avg_cost"] == pytest.approx(2500.0)

    def test_gecersiz_transfer_400_doner(self, client):
        r = client.post("/api/transfers", json={
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 999.0,
        })
        assert r.status_code == 400
        assert "Yetersiz bakiye" in r.json()["detail"]

    def test_transfer_listeleme_ucu_calisir(self, client):
        client.post("/api/transfers", json={
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 1.0,
        })
        r = client.get("/api/transfers")
        assert r.status_code == 200
        assert len(r.json()["transfers"]) == 1

    def test_transfer_geri_alma_ucu_calisir(self, client):
        r = client.post("/api/transfers", json={
            "pos_key": "ETHUSDT@BINANCE", "to_exchange": "DEX", "qty": 1.0,
        })
        tid = r.json()["transfer"]["id"]

        r2 = client.delete(f"/api/transfers/{tid}")
        assert r2.status_code == 200
        assert any(c["pos_key"] == "ETHUSDT@BINANCE"
                   for c in r2.json()["consolidated_coins"])

    def test_olmayan_transfer_geri_alma_404_doner(self, client):
        r = client.delete("/api/transfers/9999")
        assert r.status_code == 404

    def test_portfoy_ucu_no_source_degerini_doner(self, client):
        r = client.get("/api/portfolio")
        assert r.status_code == 200
        assert "no_source_value_usd" in r.json()["kpis"]
