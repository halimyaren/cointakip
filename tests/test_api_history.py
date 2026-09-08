"""
FAZ F7c — Borsa geçmişinin API'den doldurulması.

Buradaki testlerin koruduğu asıl şey MÜKERRER SAYMAMA. Aynı işlem hem
indirilen dosyada hem API'de bulunur; ikisini birden almak her işlemi iki kez
saydırır ve mutabakatın bütün değeri doğru sayabilmesinde olduğu için bu
ölümcül bir hatadır. "Dosya esastır, API boşluğu doldurur" kuralı bu yüzden
tek tek sınanır.

İkinci koruma: API'den üretilen satırlar, aynı işlemin dosyadan üretilen
satırlarıyla AYNI olmalı. Ayrışırlarsa aynı işlem hangi kaynaktan geldiğine
göre farklı bakiye üretir.
"""

import pytest

import api_history
import archive
import reconcile
import trade_sync


BINANCE_PROFIL = {
    "location": "BINANCE",
    "name": "Binance",
    "family": "binance",
    "base_url": "https://api.binance.com",
    "account_path": "/api/v3/account",
    "enabled": True,
}


def _dosya_olayi(borsa, zaman, varlik="ARB", qty=1.0):
    return reconcile._olay(borsa, zaman, "TRADE", varlik, qty,
                           source="Binance-Spot-Trade-History.csv")


def _api_olayi(borsa, zaman, varlik="ARB", qty=1.0):
    return reconcile._olay(borsa, zaman, "TRADE", varlik, qty,
                           source=api_history._kaynak_adi(borsa))


# =====================================================================
# Sınır: dosya nereye kadar geliyor
# =====================================================================
class TestDosyaSiniri:

    def test_borsa_basina_en_son_zaman_bulunur(self):
        olaylar = [
            _dosya_olayi("BINANCE", "2026-08-27T10:00:00"),
            _dosya_olayi("BINANCE", "2026-08-20T10:00:00"),
            _dosya_olayi("MEXC", "2026-08-26T09:00:00"),
        ]
        sinir = api_history.dosya_sinirlari(olaylar)
        assert sinir["BINANCE"] == "2026-08-27T10:00:00"
        assert sinir["MEXC"] == "2026-08-26T09:00:00"

    def test_zamansiz_satir_siniri_bozmaz(self):
        olaylar = [_dosya_olayi("BINANCE", ""),
                   _dosya_olayi("BINANCE", "2026-08-27T10:00:00")]
        assert api_history.dosya_sinirlari(olaylar)["BINANCE"] == \
            "2026-08-27T10:00:00"

    def test_dosya_yoksa_sinir_yok(self):
        assert api_history.dosya_sinirlari([]) == {}


class TestSinirinOtesi:

    def test_sinirdan_onceki_api_satirlari_atilir(self):
        sinir = {"BINANCE": "2026-08-27T10:00:00"}
        api = [_api_olayi("BINANCE", "2026-08-26T23:59:59"),
               _api_olayi("BINANCE", "2026-08-28T00:00:01")]
        kalan = api_history.sinirin_otesi(api, sinir)
        assert [o["time"] for o in kalan] == ["2026-08-28T00:00:01"]

    def test_sinirla_ayni_an_atilir(self):
        """Aynı saniyedeki satır büyük olasılıkla dosyanın son satırının ta
        kendisidir; iki kez saymaktansa bir kez saymak doğrudur."""
        sinir = {"BINANCE": "2026-08-27T10:00:00"}
        api = [_api_olayi("BINANCE", "2026-08-27T10:00:00")]
        assert api_history.sinirin_otesi(api, sinir) == []

    def test_dosyasiz_borsanin_tum_gecmisi_alinir(self):
        """MEXC dosyası varken BINANCE dosyası yoksa, BINANCE'in tamamı
        gelir — sınır borsa BAZINDA uygulanır."""
        sinir = {"MEXC": "2026-08-26T09:00:00"}
        api = [_api_olayi("BINANCE", "2024-01-01T00:00:00"),
               _api_olayi("MEXC", "2024-01-01T00:00:00")]
        kalan = api_history.sinirin_otesi(api, sinir)
        assert [o["exchange"] for o in kalan] == ["BINANCE"]

    def test_hic_sinir_yoksa_hepsi_kalir(self):
        api = [_api_olayi("BINANCE", "2020-01-01T00:00:00")]
        assert len(api_history.sinirin_otesi(api, {})) == 1


# =====================================================================
# Borsa olayı → mutabakat olayı
# =====================================================================
class TestOlayCevrimi:

    def _islem(self, **ustler):
        ham = {"symbol": "ARBUSDT", "id": 1, "isBuyer": True, "qty": "100",
               "price": "0.5", "quoteQty": "50", "commission": "0.05",
               "commissionAsset": "BNB", "time": 1757000000000}
        ham.update(ustler)
        return trade_sync.normalize_trade("BINANCE", ham)

    def test_alim_pozitif_miktar_uretir(self):
        satirlar = api_history.defter_olaylari(self._islem())
        ana = satirlar[0]
        assert ana["kind"] == "TRADE"
        assert ana["asset"] == "ARB"
        assert ana["qty"] == pytest.approx(100.0)
        assert ana["quote_qty"] == pytest.approx(-50.0)

    def test_stabil_kotasyonda_dolar_bilinir(self):
        ana = api_history.defter_olaylari(self._islem())[0]
        assert ana["usd_known"] is True
        assert ana["usd_value"] == pytest.approx(50.0)

    def test_stabil_olmayan_kotasyonda_dolar_bilinmez(self):
        """Uydurmak yerine "bilmiyorum" demek doğrudur; `_birim_maliyet`
        bilinmeyen maliyeti sahte bir sayıyla doldurmaz."""
        ana = api_history.defter_olaylari(
            self._islem(symbol="ARBBTC", quoteQty="0.001"))[0]
        assert ana["usd_known"] is False
        assert ana["usd_value"] == 0.0

    def test_satis_negatif_miktar_uretir(self):
        ana = api_history.defter_olaylari(self._islem(isBuyer=False))[0]
        assert ana["qty"] == pytest.approx(-100.0)
        assert ana["quote_qty"] == pytest.approx(50.0)

    def test_baska_coinden_komisyon_ayri_satir_olur(self):
        """BNB ile ödenen komisyon BNB bakiyesini azaltır. Yazılmazsa BNB
        olduğundan yüksek yeniden kurulur."""
        satirlar = api_history.defter_olaylari(self._islem())
        komisyon = [s for s in satirlar if s["kind"] == "FEE"]
        assert len(komisyon) == 1
        assert komisyon[0]["asset"] == "BNB"
        assert komisyon[0]["qty"] == pytest.approx(-0.05)

    def test_kendi_varligindan_komisyon_ikinci_kez_dusulmez(self):
        """`normalize_trade` miktarı zaten NET yazdı; ayrıca bir FEE satırı
        eklemek çift sayım olurdu."""
        satirlar = api_history.defter_olaylari(
            self._islem(commissionAsset="ARB", commission="0.1"))
        assert [s["kind"] for s in satirlar] == ["TRADE"]
        assert satirlar[0]["qty"] == pytest.approx(99.9)

    def test_dosya_ve_api_ayni_islemde_ayni_miktari_verir(self):
        """İki yolun ayrışması, aynı işlemin hangi kaynaktan geldiğine göre
        farklı bakiye üretmesi demekti."""
        api_satir = api_history.defter_olaylari(
            self._islem(commissionAsset="ARB", commission="0.1"))[0]
        # Dosya tarafının aynı işlem için ürettiği net miktar:
        # Executed 100 ARB, komisyon 0.1 ARB → 99.9
        assert api_satir["qty"] == pytest.approx(99.9)


class TestTozCevrimi:

    def _toz(self, **ustler):
        satir = {"from_asset": "MAV", "target_asset": "BNB", "amount": "12",
                 "transfered_amount": "0.02", "service_charge_amount": "0.001",
                 "operate_time": 1757000000000, "trans_id": 7}
        satir.update(ustler)
        return trade_sync.normalize_dust("BINANCE", satir)

    def test_iki_bacak_uretilir(self):
        satirlar = api_history.defter_olaylari(self._toz())
        assert [s["asset"] for s in satirlar] == ["MAV", "BNB"]

    def test_kaynak_varlik_cikar(self):
        cikan = api_history.defter_olaylari(self._toz())[0]
        assert cikan["qty"] == pytest.approx(-12.0)

    def test_hedef_varlik_komisyon_dusulmus_girer(self):
        """Gelen bacak yazılmazsa BNB bakiyesi olduğundan düşük kurulur."""
        gelen = api_history.defter_olaylari(self._toz())[1]
        assert gelen["qty"] == pytest.approx(0.019)

    def test_hedef_stabil_degilse_maliyet_bilinmez(self):
        gelen = api_history.defter_olaylari(self._toz())[1]
        assert gelen["usd_known"] is False

    def test_hedef_usdt_ise_dolar_bilinir(self):
        satirlar = api_history.defter_olaylari(
            self._toz(target_asset="USDT", transfered_amount="17.76",
                      service_charge_amount="0.1"))
        assert satirlar[0]["usd_known"] is True
        assert satirlar[0]["usd_value"] == pytest.approx(17.76)


class TestHesapAkislariCevrimi:

    def test_earn_bedelsiz_giris_olur(self):
        olay = trade_sync.normalize_earn("BINANCE", {
            "asset": "APT", "amount": "0.00040177", "time": 1757000000000})
        satir = api_history.defter_olaylari(olay)[0]
        assert satir["kind"] == "REWARD"
        assert satir["zero_cost"] is True
        assert satir["qty"] == pytest.approx(0.00040177)

    def test_yatirma_pozitif(self):
        olay = trade_sync.normalize_deposit("BINANCE", {
            "coin": "USDT", "amount": "500", "status": 1,
            "insertTime": 1757000000000, "id": "d1"})
        satir = api_history.defter_olaylari(olay)[0]
        assert satir["kind"] == "DEPOSIT"
        assert satir["qty"] == pytest.approx(500.0)

    def test_cekmede_ag_komisyonu_da_bakiyeden_cikar(self):
        """Yalnızca `amount` yazılırsa komisyon kadarı her seferinde
        açıklanamayan bir fark olarak kalırdı."""
        olay = trade_sync.normalize_withdraw("BINANCE", {
            "coin": "USDT", "amount": "100", "transactionFee": "1",
            "status": 6, "applyTime": "2026-09-04 12:00:00", "id": "w1"})
        satir = api_history.defter_olaylari(olay)[0]
        assert satir["kind"] == "WITHDRAW"
        assert satir["qty"] == pytest.approx(-101.0)


# =====================================================================
# Toplama
# =====================================================================
class TestToplama:

    def test_kasa_kilitliyken_aga_cikilmaz(self, monkeypatch):
        """Kilitli kasada imzalı istek atılamaz; sessizce boş dönmek yerine
        sebebi söylenir."""
        import keyvault
        monkeypatch.setattr(keyvault, "is_unlocked", lambda: False)
        olaylar, kaynaklar, uyarilar = api_history.topla({"transactions": []})
        assert olaylar == [] and kaynaklar == []
        assert any("kilitli" in u.lower() for u in uyarilar)

    def test_sembol_sayfa_sayfa_okunur(self, monkeypatch):
        """1000'lik sayfa dolu geldiyse devam edilir; eksik gelirse durulur."""
        import exchanges

        cagrilar = []

        def sahte(profil, symbol, from_id=None, **k):
            cagrilar.append(from_id)
            if from_id == 0:
                return [{"symbol": "ARBUSDT", "id": i, "isBuyer": True,
                         "qty": "1", "price": "1", "quoteQty": "1",
                         "commission": "0", "commissionAsset": "USDT",
                         "time": 1757000000000}
                        for i in range(1, exchanges.MY_TRADES_LIMIT + 1)]
            return [{"symbol": "ARBUSDT", "id": 5000, "isBuyer": True,
                     "qty": "1", "price": "1", "quoteQty": "1",
                     "commission": "0", "commissionAsset": "USDT",
                     "time": 1757000000000}]

        monkeypatch.setattr(exchanges, "fetch_my_trades", sahte)
        monkeypatch.setattr(api_history, "_nefes", lambda agirlik: None)
        olaylar = api_history._sembol_islemleri(
            BINANCE_PROFIL, "BINANCE", "ARBUSDT")
        assert cagrilar == [0, exchanges.MY_TRADES_LIMIT + 1]
        assert len(olaylar) == exchanges.MY_TRADES_LIMIT + 1

    def test_sayfa_tavani_sonsuz_donguyu_keser(self, monkeypatch):
        """Uç beklenmedik bir yanıt verirse döngü sonsuza kadar dönmemeli."""
        import exchanges

        def hep_dolu(profil, symbol, from_id=None, **k):
            return [{"symbol": "ARBUSDT", "id": (from_id or 0) + i,
                     "isBuyer": True, "qty": "1", "price": "1",
                     "quoteQty": "1", "commission": "0",
                     "commissionAsset": "USDT", "time": 1757000000000}
                    for i in range(1, exchanges.MY_TRADES_LIMIT + 1)]

        monkeypatch.setattr(exchanges, "fetch_my_trades", hep_dolu)
        monkeypatch.setattr(api_history, "_nefes", lambda agirlik: None)
        monkeypatch.setattr(api_history, "SAYFA_TAVANI", 3)
        olaylar = api_history._sembol_islemleri(
            BINANCE_PROFIL, "BINANCE", "ARBUSDT")
        assert len(olaylar) == 3 * exchanges.MY_TRADES_LIMIT

    def test_desteklenmeyen_akis_atlanir(self, monkeypatch):
        """MEXC'te Earn ucu yok; olmayan bir uca istek atmak hata üretirdi."""
        import exchanges
        monkeypatch.setattr(exchanges, "supports", lambda p, alan: False)
        olaylar, uyarilar = api_history._borsa_akislari(BINANCE_PROFIL,
                                                        "BINANCE")
        assert olaylar == [] and uyarilar == []

    def test_bir_pencerenin_dusmesi_akisi_iptal_etmez(self, monkeypatch):
        """Bir pencere hata verdiğinde diğerleri yine de okunmalı."""
        monkeypatch.setattr(api_history, "_nefes", lambda agirlik: None)
        cagri = {"n": 0}

        def cek(profil, baslangic, bitis):
            cagri["n"] += 1
            if cagri["n"] == 1:
                raise RuntimeError("HTTP 418")
            return [{"asset": "APT", "amount": "1", "time": 1757000000000}]

        olaylar, uyarilar = api_history._pencereli_akis(
            BINANCE_PROFIL, "BINANCE", cek, trade_sync.normalize_earn,
            1000, 3, "Earn", 150)
        assert len(olaylar) == 2
        assert len(uyarilar) == 1 and "418" in uyarilar[0]

    def test_pencereler_geriye_dogru_ve_ustuste_binmez(self):
        pencereler = list(api_history._pencereler(1000, 3))
        assert len(pencereler) == 3
        for once, sonra in zip(pencereler, pencereler[1:]):
            assert sonra[1] < once[0]      # bitiş, öncekinin başından eski


# =====================================================================
# FAZ F7d — canlı hesapta bulunan iki hata
# =====================================================================
class TestDerinlikSinirdanGelir:
    """Doldurma, dosyaların zaten kapsadığı dönem için istek atmamalı."""

    def test_dosya_yeniyse_az_pencere_gezilir(self):
        import datetime as dt
        dun = (dt.datetime.now() - dt.timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%S")
        assert api_history._geriye_gun(dun) <= api_history.GUVENLIK_PAYI_GUN + 1

    def test_dosya_yoksa_varsayilan_derinlige_dusulur(self):
        assert api_history._geriye_gun(None) == api_history.VARSAYILAN_GERIYE_GUN
        assert api_history._geriye_gun("") == api_history.VARSAYILAN_GERIYE_GUN

    def test_bozuk_tarih_varsayilana_duser(self):
        """Bozuk bir sınır yüzünden binlerce istek atılmamalı."""
        assert api_history._geriye_gun("olmayan-tarih") == \
            api_history.VARSAYILAN_GERIYE_GUN

    def test_emniyet_payi_kadar_ustuste_binilir(self):
        """Sınırın hemen ötesindeki bir işlemi kaçırmaktansa üst üste binmek
        yeğdir; çakışan satırlar zaten sınır süzgecinde atılıyor."""
        import datetime as dt
        bugun = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        assert api_history._geriye_gun(bugun) >= api_history.GUVENLIK_PAYI_GUN

    def test_pencere_adedi_yukari_yuvarlanir(self):
        """12 günü 7'şer günlük pencerelerle kapatmak 2 pencere eder; aşağı
        yuvarlamak son 5 günü sessizce dışarıda bırakırdı."""
        assert api_history._pencere_adedi(12, 7) == 2
        assert api_history._pencere_adedi(14, 7) == 2
        assert api_history._pencere_adedi(1, 90) == 1

    def test_pencere_adedinin_tavani_var(self):
        assert api_history._pencere_adedi(100000, 1) == api_history.PENCERE_TAVANI

    def test_dar_pencereli_borsada_daha_cok_cagri_gerekir(self):
        """MEXC 7, Binance 90 günlük pencere kabul ediyor: aynı derinlik
        MEXC'te daha çok çağrı demektir."""
        assert api_history._pencere_adedi(90, 7) > api_history._pencere_adedi(90, 90)


# =====================================================================
# Arşive yazma ve okuma
# =====================================================================
class TestArsiv:

    def test_yazilan_gecmis_geri_okunur(self):
        olaylar = [_api_olayi("BINANCE", "2026-09-01T10:00:00")]
        assert archive.save_api_history("BINANCE", olaylar) == 1
        geri = archive.load_api_history()
        assert len(geri) == 1
        assert geri[0]["asset"] == "ARB"
        assert geri[0]["time"] == "2026-09-01T10:00:00"

    def test_yeniden_doldurma_eskisini_siler(self):
        """Uç kendi penceresi için tek doğrudur; eski okumayla birleştirmek
        mükerrer satır üretirdi."""
        archive.save_api_history("BINANCE", [
            _api_olayi("BINANCE", "2026-09-01T10:00:00"),
            _api_olayi("BINANCE", "2026-09-02T10:00:00")])
        archive.save_api_history("BINANCE", [
            _api_olayi("BINANCE", "2026-09-03T10:00:00")])
        geri = archive.load_api_history()
        assert [o["time"] for o in geri] == ["2026-09-03T10:00:00"]

    def test_bir_borsanin_doldurulmasi_digerini_silmez(self):
        archive.save_api_history("BINANCE", [_api_olayi("BINANCE", "2026-09-01T10:00:00")])
        archive.save_api_history("MEXC", [_api_olayi("MEXC", "2026-09-01T10:00:00")])
        archive.save_api_history("BINANCE", [_api_olayi("BINANCE", "2026-09-05T10:00:00")])
        assert {o["exchange"] for o in archive.load_api_history()} == \
            {"BINANCE", "MEXC"}

    def test_arsiv_yokken_okuma_patlamaz(self):
        assert archive.load_api_history() == []
        assert archive.api_history_status() == []

    def test_durum_ozeti_aralik_verir(self):
        archive.save_api_history("BINANCE", [
            _api_olayi("BINANCE", "2026-09-01T10:00:00"),
            _api_olayi("BINANCE", "2026-09-05T10:00:00")])
        durum = archive.api_history_status()
        assert len(durum) == 1
        assert durum[0]["rows"] == 2
        assert durum[0]["first"] == "2026-09-01T10:00:00"
        assert durum[0]["last"] == "2026-09-05T10:00:00"


# =====================================================================
# Mutabakatla birleşme
# =====================================================================
class TestMutabakatlaBirlesme:

    def test_api_kapaliyken_arsiv_okunmaz(self, tmp_path):
        archive.save_api_history("BINANCE", [_api_olayi("BINANCE", "2026-09-05T10:00:00")])
        olaylar, kaynaklar, _ = reconcile.load_all_events(str(tmp_path))
        assert olaylar == []
        assert kaynaklar == []

    def test_dosya_yokken_api_gecmisinin_tamami_gelir(self, tmp_path):
        archive.save_api_history("BINANCE", [
            _api_olayi("BINANCE", "2024-01-01T10:00:00"),
            _api_olayi("BINANCE", "2026-09-05T10:00:00")])
        olaylar, kaynaklar, _ = reconcile.load_all_events(str(tmp_path), api=True)
        assert len(olaylar) == 2
        assert kaynaklar[0]["kind"] == "api"
        assert kaynaklar[0]["rows"] == 2

    def test_dosyanin_kapsadigi_donem_apiden_alinmaz(self):
        """Mükerrer sayma bu testin engellediği tek şey."""
        dosya_olaylari = [_dosya_olayi("BINANCE", "2026-08-27T10:00:00")]
        archive.save_api_history("BINANCE", [
            _api_olayi("BINANCE", "2026-08-20T10:00:00"),   # dosyanın içinde
            _api_olayi("BINANCE", "2026-09-05T10:00:00"),   # dosyadan sonra
        ])
        olaylar, kaynaklar, uyarilar = reconcile._api_ekle(
            list(dosya_olaylari), [], [])
        assert [o["time"] for o in olaylar] == [
            "2026-08-27T10:00:00", "2026-09-05T10:00:00"]
        assert kaynaklar[0]["after_files"] == "2026-08-27T10:00:00"

    def test_kapsam_penceresi_apiyle_genisler(self, tmp_path):
        """Kapsam raporu "uyuşmuyor" ile "dosya o kadar geriye gitmiyor"u
        ayırt edebilsin diye API'nin getirdiği dönem de pencereye girmeli."""
        archive.save_api_history("BINANCE", [
            _api_olayi("BINANCE", "2026-09-05T10:00:00")])
        olaylar, _, _ = reconcile.load_all_events(str(tmp_path), api=True)
        pencere = reconcile.coverage_windows(olaylar)
        assert pencere["BINANCE"]["last"] == "2026-09-05"

    def test_bos_arsiv_davranisi_degistirmez(self, tmp_path):
        with_api = reconcile.load_all_events(str(tmp_path), api=True)
        without = reconcile.load_all_events(str(tmp_path), api=False)
        assert with_api == without


# =====================================================================
# Uçlar
# =====================================================================
class TestUclar:

    def test_durum_ucu_aga_cikmaz(self, client):
        """Rapor ekranı her açılışta yüzlerce imzalı istek atmamalı."""
        resp = client.get("/api/reconcile/api-history")
        assert resp.status_code == 200
        assert resp.json()["filled"] == []

    def test_doldurma_kilitli_kasada_reddedilir(self, client, monkeypatch):
        import keyvault
        monkeypatch.setattr(keyvault, "is_unlocked", lambda: False)
        resp = client.post("/api/reconcile/api-history")
        assert resp.status_code == 400
        assert "kasa" in resp.json()["detail"].lower()

    def test_doldurma_sonucu_arsive_yazilir(self, client, monkeypatch):
        import keyvault

        monkeypatch.setattr(keyvault, "is_unlocked", lambda: True)
        # `main` modülü `api_history`i çağrı anında import ediyor; modülün
        # kendisini yamamak bu yüzden yeterli.
        monkeypatch.setattr(
            api_history, "topla",
            lambda defter, profiller=None, sinirlar=None: (
                [_api_olayi("BINANCE", "2026-09-05T10:00:00")],
                [{"name": "Binance API", "exchange": "BINANCE", "kind": "api",
                  "rows": 1}],
                []))

        resp = client.post("/api/reconcile/api-history")
        assert resp.status_code == 200
        veri = resp.json()
        assert veri["events"] == 1
        assert veri["filled"][0]["exchange"] == "BINANCE"
        assert len(archive.load_api_history()) == 1

    def test_mutabakat_ucu_doldurulmus_gecmisi_katar(self, client):
        archive.save_api_history("BINANCE", [
            _api_olayi("BINANCE", "2026-09-05T10:00:00")])
        rapor = client.get("/api/reconcile").json()
        assert rapor["event_count"] >= 1
        assert "BINANCE" in rapor["coverage"]


# =====================================================================
# Arayüz bağlantısı
# =====================================================================
class TestArayuz:

    def _oku(self, ad):
        import os
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(kok, "app", "static", ad), encoding="utf-8") as f:
            return f.read()

    def test_doldurma_dugmesi_ekranda(self):
        html = self._oku("index.html")
        assert "fillApiHistory()" in html
        assert "Geçmişi Doldur" in html

    def test_sekme_acilinca_durum_okunur(self):
        """Kullanıcı ekranı açtığında daha önce doldurulup doldurulmadığını
        görmeli; aksi hâlde boş bir tablo neden boş, anlaşılmaz."""
        html = self._oku("index.html")
        assert "fetchApiHistoryStatus()" in html

    def test_islevler_app_js_icinde_tanimli(self):
        js = self._oku("app.js")
        for ad in ("fillApiHistory", "fetchApiHistoryStatus",
                   "apiHistoryBusy", "apiHistoryFilled", "apiHistoryWarnings"):
            assert ad in js, f"{ad} app.js içinde yok"

    def test_tarayici_diyalogu_kullanilmaz(self):
        """Projede uygulama içi onay penceresi var; tarayıcınınki kullanılmaz."""
        js = self._oku("app.js")
        nerede = js.index("async fillApiHistory()")
        blok = js[nerede:nerede + 1600]
        assert "askConfirm" in blok
        for yasak in ("confirm(", "alert(", "prompt("):
            assert f" {yasak}" not in blok

    def test_doldurma_sonrasi_rapor_tazelenir(self):
        """Eski rapor ekranda kalırsa kullanıcı güncel olmayan bir fark
        tablosuna bakar."""
        js = self._oku("app.js")
        nerede = js.index("async fillApiHistory()")
        blok = js[nerede:nerede + 1600]
        assert "runReconcile()" in blok
