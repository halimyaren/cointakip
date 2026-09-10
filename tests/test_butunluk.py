"""
Defter bütünlük denetimi.

Buradaki her test, gerçekte yaşanmış bir hatanın genellemesini sınar. Sırf
"temiz defterde sessiz kalıyor" demek yetmez — bir denetimin değeri, hatayı
GERÇEKTEN yakalayıp yakalamadığıyla ölçülür. Bu yüzden her kontrol için
hatalı bir defter kurulup bulgunun çıktığı doğrulanır.

En kritik güvence en sonda: **denetim hiçbir şey yazmaz.** Otomatik düzelten
bir denetim, sessiz bir hatayı sessiz bir değişiklikle takas ederdi; 9 Eylül
onarımında hangi kaydın taşınacağına ancak bağların haritası çıkarıldıktan
sonra karar verilebilmişti.
"""

import hashlib
import os

import pytest

import butunluk
import data_manager as dm


def _temiz_defter():
    return {
        "wallets": {"usdt_cash": 1000.0,
                    "exchange_cash": {"BINANCE": 600.0, "MEXC": 400.0},
                    "futures_balance": 0.0, "margin_balance": 0.0},
        "settings": {"currency": "USD"},
        "transactions": [
            {"id": 1, "date": "2026-01-01", "coin": "BTCUSDT",
             "exchange": "BINANCE", "qty": 0.5, "cost": 90000.0,
             "status": "Aktif", "category": "Majör / L1"},
            {"id": 2, "date": "2026-02-01", "coin": "ETHUSDT",
             "exchange": "MEXC", "qty": 2.0, "cost": 2000.0,
             "status": "Kapandı / İzleme", "exit_date": "2026-03-01",
             "exit_price": 2500.0, "category": "Majör / L1"},
        ],
        "next_tx_id": 3,
        "targets": {}, "transfers": [], "rebuilds": [], "hedges": [],
    }


def _kodlar(rapor):
    return {b["code"] for b in rapor["findings"]}


def _bulgu(rapor, kod):
    return next(b for b in rapor["findings"] if b["code"] == kod)


# =====================================================================
# Temiz defter
# =====================================================================
class TestTemizDefter:

    def test_temiz_defterde_bulgu_yok(self):
        rapor = butunluk.denetle(_temiz_defter())
        assert rapor["ok"] is True
        assert rapor["findings"] == []
        assert rapor["error_count"] == 0

    def test_rapor_kac_kontrol_calistigini_soyler(self):
        """"Bulgu yok" ile "hiç bakılmadı" ayırt edilebilmeli."""
        rapor = butunluk.denetle(_temiz_defter())
        assert rapor["checks_run"] == len(butunluk.DENETIMLER)
        assert rapor["transaction_count"] == 2


# =====================================================================
# İşlem numaraları — 9 Eylül 2026 çakışması
# =====================================================================
class TestNumaraDenetimi:

    def test_cakisan_numara_yakalanir(self):
        d = _temiz_defter()
        d["transactions"][1]["id"] = 1
        rapor = butunluk.denetle(d)
        assert "tx_id_cakismasi" in _kodlar(rapor)
        assert rapor["ok"] is False

    def test_numarasiz_kayit_yakalanir(self):
        d = _temiz_defter()
        d["transactions"][0].pop("id")
        assert "tx_id_yok" in _kodlar(butunluk.denetle(d))

    def test_geride_kalmis_sayac_cakisma_OLMADAN_yakalanir(self):
        """Asıl değer burada: çakışma henüz oluşmadan uyarır. 9 Eylül'de
        sayaç dokuz gün geride kaldıktan sonra çakışma üretmişti."""
        d = _temiz_defter()
        d["next_tx_id"] = 2          # en büyük numara 2, olması gereken 3
        rapor = butunluk.denetle(d)
        assert "tx_id_sayaci_geride" in _kodlar(rapor)
        assert "tx_id_cakismasi" not in _kodlar(rapor)

    def test_ileri_sayac_sorun_degil(self):
        d = _temiz_defter()
        d["next_tx_id"] = 500
        assert "tx_id_sayaci_geride" not in _kodlar(butunluk.denetle(d))


# =====================================================================
# Nakit
# =====================================================================
class TestNakitDenetimi:

    def test_toplam_tutmuyorsa_yakalanir(self):
        d = _temiz_defter()
        d["wallets"]["usdt_cash"] = 1013.76      # alımda düşülmeyen nakit
        rapor = butunluk.denetle(d)
        assert "nakit_toplami_tutmuyor" in _kodlar(rapor)
        assert "13.7" in _bulgu(rapor, "nakit_toplami_tutmuyor")["items"][0]

    def test_kurus_farki_gurultu_uretmez(self):
        """Elle giriş yuvarlaması her açılışta uyarı üretmemeli."""
        d = _temiz_defter()
        d["wallets"]["usdt_cash"] = 1000.004
        assert "nakit_toplami_tutmuyor" not in _kodlar(butunluk.denetle(d))

    def test_negatif_nakit_yakalanir(self):
        d = _temiz_defter()
        d["wallets"]["exchange_cash"]["MEXC"] = -5.0
        d["wallets"]["usdt_cash"] = 595.0
        assert "negatif_nakit" in _kodlar(butunluk.denetle(d))


# =====================================================================
# Pozisyon alanları
# =====================================================================
class TestPozisyonDenetimi:

    def test_bos_zorunlu_alan_yakalanir(self):
        d = _temiz_defter()
        d["transactions"][0]["coin"] = ""
        assert "eksik_alan" in _kodlar(butunluk.denetle(d))

    def test_negatif_miktarli_acik_lot_yakalanir(self):
        d = _temiz_defter()
        d["transactions"][0]["qty"] = -1.0
        assert "negatif_miktar" in _kodlar(butunluk.denetle(d))

    def test_tanimsiz_durum_uyari_verir(self):
        d = _temiz_defter()
        d["transactions"][0]["status"] = "Yarim"
        rapor = butunluk.denetle(d)
        assert "bilinmeyen_durum" in _kodlar(rapor)
        # Uyarı öneriyi durdurmaz; defter yine de kullanılabilir.
        assert _bulgu(rapor, "bilinmeyen_durum")["severity"] == butunluk.UYARI

    def test_kapali_lotta_cikis_tarihi_aranir(self):
        d = _temiz_defter()
        d["transactions"][1].pop("exit_date")
        assert "kapali_lot_eksik" in _kodlar(butunluk.denetle(d))


# =====================================================================
# Bağlar — 9 Eylül onarımında haritası çıkarılan bağlar
# =====================================================================
class TestBagDenetimi:

    def test_transferin_tukettigi_olmayan_lot_yakalanir(self):
        d = _temiz_defter()
        d["transfers"] = [{"id": 1, "consumed": [{"tx_id": 999, "qty": 1.0}]}]
        rapor = butunluk.denetle(d)
        assert "kopuk_bag" in _kodlar(rapor)
        assert "999" in _bulgu(rapor, "kopuk_bag")["items"][0]

    def test_mutabakatin_olmayan_kaydi_yakalanir(self):
        d = _temiz_defter()
        d["rebuilds"] = [{"id": 1, "closed_tx_ids": [1], "created_tx_ids": [42]}]
        assert "kopuk_bag" in _kodlar(butunluk.denetle(d))

    def test_mutabakat_kz_kaydi_da_denetlenir(self):
        d = _temiz_defter()
        d["rebuilds"] = [{"id": 1, "realized": {"tx_id": 77, "booked": True}}]
        assert "kopuk_bag" in _kodlar(butunluk.denetle(d))

    def test_saglam_baglar_bulgu_uretmez(self):
        d = _temiz_defter()
        d["transfers"] = [{"id": 1, "consumed": [{"tx_id": 1, "qty": 0.1}]}]
        d["rebuilds"] = [{"id": 1, "closed_tx_ids": [2], "created_tx_ids": [1]}]
        assert "kopuk_bag" not in _kodlar(butunluk.denetle(d))


class TestArsivBagi:

    def test_olmayan_kayda_bakan_islenmis_olay_yakalanir(self, monkeypatch):
        """Bağ koparsa olay 'işlendi' görünür ama defterde karşılığı olmaz;
        aynı işlem bir daha yakalanmaz ve eksik kalır."""
        import archive
        monkeypatch.setattr(archive, "applied_events_with_tx", lambda: [
            {"event_uid": "BINANCE:trade:ARBUSDT:1", "kind": "TRADE",
             "symbol": "ARBUSDT", "applied_tx_id": 999}])
        assert "arsiv_bagi_kopuk" in _kodlar(butunluk.denetle(_temiz_defter()))

    def test_saglam_bag_bulgu_uretmez(self, monkeypatch):
        import archive
        monkeypatch.setattr(archive, "applied_events_with_tx", lambda: [
            {"event_uid": "x", "kind": "TRADE", "symbol": "BTCUSDT",
             "applied_tx_id": 1}])
        assert "arsiv_bagi_kopuk" not in _kodlar(butunluk.denetle(_temiz_defter()))

    def test_arsiv_okunamazsa_denetim_durmaz(self, monkeypatch):
        """Arşive ulaşılamaması, defterin denetlenememesi anlamına gelmemeli
        — ama sessizce 'temiz' de denmemeli."""
        import archive

        def patla():
            raise RuntimeError("arsiv kilitli")

        monkeypatch.setattr(archive, "applied_events_with_tx", patla)
        rapor = butunluk.denetle(_temiz_defter())
        assert "arsiv_okunamadi" in _kodlar(rapor)
        assert rapor["ok"] is True          # uyarı, hata değil


# =====================================================================
# Dayanıklılık
# =====================================================================
class TestDayaniklilik:

    def test_bir_denetimin_dusmesi_digerlerini_iptal_etmez(self, monkeypatch):
        def patlayan(data, ctx):
            raise RuntimeError("beklenmedik")

        monkeypatch.setattr(butunluk, "DENETIMLER",
                            (patlayan, butunluk._nakit))
        d = _temiz_defter()
        d["wallets"]["usdt_cash"] = 5000.0
        rapor = butunluk.denetle(d)
        assert "denetim_dustu" in _kodlar(rapor)
        assert "nakit_toplami_tutmuyor" in _kodlar(rapor)

    def test_bos_defter_patlatmaz(self):
        rapor = butunluk.denetle({"transactions": [], "wallets": {}})
        assert rapor["ok"] is True

    def test_ornek_listesi_kirpilir(self):
        """148 kayıtlık bir defterde tüm örnekleri taşımak raporu okunmaz
        hâle getirir; hiç göstermemek 'nerede?' sorusunu cevapsız bırakır."""
        d = _temiz_defter()
        d["transactions"] = [
            {"id": i, "date": "2026-01-01", "coin": "", "exchange": "BINANCE",
             "qty": 1.0, "cost": 1.0, "status": "Aktif"}
            for i in range(1, 60)]
        d["next_tx_id"] = 60
        b = _bulgu(butunluk.denetle(d), "eksik_alan")
        assert b["count"] == 59
        assert len(b["items"]) == butunluk.ORNEK_TAVANI
        assert b["truncated"] is True


# =====================================================================
# EN KRİTİK GÜVENCE: DENETİM HİÇBİR ŞEY YAZMAZ
# =====================================================================
class TestSaltOkunur:

    def _ozet(self, yol):
        with open(yol, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def test_denetim_defteri_degistirmez(self, kayitli_portfoy):
        once = self._ozet(dm.DATA_FILE)
        butunluk.denetle()
        assert self._ozet(dm.DATA_FILE) == once

    def test_hatali_defterde_bile_yazmaz(self, kayitli_portfoy):
        """Hata bulunca 'düzelteyim' diye yazmaya kalkmamalı: hangi kaydın
        değişeceği ona kimin işaret ettiğine bağlı ve o karar kullanıcının."""
        d = dm.load_portfolio()
        d["transactions"][1]["id"] = d["transactions"][0]["id"]
        d["wallets"]["usdt_cash"] = 99999.0
        dm.save_portfolio(d)

        once = self._ozet(dm.DATA_FILE)
        rapor = butunluk.denetle()
        assert rapor["ok"] is False
        assert self._ozet(dm.DATA_FILE) == once

    def test_verilen_sozlugu_de_degistirmez(self):
        d = _temiz_defter()
        d["transactions"][0]["id"] = 2      # çakışma kur
        import copy
        kopya = copy.deepcopy(d)
        butunluk.denetle(d)
        assert d == kopya

    def test_modulde_kaydetme_cagrisi_yok(self):
        """Sözün kaynak seviyesinde denetimi: ileride biri 'küçük bir
        düzeltme' eklemek isterse bu test onu durdurur."""
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(kok, "app", "butunluk.py"), encoding="utf-8") as f:
            kaynak = f.read()
        for yasak in ("save_portfolio", "save_settings", "open(",
                      "os.replace", "json.dump"):
            assert yasak not in kaynak, f"butunluk.py içinde '{yasak}' var"

    def test_rapor_salt_okunur_oldugunu_soyler(self):
        assert butunluk.denetle(_temiz_defter())["read_only"] is True


class TestUc:

    def test_uc_raporu_dondurur(self, client):
        yanit = client.get("/api/integrity")
        assert yanit.status_code == 200
        veri = yanit.json()
        assert veri["read_only"] is True
        assert "findings" in veri and "ok" in veri

    def test_uc_defteri_degistirmez(self, client):
        with open(dm.DATA_FILE, "rb") as f:
            once = hashlib.sha256(f.read()).hexdigest()
        client.get("/api/integrity")
        with open(dm.DATA_FILE, "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest() == once
