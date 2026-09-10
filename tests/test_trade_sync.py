"""
CoinTakip — Borsa İşlemi Yakalama Testleri (FAZ F7)

Bu takımın çıkış noktası somut bir olaydır. 6 Eylül 2026'da kullanıcı
Binance'in "Küçük Bakiyeleri Dönüştür" ekranını sordu: bir kullanıcı buna
basarsa ne olur?

Ölçüldü. Ekrandaki 7 coin kullanıcının açık Binance pozisyonlarıyla birebir
örtüşüyordu (SAGA'nın 4 lotunun toplamı bakiyeye tam eşitti). Dönüşüm
yapılsaydı:

    kalan maliyet 434.54 USD  →  ele geçen 17.03 USDT
    yani ~418 USD gerçekleşmiş zarar

...ve bunun HİÇBİRİ deftere girmeyecekti, çünkü toz dönüşümü bir spot işlem
değildir ve `myTrades` ucuna hiç düşmez. "Küçük bakiye" piyasa değeri için
küçüktür, maliyet tabanı için değil.

Buradaki testlerin çoğu o vakayı ve onun etrafındaki sessiz başarısızlık
ihtimallerini kilitler.

HİÇBİR TEST AĞA ÇIKMAZ: borsa çağrıları sahte cevaplarla değiştirilir.
"""

import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(PROJECT_ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import archive                       # noqa: E402
import data_manager                  # noqa: E402
import exchanges                     # noqa: E402
import trade_sync                    # noqa: E402
from trade_sync import TradeSyncService  # noqa: E402


BINANCE_PROFIL = {
    "location": "BINANCE",
    "name": "Binance",
    "family": "binance",
    "base_url": "https://api.binance.com",
    "account_path": "/api/v3/account",
    "enabled": True,
}


def _akislari_sustur(monkeypatch, **ustler):
    """Hesap düzeyindeki BÜTÜN akışları boşa çeker.

    `conftest` imzalı çağrının tek kapısını (`signed_get`) duvarla kapattığı
    için, bir akış susturulmazsa test AĞA ÇIKMAYA ÇALIŞIR ve gürültülü şekilde
    düşer. Bu yardımcı, taramanın tamamını sınayan testlerin ilgilenmedikleri
    akışları tek satırda susturmasını sağlar; `ustler` ile yalnızca sınanan
    akış değiştirilir.
    """
    for ad in ("fetch_dust_log", "fetch_earn_rewards",
               "fetch_soft_staking_rewards",
               "fetch_deposits", "fetch_withdrawals"):
        monkeypatch.setattr(exchanges, ad, ustler.get(ad, lambda *a, **k: []))


def _trade(id_, symbol="ARBUSDT", qty="100", price="0.40", quote="40.0",
           buyer=False, commission="0.04", commission_asset="USDT",
           time_ms=1757000000000):
    return {"symbol": symbol, "id": id_, "orderId": 1, "price": price,
            "qty": qty, "quoteQty": quote, "commission": commission,
            "commissionAsset": commission_asset, "time": time_ms,
            "isBuyer": buyer, "isMaker": False}


# Binance'in gerçek toz cevabının biçimi. Ekran görüntüsündeki dönüşümün
# sayılarıyla dolduruldu.
TOZ_CEVABI = {
    "total": 1,
    "userAssetDribblets": [{
        "operateTime": 1757100000000,
        "totalTransferedAmount": "17.40204840",
        "totalServiceChargeAmount": "0.36254267",
        "transId": 45178372831,
        "targetAsset": "USDT",
        "userAssetDribbletDetails": [
            {"transId": 4359321, "serviceChargeAmount": "0.15581754",
             "amount": "172060", "operateTime": 1757100000000,
             "transferedAmount": "7.79087680", "fromAsset": "DOGS"},
            {"transId": 4359322, "serviceChargeAmount": "0.13815903",
             "amount": "445.96200671", "operateTime": 1757100000000,
             "transferedAmount": "6.90795148", "fromAsset": "SAGA"},
        ],
    }],
}


@pytest.fixture
def servis():
    """Tekil örnek değil YENİ bir servis: conftest tekil örneğin `scan`ini
    sahteleyip ağa çıkmasını engelliyor ve o sahte burada işimize yaramaz."""
    return TradeSyncService()


@pytest.fixture
def kasa_acik(monkeypatch):
    import keyvault
    monkeypatch.setattr(keyvault, "is_unlocked", lambda: True)
    monkeypatch.setattr(exchanges, "credentials_stored", lambda konum: True)
    monkeypatch.setattr(exchanges, "list_profiles",
                        lambda: {"BINANCE": dict(BINANCE_PROFIL)})


def _bakiye_okumasi(varliklar):
    return {"id": "BINANCE", "location": "BINANCE", "source": "exchange",
            "ok": True, "notes": [],
            "balances": [{"asset": a, "qty": q, "free": q, "locked": 0.0}
                         for a, q in varliklar.items()]}


# =====================================================================
class TestTozDonusumu:
    """Bu sınıf F7'nin var oluş sebebidir."""

    def test_toz_donusumu_mytrades_ucunda_gorunmez(self):
        """Kayıt için: toz dönüşümü spot işlem değildir.

        `myTrades` boş dönerken bakiyeden varlık silinmesi, yalnızca
        `myTrades` dinleyen bir sistemin göremeyeceği tek şeydir.
        """
        satirlar = exchanges.dust_rows(TOZ_CEVABI)
        assert len(satirlar) == 2
        # Toz satırlarının hiçbirinde spot işlem numarası (`id`) yok;
        # ayrı bir uçtan gelirler.
        assert all("id" not in s for s in satirlar)

    def test_toz_cevabi_duz_satirlara_acilir(self):
        satirlar = exchanges.dust_rows(TOZ_CEVABI)
        dogs = next(s for s in satirlar if s["from_asset"] == "DOGS")
        assert dogs["amount"] == pytest.approx(172060.0)
        assert dogs["transfered_amount"] == pytest.approx(7.7908768)
        assert dogs["service_charge_amount"] == pytest.approx(0.15581754)
        assert dogs["target_asset"] == "USDT"

    def test_hedef_varlik_yoksa_bnb_varsayilir(self):
        """Klasik BNB dönüşümünde alan hiç gelmeyebiliyor. Bu uydurma değil,
        o dönüşümün belgelenmiş tanımıdır."""
        ham = {"userAssetDribblets": [{
            "operateTime": 1757100000000, "transId": 1,
            "userAssetDribbletDetails": [
                {"transId": 9, "amount": "1", "transferedAmount": "0.01",
                 "serviceChargeAmount": "0.0002", "fromAsset": "XAI"}]}]}
        assert exchanges.dust_rows(ham)[0]["target_asset"] == "BNB"

    def test_toz_bir_satistir_ve_efektif_fiyat_tasir(self):
        satir = next(s for s in exchanges.dust_rows(TOZ_CEVABI)
                     if s["from_asset"] == "SAGA")
        olay = trade_sync.normalize_dust("BINANCE", satir)
        assert olay["side"] == "SELL"
        assert olay["base_asset"] == "SAGA"
        assert olay["quote_asset"] == "USDT"
        assert olay["qty"] == pytest.approx(445.96200671)
        # 6.90795148 / 445.96200671
        assert olay["price"] == pytest.approx(0.01548999, rel=1e-4)

    def test_saga_vakasi_maliyet_tabani_silinirdi(self):
        """6 Eylül 2026 ölçümü: 445.96 SAGA, kalan maliyet ~102 USD,
        ele geçen 6.91 USDT → ~95 USD gerçekleşmiş zarar.

        Testin amacı sayıyı doğrulamak değil, bu zararın artık HESAPLANABİLİR
        olduğunu kilitlemek: özellik geri alınırsa burası kırılır.
        """
        satir = next(s for s in exchanges.dust_rows(TOZ_CEVABI)
                     if s["from_asset"] == "SAGA")
        olay = trade_sync.normalize_dust("BINANCE", satir)
        kalan_maliyet = 102.09          # defterdeki 4 lotun toplamı
        gerceklesen = olay["quote_qty"] - olay["fee_qty"] - kalan_maliyet
        assert gerceklesen == pytest.approx(-95.32, abs=0.05)

    def test_toz_bakiye_etkisi_komisyonu_dusurur(self):
        satir = next(s for s in exchanges.dust_rows(TOZ_CEVABI)
                     if s["from_asset"] == "DOGS")
        etki = trade_sync.olay_bakiye_etkisi(
            trade_sync.normalize_dust("BINANCE", satir))
        assert etki["DOGS"] == pytest.approx(-172060.0)
        assert etki["USDT"] == pytest.approx(7.7908768 - 0.15581754)

    def test_mexc_toz_ucu_sunmuyor_ve_bu_gizlenmez(self):
        """Yokluğu uydurmuyoruz: MEXC'in belgelenmiş bir toz ucu yok."""
        mexc = exchanges.BUILTIN_PROFILES["MEXC"]
        assert exchanges.supports(mexc, "dust_log_path") is False
        assert exchanges.supports(mexc, "my_trades_path") is True
        with pytest.raises(exchanges.ExchangeError, match="toz"):
            exchanges.fetch_dust_log(mexc)

    def test_desteklenmeyen_borsada_toz_sessizce_atlanir(self, servis):
        sonuc = servis._tozu_cek("MEXC", exchanges.BUILTIN_PROFILES["MEXC"])
        assert sonuc == {"events": [], "supported": False}


# =====================================================================
class TestTozAralikParametreleri:
    """7 Eylül 2026, canlı hesapta bulunan hata.

    İlk (aralıksız) çağrı çalışmış, imleç kurulmuştu. Sonraki her tur
    `startTime`'ı TEK BAŞINA gönderdiği için Binance şunu döndürüyordu:

        -1102  Mandatory parameter 'endTTime' was not sent...

    Toz akışı böylece sessizce ölmüştü. Daha kötüsü ikincil zarardı: her
    turda bir hata oluştuğu için `_yazilacak_bakiye` bakiye fotoğrafının
    TAMAMINI donduruyor ve açıklanamayan değişim tespiti hiç çalışmıyordu —
    yani toz özelliğini eklemekteki asıl amaç olan güvenlik ağı kapalıydı.
    """

    def _yakala(self, monkeypatch):
        yakalanan = {}

        def sahte_get(profil, yol, anahtar, gizli, params):
            yakalanan.update({"yol": yol, "params": dict(params or {})})
            return {"userAssetDribblets": []}

        monkeypatch.setattr(exchanges, "signed_get", sahte_get)
        monkeypatch.setattr(exchanges, "_anahtarlar", lambda *a, **k: ("k", "s"))
        return yakalanan

    def test_duzenli_tarama_hic_aralik_gondermez(self, servis, monkeypatch):
        """Düzenli tarama artık sunucu tarafı filtreye bel bağlamıyor.

        Uç zaten son 100 kayıtla sınırlı, ağırlığı 1 ve toz dönüşümü saatte
        en fazla bir kez yapılabiliyor. Aralık göndermemek, aynı hatanın
        tekrar edilme ihtimalini tümden ortadan kaldırır.
        """
        yakalanan = self._yakala(monkeypatch)
        archive.set_sync_cursor("BINANCE", trade_sync.TOZ_KAPSAMI,
                                cursor=1757100000000)
        servis._tozu_cek("BINANCE", dict(BINANCE_PROFIL))
        assert yakalanan["params"] == {}

    def test_baslangic_verilirse_bitis_de_gonderilir(self, monkeypatch):
        """Asıl kural: Binance bu ikisini ÇİFT ister."""
        yakalanan = self._yakala(monkeypatch)
        exchanges.fetch_dust_log(dict(BINANCE_PROFIL), start_time_ms=1757100000000)
        assert "startTime" in yakalanan["params"]
        assert "endTime" in yakalanan["params"]
        assert yakalanan["params"]["endTime"] > yakalanan["params"]["startTime"]

    def test_bitis_verilirse_baslangic_da_gonderilir(self, monkeypatch):
        yakalanan = self._yakala(monkeypatch)
        exchanges.fetch_dust_log(dict(BINANCE_PROFIL), end_time_ms=1757100000000)
        assert yakalanan["params"]["endTime"] == 1757100000000
        assert yakalanan["params"]["startTime"] == (
            1757100000000 - exchanges.DUST_VARSAYILAN_PENCERE_MS)

    def test_imlecten_eski_kayitlar_yerelde_suzulur(self, servis, monkeypatch):
        """Aralığı sunucuya bırakmadığımıza göre süzmeyi kendimiz yapmalıyız.

        TOZ_CEVABI'ndaki iki kayıt da 1757100000000 anına ait; imleç oraya
        kurulmuşken hiçbiri yeniden olay üretmemeli.
        """
        monkeypatch.setattr(exchanges, "fetch_dust_log",
                            lambda *a, **k: exchanges.dust_rows(TOZ_CEVABI))
        archive.set_sync_cursor("BINANCE", trade_sync.TOZ_KAPSAMI,
                                cursor=1757100000000)
        sonuc = servis._tozu_cek("BINANCE", dict(BINANCE_PROFIL))
        assert sonuc["events"] == []

    def test_imlecten_yeni_kayit_gecer(self, servis, monkeypatch):
        monkeypatch.setattr(exchanges, "fetch_dust_log",
                            lambda *a, **k: exchanges.dust_rows(TOZ_CEVABI))
        archive.set_sync_cursor("BINANCE", trade_sync.TOZ_KAPSAMI,
                                cursor=1757099999999)
        sonuc = servis._tozu_cek("BINANCE", dict(BINANCE_PROFIL))
        assert len(sonuc["events"]) == 2

    def test_basarili_tur_eski_hatayi_temizler(self, servis, monkeypatch):
        """Hata kaydı kalıcı olsaydı, düzeltmeden sonra bile fotoğraf
        donmaya devam ederdi."""
        _akislari_sustur(monkeypatch)
        archive.set_sync_cursor("BINANCE", trade_sync.TOZ_KAPSAMI,
                                error="HTTP 400: endTTime")
        servis._tozu_cek("BINANCE", dict(BINANCE_PROFIL))
        assert not archive.get_sync_cursor(
            "BINANCE", trade_sync.TOZ_KAPSAMI).get("last_error")


# =====================================================================
class TestNormalizasyon:

    def test_satis_olayi(self):
        o = trade_sync.normalize_trade("BINANCE", _trade(991))
        assert o["side"] == "SELL"
        assert o["event_uid"] == "BINANCE:trade:ARBUSDT:991"
        assert o["base_asset"] == "ARB" and o["quote_asset"] == "USDT"

    def test_alimda_komisyon_isleme_varligindansa_net_miktar_yazilir(self):
        """CSV okuyucusu (`reconcile.load_binance_trades`) aynı düzeltmeyi
        yapıyor. İki yolun farklı sonuç vermesi, aynı işlemin dosyadan mı
        API'den mi geldiğine göre farklı bakiye üretirdi."""
        o = trade_sync.normalize_trade(
            "BINANCE", _trade(1, buyer=True, commission="0.1",
                              commission_asset="ARB"))
        assert o["qty"] == pytest.approx(99.9)
        assert json.loads(o["raw_json"])["gross_qty"] == pytest.approx(100.0)

    def test_komisyon_bnb_ise_ayri_varliktan_duser(self):
        etki = trade_sync.olay_bakiye_etkisi(trade_sync.normalize_trade(
            "BINANCE", _trade(2, buyer=True, commission="0.002",
                              commission_asset="BNB")))
        assert etki["ARB"] == pytest.approx(100.0)
        assert etki["BNB"] == pytest.approx(-0.002)

    def test_alimda_taban_komisyonu_iki_kez_dusulmez(self):
        etki = trade_sync.olay_bakiye_etkisi(trade_sync.normalize_trade(
            "BINANCE", _trade(3, buyer=True, commission="0.1",
                              commission_asset="ARB")))
        assert etki["ARB"] == pytest.approx(99.9)

    def test_satista_kot_komisyonu_gelirden_duser(self):
        etki = trade_sync.olay_bakiye_etkisi(
            trade_sync.normalize_trade("BINANCE", _trade(4)))
        assert etki["USDT"] == pytest.approx(39.96)

    def test_sembolsuz_satir_reddedilir(self):
        with pytest.raises(ValueError):
            trade_sync.normalize_trade("BINANCE", {"id": 1})


# =====================================================================
class TestSembolSecimi:

    def _defter(self):
        return {"transactions": [
            {"id": 1, "coin": "ARBUSDT", "exchange": "BINANCE", "status": "Aktif",
             "qty": 100.0, "cost": 1.0},
            {"id": 2, "coin": "SAGAUSDT", "exchange": "BINANCE",
             "status": "Kapandı / İzleme", "qty": 5.0, "cost": 1.0},
            {"id": 3, "coin": "GOATUSDT", "exchange": "MEXC", "status": "Aktif",
             "qty": 5.0, "cost": 1.0},
        ]}

    def test_defterdeki_acik_pozisyonlar_alinir(self):
        s = trade_sync.aday_semboller("BINANCE", self._defter(), [])
        assert "ARBUSDT" in s
        assert "SAGAUSDT" not in s      # kapanmış
        assert "GOATUSDT" not in s      # başka borsa

    def test_bakiyedeki_yeni_coin_de_alinir(self):
        """Defterde HİÇ olmayan yeni bir alım ancak bakiyede görünür."""
        s = trade_sync.aday_semboller(
            "BINANCE", self._defter(), [{"asset": "TIA", "qty": 3.0}])
        assert "TIAUSDT" in s

    def test_nakit_varliklar_sembol_uretmez(self):
        s = trade_sync.aday_semboller(
            "BINANCE", {"transactions": []},
            [{"asset": "USDT", "qty": 100.0}, {"asset": "USDC", "qty": 1.0}])
        assert s == []

    def test_degisen_varliga_daraltma(self):
        """Bakiyesi değişmemiş bir sembolde yeni işlem olamaz; her turda 20
        ağırlık harcamanın anlamı yok."""
        s = trade_sync.aday_semboller(
            "BINANCE", self._defter(), [{"asset": "TIA", "qty": 3.0}],
            degisen_varliklar={"TIA"})
        assert s == ["TIAUSDT"]


# =====================================================================
class TestAciklanamayanDegisim:

    def test_islemle_aciklanan_degisim_bildirilmez(self):
        olay = trade_sync.normalize_trade("BINANCE", _trade(1))
        farklar = trade_sync.bakiye_farki(
            {"ARB": 100.0, "USDT": 10.0}, {"USDT": 49.96})
        assert trade_sync.aciklanamayan_degisimler(farklar, [olay]) == []

    def test_aciklanamayan_degisim_bildirilir(self):
        """Para yatırma bu sürümün kapsamı dışında — ama görünmez değil."""
        farklar = trade_sync.bakiye_farki({"USDT": 10.0}, {"USDT": 510.0})
        out = trade_sync.aciklanamayan_degisimler(farklar, [])
        assert len(out) == 1
        assert out[0]["asset"] == "USDT"
        assert out[0]["unexplained"] == pytest.approx(500.0)

    def test_yuvarlama_farki_anomali_uretmez(self):
        olay = trade_sync.normalize_trade("BINANCE", _trade(1))
        farklar = trade_sync.bakiye_farki(
            {"ARB": 100.0, "USDT": 10.0}, {"USDT": 49.9600001})
        assert trade_sync.aciklanamayan_degisimler(farklar, [olay]) == []

    def test_toz_donusumu_anomali_olarak_kalmaz(self, servis, kasa_acik,
                                                monkeypatch):
        """Toz okunabiliyorsa dönüşüm AÇIKLANIR; okunamıyorsa açıklanamayan
        değişim olarak yine de görünür. İkisi de sessizlikten iyidir."""
        monkeypatch.setattr(archive, "get_balance_state",
                            lambda ex: {"DOGS": 172060.0, "USDT": 10.0})
        monkeypatch.setattr(exchanges, "read_exchange",
                            lambda k, p=None: _bakiye_okumasi({"USDT": 17.63}))
        monkeypatch.setattr(exchanges, "fetch_my_trades",
                            lambda *a, **k: [])
        monkeypatch.setattr(
            exchanges, "fetch_dust_log",
            lambda *a, **k: [s for s in exchanges.dust_rows(TOZ_CEVABI)
                             if s["from_asset"] == "DOGS"])
        archive.set_sync_cursor("BINANCE", trade_sync.TOZ_KAPSAMI, cursor=1)

        rapor = servis._borsayi_tara("BINANCE", dict(BINANCE_PROFIL), full=True)
        assert [a["asset"] for a in rapor["unexplained"]] == []
        assert rapor["found_events"] == 1


# =====================================================================
class TestDonmusFotograf:
    """7 Eylül 2026 gecesi yaşanan yanlış alarm.

    Toz ucu 22 saat hata verdi. `_yazilacak_bakiye` bunu doğru bulup bakiye
    fotoğrafını 00:58'de DONDURDU — sinyali tüketmemek için, bilerek. Ama
    `aciklanamayan_degisimler` farkı yalnızca O TARAMANIN bulgularıyla
    mahsup ediyordu. Toz düzelince ilk başarılı tarama, donmuş (satış
    öncesi) fotoğrafı güncel (satış sonrası) bakiyeyle karşılaştırdı ve
    kullanıcının SABAH ÇOKTAN DEFTERE İŞLEDİĞİ ARB satışını üç ayrı
    "açıklanamayan" satır olarak raporladı:

        -144.6 ARB   +27.60414 USDT   -0.00002757 BNB

    Kullanıcı haklı olarak programın sapıttığını düşündü. İki kural
    birbiriyle çelişiyordu; bu sınıf çelişkinin kapandığını kilitler.
    """

    FOTOGRAF_TS = 1757000000.0

    def _fotograf(self, monkeypatch, varliklar):
        monkeypatch.setattr(archive, "get_balance_state", lambda ex: varliklar)
        monkeypatch.setattr(archive, "get_balance_state_ts",
                            lambda ex: self.FOTOGRAF_TS)

    def test_onceki_taramada_yakalanan_satis_anomali_uretmez(
            self, servis, kasa_acik, monkeypatch):
        """Vakanın kendisi. Satış arşivde DURUYOR ama bu turun bulgusu
        değil; buna rağmen farkı açıklamalı."""
        satis = trade_sync.normalize_trade(
            "BINANCE", _trade(195467667, qty="144.6", price="0.1909",
                              quote="27.60414", commission="0.00002757",
                              commission_asset="BNB",
                              time_ms=int((self.FOTOGRAF_TS + 60) * 1000)))
        archive.record_exchange_events([satis])

        self._fotograf(monkeypatch, {"ARB": 1446.2774, "USDT": 1220.332466,
                                     "BNB": 0.00146542})
        monkeypatch.setattr(exchanges, "read_exchange",
                            lambda k, p=None: _bakiye_okumasi(
                                {"ARB": 1301.6774, "USDT": 1247.936606,
                                 "BNB": 0.00143785}))
        monkeypatch.setattr(exchanges, "fetch_my_trades", lambda *a, **k: [])
        _akislari_sustur(monkeypatch)

        rapor = servis._borsayi_tara("BINANCE", dict(BINANCE_PROFIL), full=True)
        assert rapor["unexplained"] == []

    def test_deftere_islenmis_olay_da_sayilir(self, servis, kasa_acik,
                                              monkeypatch):
        """Kullanıcının satırla ilgili kararı, işlemin gerçekleşmiş olduğu
        gerçeğini değiştirmez."""
        satis = trade_sync.normalize_trade(
            "BINANCE", _trade(700, qty="100", price="0.40", quote="40.0",
                              time_ms=int((self.FOTOGRAF_TS + 60) * 1000)))
        archive.record_exchange_events([satis])
        archive.set_event_status(satis["event_uid"], archive.EVENT_APPLIED, None)

        self._fotograf(monkeypatch, {"ARB": 100.0, "USDT": 10.0})
        monkeypatch.setattr(exchanges, "read_exchange",
                            lambda k, p=None: _bakiye_okumasi({"USDT": 49.96}))
        monkeypatch.setattr(exchanges, "fetch_my_trades", lambda *a, **k: [])
        _akislari_sustur(monkeypatch)

        rapor = servis._borsayi_tara("BINANCE", dict(BINANCE_PROFIL), full=True)
        assert rapor["unexplained"] == []

    def test_yok_sayilan_olay_da_sayilir(self, servis, kasa_acik, monkeypatch):
        """"Yok say" kararı bakiyeyi geri getirmez."""
        satis = trade_sync.normalize_trade(
            "BINANCE", _trade(701, qty="100", price="0.40", quote="40.0",
                              time_ms=int((self.FOTOGRAF_TS + 60) * 1000)))
        archive.record_exchange_events([satis])
        archive.set_event_status(satis["event_uid"], archive.EVENT_DISMISSED)

        self._fotograf(monkeypatch, {"ARB": 100.0, "USDT": 10.0})
        monkeypatch.setattr(exchanges, "read_exchange",
                            lambda k, p=None: _bakiye_okumasi({"USDT": 49.96}))
        monkeypatch.setattr(exchanges, "fetch_my_trades", lambda *a, **k: [])
        _akislari_sustur(monkeypatch)

        rapor = servis._borsayi_tara("BINANCE", dict(BINANCE_PROFIL), full=True)
        assert rapor["unexplained"] == []

    def test_fotograftan_onceki_olay_mahsup_edilmez(self, servis):
        """Fotoğraf çekilmeden önce olmuş bir işlemin etkisi zaten `onceki`
        içinde sayılıdır; ikinci kez mahsup etmek TERS yönde yanlış bir
        anomali üretirdi."""
        eski = trade_sync.normalize_trade(
            "BINANCE", _trade(500, time_ms=int((self.FOTOGRAF_TS - 600) * 1000)))
        archive.record_exchange_events([eski])
        archive.set_balance_state("BINANCE", {"USDT": 10.0})

        cikan = servis._aciklayici_olaylar("BINANCE", [])
        assert [o["event_uid"] for o in cikan] == []

    def test_ayni_olay_iki_kez_mahsup_edilmez(self, servis, monkeypatch):
        """Bu turun bulgusu arşivde de varsa çift sayılmamalı."""
        satis = trade_sync.normalize_trade(
            "BINANCE", _trade(800, time_ms=int((self.FOTOGRAF_TS + 60) * 1000)))
        archive.record_exchange_events([satis])
        monkeypatch.setattr(archive, "get_balance_state_ts",
                            lambda ex: self.FOTOGRAF_TS)

        cikan = servis._aciklayici_olaylar("BINANCE", [satis])
        assert len(cikan) == 1

    def test_kendi_gozlemimiz_mahsup_edilmez(self, servis, monkeypatch):
        """Açıklanamayan satırlar BİZİM gözlemimizdir. Onları mahsup etmek,
        bir farkı kendisiyle açıklamak — yani çift saymak — olurdu."""
        anomali = servis._anomali_olayi(
            "BINANCE", {"asset": "USDT", "delta": 500.0, "explained": 0.0,
                        "unexplained": 500.0})
        anomali["trade_ts"] = self.FOTOGRAF_TS + 60
        archive.record_exchange_events([anomali])
        monkeypatch.setattr(archive, "get_balance_state_ts",
                            lambda ex: self.FOTOGRAF_TS)

        cikan = servis._aciklayici_olaylar("BINANCE", [])
        assert cikan == []

    def test_fotograf_yoksa_eski_davranis_surer(self, servis, monkeypatch):
        """İlk tarama yolunu bozmuyoruz."""
        monkeypatch.setattr(archive, "get_balance_state_ts", lambda ex: None)
        olay = trade_sync.normalize_trade("BINANCE", _trade(900))
        assert servis._aciklayici_olaylar("BINANCE", [olay]) == [olay]


# =====================================================================
class TestImlec:
    """İmleç mantığı: ilk tarama başlangıç kurar, sonrası yakalar."""

    def test_ilk_tarama_olay_uretmez_sadece_imlec_kurar(self, servis,
                                                        monkeypatch):
        monkeypatch.setattr(exchanges, "fetch_my_trades",
                            lambda p, s, from_id=None, **k: [_trade(500),
                                                             _trade(501)])
        olaylar, temel = servis._sembolu_cek("BINANCE", dict(BINANCE_PROFIL),
                                             "ARBUSDT")
        assert temel is True
        assert olaylar == []
        assert archive.get_sync_cursor("BINANCE", "ARBUSDT")["cursor"] == "501"

    def test_ikinci_tarama_yeni_islemi_yakalar(self, servis, monkeypatch):
        cagrilar = []

        def sahte(profil, sembol, from_id=None, **k):
            cagrilar.append(from_id)
            return [] if from_id is None else [_trade(502)]

        archive.set_sync_cursor("BINANCE", "ARBUSDT", cursor=501)
        monkeypatch.setattr(exchanges, "fetch_my_trades", sahte)
        olaylar, temel = servis._sembolu_cek("BINANCE", dict(BINANCE_PROFIL),
                                             "ARBUSDT")
        assert temel is False
        assert cagrilar[0] == 502          # son görülen + 1
        assert [o["_trade_id"] for o in olaylar] == [502]

    def test_hata_imleci_sifirlamaz(self):
        """Başarısız bir çağrı yüzünden imleci kaybetmek, aradaki işlemleri
        sessizce atlamak demek olurdu."""
        archive.set_sync_cursor("BINANCE", "ARBUSDT", cursor=501)
        archive.set_sync_cursor("BINANCE", "ARBUSDT", error="HTTP 418")
        durum = archive.get_sync_cursor("BINANCE", "ARBUSDT")
        assert durum["cursor"] == "501"
        assert "418" in durum["last_error"]

    def test_gecersiz_sembol_tekrar_yoklanmaz(self, servis):
        """Delist olmuş bir coin için her turda 20 ağırlık harcamayalım."""
        archive.set_sync_cursor("BINANCE", "OLDUSDT",
                                error="HTTP 400: {\"code\":-1121,"
                                      "\"msg\":\"Invalid symbol.\"}")
        assert servis._sembol_atlanir_mi("BINANCE", "OLDUSDT") is True

    def test_bir_kez_calismis_sembol_gecici_hatada_atlanmaz(self, servis):
        archive.set_sync_cursor("BINANCE", "ARBUSDT", cursor=501)
        archive.set_sync_cursor("BINANCE", "ARBUSDT", error="timeout")
        assert servis._sembol_atlanir_mi("BINANCE", "ARBUSDT") is False

    def test_toz_ilk_taramasi_da_temel_kurar(self, servis, monkeypatch):
        monkeypatch.setattr(exchanges, "fetch_dust_log",
                            lambda *a, **k: exchanges.dust_rows(TOZ_CEVABI))
        sonuc = servis._tozu_cek("BINANCE", dict(BINANCE_PROFIL))
        assert sonuc["baseline"] is True
        assert sonuc["events"] == []
        assert archive.get_sync_cursor(
            "BINANCE", trade_sync.TOZ_KAPSAMI)["cursor"] == "1757100000000"


# =====================================================================
class TestTekillestirme:

    def test_ayni_islem_iki_kez_yazilmaz(self):
        olay = trade_sync.normalize_trade("BINANCE", _trade(700))
        assert archive.record_exchange_events([olay]) == 1
        assert archive.record_exchange_events([olay]) == 0
        assert len(archive.list_exchange_events()) == 1

    def test_islenmis_satir_yeniden_bekliyor_olmaz(self):
        """Kullanıcının verdiği karar, yeniden çekim yüzünden silinmemeli."""
        olay = trade_sync.normalize_trade("BINANCE", _trade(701))
        archive.record_exchange_events([olay])
        archive.set_event_status(olay["event_uid"], archive.EVENT_APPLIED, 42)
        archive.record_exchange_events([olay])
        assert archive.get_exchange_event(
            olay["event_uid"])["status"] == archive.EVENT_APPLIED

    def test_yalnizca_bekleyen_satirin_durumu_degisir(self):
        olay = trade_sync.normalize_trade("BINANCE", _trade(702))
        archive.record_exchange_events([olay])
        assert archive.set_event_status(olay["event_uid"],
                                        archive.EVENT_DISMISSED) is True
        assert archive.set_event_status(olay["event_uid"],
                                        archive.EVENT_APPLIED, 1) is False

    def test_yazamama_ile_yeni_yok_ayrilir(self, monkeypatch):
        """`None` (arşive ulaşılamadı) ile `0` (yeni işlem yok) aynı şey değil."""
        monkeypatch.setattr(archive, "init_archive", lambda: False)
        assert archive.record_exchange_events(
            [trade_sync.normalize_trade("BINANCE", _trade(703))]) is None


# =====================================================================
class TestDeftereIsleme:

    def _bekleyen(self, id_=800, **kw):
        olay = trade_sync.normalize_trade("BINANCE", _trade(id_, **kw))
        archive.record_exchange_events([olay])
        return olay

    def test_satis_deftere_islenir_ve_kaynak_damgalanir(self, servis,
                                                        kayitli_portfoy):
        import data_manager
        olay = self._bekleyen(810, symbol="ETHUSDT", qty="0.5", price="2100",
                              quote="1050.0", commission="1.0")
        servis.apply_event(olay["event_uid"], live_prices={})

        defter = data_manager.load_portfolio()
        kapanan = [t for t in defter["transactions"]
                   if t.get("source_ref") == olay["event_uid"]]
        assert len(kapanan) == 1
        assert kapanan[0]["exit_price"] == pytest.approx(2100.0)
        assert kapanan[0]["date"] == "2025-09-04" or kapanan[0]["date"][:2] == "20"
        assert archive.get_exchange_event(
            olay["event_uid"])["status"] == archive.EVENT_APPLIED

    def test_satis_nakdi_kasaya_yazar(self, servis, kayitli_portfoy):
        import data_manager
        onceki = data_manager.load_portfolio()["wallets"]["usdt_cash"]
        olay = self._bekleyen(811, symbol="ETHUSDT", qty="0.5", price="2100",
                              quote="1050.0", commission="1.0")
        servis.apply_event(olay["event_uid"], live_prices={})
        sonraki = data_manager.load_portfolio()["wallets"]["usdt_cash"]
        assert sonraki > onceki

    def test_ayni_islem_ikinci_kez_islenemez(self, servis, kayitli_portfoy):
        olay = self._bekleyen(812, symbol="ETHUSDT", qty="0.5", price="2100",
                              quote="1050.0")
        servis.apply_event(olay["event_uid"], live_prices={})
        with pytest.raises(ValueError, match="tekrar işlenemez"):
            servis.apply_event(olay["event_uid"], live_prices={})

    def test_defterde_acik_pozisyon_yoksa_satis_reddedilir(self, servis,
                                                           kayitli_portfoy):
        olay = self._bekleyen(813, symbol="ARBUSDT")
        with pytest.raises(ValueError, match="açık pozisyon yok"):
            servis.apply_event(olay["event_uid"], live_prices={})

    def test_alim_yeni_kayit_olusturur(self, servis, kayitli_portfoy):
        import data_manager
        olay = self._bekleyen(814, symbol="ARBUSDT", buyer=True,
                              commission="0.0", commission_asset="USDT")
        servis.apply_event(olay["event_uid"], live_prices={})
        defter = data_manager.load_portfolio()
        yeni = [t for t in defter["transactions"]
                if t.get("source_ref") == olay["event_uid"]]
        assert len(yeni) == 1
        assert yeni[0]["status"] == "Aktif"
        assert yeni[0]["coin"] == "ARBUSDT"
        assert yeni[0]["qty"] == pytest.approx(100.0)

    def test_aciklanamayan_degisim_deftere_islenemez(self, servis,
                                                     kayitli_portfoy):
        anomali = servis._anomali_olayi(
            "BINANCE", {"asset": "USDT", "delta": 500.0, "explained": 0.0,
                        "unexplained": 500.0})
        archive.record_exchange_events([anomali])
        with pytest.raises(ValueError, match="işlenemez"):
            servis.apply_event(anomali["event_uid"], live_prices={})

    def test_dolar_fiyati_bilinmiyorsa_islem_reddedilir(self, servis,
                                                        kayitli_portfoy):
        """Uydurma bir kurla gerçekleşmiş K/Z yazmak, yanlış sayıyı doğru gibi
        deftere koymak olurdu."""
        olay = trade_sync.normalize_trade("BINANCE", {
            "symbol": "ETHBTC", "id": 815, "price": "0.03", "qty": "0.5",
            "quoteQty": "0.015", "commission": "0", "commissionAsset": "BTC",
            "time": 1757000000000, "isBuyer": False})
        archive.record_exchange_events([olay])
        with pytest.raises(ValueError, match="dolar fiyatı hesaplanamadı"):
            servis.apply_event(olay["event_uid"], live_prices={})

    def test_stabil_olmayan_kot_canli_fiyatla_cevrilir(self, servis,
                                                       kayitli_portfoy):
        olay = trade_sync.normalize_trade("BINANCE", {
            "symbol": "ETHBTC", "id": 816, "price": "0.02", "qty": "0.5",
            "quoteQty": "0.01", "commission": "0", "commissionAsset": "BTC",
            "time": 1757000000000, "isBuyer": False})
        assert servis._dolar_fiyati(
            olay, {"BTCUSDT": {"price": 100000.0}}) == pytest.approx(2000.0)

    def test_yok_sayilan_satir_deftere_islenemez(self, servis, kayitli_portfoy):
        olay = self._bekleyen(817, symbol="ETHUSDT")
        servis.dismiss_event(olay["event_uid"])
        with pytest.raises(ValueError):
            servis.apply_event(olay["event_uid"], live_prices={})


# =====================================================================
class TestIpuclari:

    def test_ayni_gun_benzer_miktar_cift_kayit_uyarisi_verir(self, servis):
        defter = {"transactions": [
            {"id": 9, "coin": "ETHUSDT", "exchange": "BINANCE",
             "status": "Kapandı / İzleme", "qty": 0.5, "cost": 2000.0,
             "exit_date": "2025-09-04"},
        ]}
        olay = trade_sync.normalize_trade(
            "BINANCE", _trade(900, symbol="ETHUSDT", qty="0.5", price="2100",
                              quote="1050.0", time_ms=1757000000000))
        olay["trade_at"] = "2025-09-04T12:00:00"
        ipucu = servis._ipucu({**olay, "kind": "TRADE"}, defter)
        assert "possible_duplicate" in ipucu
        assert ipucu["possible_duplicate"]["tx_id"] == 9

    def test_uyari_olasilik_dilinde_yazilir(self, servis):
        """Elle girilmiş kayıtlar borsa işlem numarası taşımıyor; kesin
        bilinmeyen bir şey kesinmiş gibi söylenemez."""
        defter = {"transactions": [
            {"id": 9, "coin": "ETHUSDT", "exchange": "BINANCE",
             "status": "Kapandı / İzleme", "qty": 0.5, "cost": 2000.0,
             "exit_date": "2025-09-04"}]}
        olay = trade_sync.normalize_trade(
            "BINANCE", _trade(901, symbol="ETHUSDT", qty="0.5"))
        olay["trade_at"] = "2025-09-04T12:00:00"
        not_metni = servis._ipucu(olay, defter)["possible_duplicate"]["note"]
        assert "olabilir" in not_metni

    def test_acik_lot_yokken_de_cift_kayit_ipucu_verilir(self, servis):
        """En çok burada gerekli: satış zaten elle işlenmişse açık lot kalmaz
        ve kullanıcı sadece "açık pozisyon yok" görürse sebebini anlamaz."""
        defter = {"transactions": [
            {"id": 9, "coin": "ETHUSDT", "exchange": "BINANCE",
             "status": "Kapandı / İzleme", "qty": 0.5, "cost": 2000.0,
             "exit_date": "2025-09-04"}]}
        olay = trade_sync.normalize_trade(
            "BINANCE", _trade(903, symbol="ETHUSDT", qty="0.5"))
        olay["trade_at"] = "2025-09-04T12:00:00"
        ipucu = servis._ipucu(olay, defter)
        assert ipucu["applicable"] is False
        assert "possible_duplicate" in ipucu
        assert "zaten" in ipucu["reason"]

    def test_defterden_fazla_satis_uyarilir(self, servis, ornek_portfoy):
        olay = trade_sync.normalize_trade(
            "BINANCE", _trade(902, symbol="ETHUSDT", qty="99"))
        ipucu = servis._ipucu(olay, ornek_portfoy)
        assert "warning" in ipucu
        assert ipucu["applicable"] is True

    def test_anomali_satiri_islenebilir_degildir(self, servis):
        anomali = servis._anomali_olayi(
            "BINANCE", {"asset": "USDT", "delta": 1.0, "explained": 0.0,
                        "unexplained": 1.0})
        ipucu = servis._ipucu(anomali, {"transactions": []})
        assert ipucu["applicable"] is False


# =====================================================================
class TestTaramaDavranisi:

    def test_kasa_kilitliyken_sessizce_atlanir(self, servis, monkeypatch):
        """Anahtarlar kasada; kasa her açılışta elle açılıyor. Her turda hata
        üretmek gerçek hataları görünmez yapan gürültü olurdu."""
        import keyvault
        monkeypatch.setattr(keyvault, "is_unlocked", lambda: False)
        monkeypatch.setattr(exchanges, "list_profiles",
                            lambda: {"BINANCE": dict(BINANCE_PROFIL)})
        rapor = servis.scan()
        assert rapor["ok"] is False
        assert rapor["skipped"] == "vault_locked"
        assert "kasa" in rapor["message"].lower()

    def test_profil_yoksa_neden_soylenir(self, servis, monkeypatch):
        monkeypatch.setattr(exchanges, "list_profiles", lambda: {})
        rapor = servis.scan()
        assert rapor["skipped"] == "no_profile"
        assert rapor["message"]

    def test_ust_uste_binen_tarama_engellenir(self, servis):
        servis._tarama_kilidi.acquire()
        try:
            assert servis.scan()["skipped"] == "already_running"
        finally:
            servis._tarama_kilidi.release()

    def test_ilk_bakiye_taramasi_anomali_uretmez(self, servis, kasa_acik,
                                                 monkeypatch):
        """İlk turda her varlık "değişmiş" görünür; hepsini anomali diye
        listelemek uyarıyı ilk günden değersizleştirirdi."""
        monkeypatch.setattr(exchanges, "read_exchange",
                            lambda k, p=None: _bakiye_okumasi({"ARB": 100.0}))
        monkeypatch.setattr(exchanges, "fetch_my_trades", lambda *a, **k: [])
        _akislari_sustur(monkeypatch)
        rapor = servis._borsayi_tara("BINANCE", dict(BINANCE_PROFIL), full=True)
        assert rapor["first_balance_scan"] is True
        assert rapor["unexplained"] == []

    def test_bakiye_okunamazsa_sembol_yoklanmaz(self, servis, kasa_acik,
                                                monkeypatch):
        def patla(*a, **k):
            raise AssertionError("bakiye okunamadıysa sembol yoklanmamalı")

        monkeypatch.setattr(
            exchanges, "read_exchange",
            lambda k, p=None: {"ok": False, "balances": [],
                               "notes": [{"level": "error",
                                          "message": "kasa kilitli"}]})
        monkeypatch.setattr(exchanges, "fetch_my_trades", patla)
        rapor = servis._borsayi_tara("BINANCE", dict(BINANCE_PROFIL))
        assert rapor["ok"] is False

    def test_hatali_sembolun_degisim_sinyali_tuketilmez(self, servis):
        """Bakiye fotoğrafı bir SİNYALDİR: bir varlık değiştiği için o sembolü
        yokluyoruz. Başarısız bir çekimden sonra fotoğrafı tazelersek,
        bakamadığımız değişim bir daha hiç fark edilmez."""
        onceki = {"ARB": 100.0, "TIA": 5.0}
        simdiki = {"ARB": 50.0, "TIA": 9.0}
        yazilacak = servis._yazilacak_bakiye(
            onceki, simdiki, [{"scope": "ARBUSDT", "error": "HTTP 500"}], False)
        assert yazilacak["ARB"] == 100.0     # sinyal korundu
        assert yazilacak["TIA"] == 9.0       # çalışan sembol ilerledi

    def test_arsive_yazilamadiysa_fotograf_hic_tazelenmez(self, servis):
        onceki = {"ARB": 100.0}
        yazilacak = servis._yazilacak_bakiye(onceki, {"ARB": 50.0}, [], True)
        assert yazilacak == onceki

    def test_toz_hatasi_tum_fotografi_dondurur(self, servis):
        """Toz akışının hangi varlığı etkilediğini bilmiyoruz."""
        onceki = {"ARB": 100.0, "TIA": 5.0}
        yazilacak = servis._yazilacak_bakiye(
            onceki, {"ARB": 50.0, "TIA": 9.0},
            [{"scope": trade_sync.TOZ_KAPSAMI, "error": "HTTP 418"}], False)
        assert yazilacak == onceki

    def test_hata_varken_anomali_uretilmez(self, servis, kasa_acik, monkeypatch):
        """"Açıklanamayan değişim" ile "bakamadım" ayrı şeylerdir; ikincisini
        birincisi gibi sunmak yanlış bir iddia olurdu."""
        monkeypatch.setattr(archive, "get_balance_state",
                            lambda ex: {"ARB": 100.0})
        monkeypatch.setattr(exchanges, "read_exchange",
                            lambda k, p=None: _bakiye_okumasi({"ARB": 40.0}))

        def patla(*a, **k):
            raise exchanges.ExchangeError("HTTP 500")

        monkeypatch.setattr(exchanges, "fetch_my_trades", patla)
        _akislari_sustur(monkeypatch)
        rapor = servis._borsayi_tara("BINANCE", dict(BINANCE_PROFIL), full=True)
        assert rapor["unexplained"] == []
        assert rapor["unexplained_skipped"] is True

    def test_bir_sembolun_hatasi_digerlerini_durdurmaz(self, servis, kasa_acik,
                                                       monkeypatch):
        def sahte(profil, sembol, from_id=None, **k):
            if sembol == "ARBUSDT":
                raise exchanges.ExchangeError("HTTP 500")
            return []

        monkeypatch.setattr(
            exchanges, "read_exchange",
            lambda k, p=None: _bakiye_okumasi({"ARB": 1.0, "TIA": 1.0}))
        monkeypatch.setattr(exchanges, "fetch_my_trades", sahte)
        _akislari_sustur(monkeypatch)
        rapor = servis._borsayi_tara("BINANCE", dict(BINANCE_PROFIL), full=True)
        assert rapor["ok"] is True
        assert [h["scope"] for h in rapor["errors"]] == ["ARBUSDT"]
        assert "TIAUSDT" in rapor["symbols"]


# =====================================================================
class TestSaltOkuma:
    """Kullanıcıya verilen söz: bu bağlantı hiçbir koşulda emir veremez."""

    def test_islem_uclari_yalnizca_get_kullanir(self, monkeypatch):
        cagrilar = []
        monkeypatch.setattr(exchanges, "signed_get",
                            lambda p, yol, k, s, params=None:
                            (cagrilar.append((yol, params)) or []))
        monkeypatch.setattr(exchanges, "_kasadan", lambda k: ("a", "b"))
        exchanges.fetch_my_trades(exchanges.BUILTIN_PROFILES["BINANCE"],
                                  "ARBUSDT", from_id=5)
        assert cagrilar[0][0] == "/api/v3/myTrades"
        assert cagrilar[0][1]["fromId"] == 5

    def test_modulde_yazma_metodu_yok(self):
        kaynak = open(os.path.join(APP_DIR, "exchanges.py"),
                      encoding="utf-8").read()
        for yasak in ('method="POST"', "method='POST'", '"DELETE"', "urlopen(req, data"):
            assert yasak not in kaynak, f"exchanges.py yazma çağrısı içeriyor: {yasak}"

    def test_trade_sync_kendi_http_katmanini_kurmaz(self):
        kaynak = open(os.path.join(APP_DIR, "trade_sync.py"),
                      encoding="utf-8").read()
        assert "urllib" not in kaynak
        assert "requests" not in kaynak

    def test_anahtarin_gidecegi_yol_anahtarsiz_degistirilemez(self):
        """`my_trades_path` anahtarın NEREYE gideceğini belirler; bu yüzden
        güvenlik sınırının içindedir."""
        exchanges.save_profile(dict(BINANCE_PROFIL,
                                    my_trades_path="/api/v3/myTrades"))
        with pytest.raises(ValueError, match="anahtar yeniden girilmeden"):
            exchanges.update_profile_fields(
                "BINANCE", {"my_trades_path": "/evil/path"})

    def test_dust_log_path_de_korumali(self):
        exchanges.save_profile(dict(BINANCE_PROFIL))
        with pytest.raises(ValueError, match="anahtar yeniden girilmeden"):
            exchanges.update_profile_fields(
                "BINANCE", {"dust_log_path": "/evil/path"})


# =====================================================================
class TestEskiProfilUyumu:

    def test_alan_tasimayan_eski_profil_calismaya_devam_eder(self):
        """Kullanıcının kayıtlı BINANCE profili bu alanlar EKLENMEDEN önce
        yazıldı; yeteneğin kaybolmaması gerekir."""
        eski = {"location": "BINANCE", "family": "binance",
                "base_url": "https://api.binance.com",
                "account_path": "/api/v3/account"}
        assert exchanges.endpoint_path(eski, "my_trades_path") == "/api/v3/myTrades"
        assert exchanges.endpoint_path(eski, "dust_log_path") == \
            "/sapi/v1/asset/dribblet"

    def test_bilinmeyen_borsada_yetenek_uydurulmaz(self):
        yabanci = {"location": "GATEIO", "family": "binance",
                   "base_url": "https://api.gateio.ws",
                   "account_path": "/x"}
        assert exchanges.endpoint_path(yabanci, "my_trades_path") == ""
        assert exchanges.supports(yabanci, "dust_log_path") is False


# =====================================================================
class TestUcNoktalar:

    def test_gelen_kutusu_ucu(self, client, monkeypatch):
        olay = trade_sync.normalize_trade("BINANCE", _trade(950))
        archive.record_exchange_events([olay])
        r = client.get("/api/exchange-trades")
        assert r.status_code == 200
        body = r.json()
        assert body["counts"]["pending"] == 1
        assert body["events"][0]["event_uid"] == olay["event_uid"]
        assert "capabilities" in body

    def test_tarama_ucu_deftere_yazmaz(self, client, monkeypatch):
        import data_manager
        onceki = json.dumps(data_manager.load_portfolio(), sort_keys=True)
        monkeypatch.setattr(trade_sync.trade_sync, "scan",
                            lambda location=None, full=False:
                            {"ok": False, "skipped": "vault_locked",
                             "message": "kasa kilitli"})
        r = client.post("/api/exchange-trades/scan", json={"full": True})
        assert r.status_code == 200
        assert r.json()["skipped"] == "vault_locked"
        assert json.dumps(data_manager.load_portfolio(), sort_keys=True) == onceki

    def test_yok_sayma_ucu(self, client):
        olay = trade_sync.normalize_trade("BINANCE", _trade(951))
        archive.record_exchange_events([olay])
        r = client.post(f"/api/exchange-trades/{olay['event_uid']}/dismiss")
        assert r.status_code == 200
        assert archive.get_exchange_event(
            olay["event_uid"])["status"] == archive.EVENT_DISMISSED

    def test_olmayan_satir_400_doner(self, client):
        r = client.post("/api/exchange-trades/YOK:trade:X:1/apply", json={})
        assert r.status_code == 400

    def test_uygulama_ucu_hatayi_gizlemez(self, client):
        olay = trade_sync.normalize_trade("BINANCE", _trade(952,
                                                            symbol="ARBUSDT"))
        archive.record_exchange_events([olay])
        r = client.post(f"/api/exchange-trades/{olay['event_uid']}/apply",
                        json={"cost_method": "FIFO"})
        assert r.status_code == 400
        assert "açık pozisyon yok" in r.json()["detail"]


# =====================================================================
class TestArayuz:

    def _oku(self, ad):
        yol = os.path.join(APP_DIR, "static", ad)
        return open(yol, encoding="utf-8").read()

    def test_gelen_kutusu_paneli_var(self):
        html = self._oku("index.html")
        assert "BORSA İŞLEMLERİ" in html
        assert "exchangeTrades" in html
        assert "scanExchangeTrades()" in html

    def test_toz_ve_anomali_ayri_etiketlenir(self):
        # Etiketler FAZ F7b'de `app.js` içindeki tek bir eşlemeye taşındı:
        # tür sayısı beşe çıkınca HTML'deki üçlü operatör zinciri hem
        # okunmaz oldu hem de her yeni türde iki yerde güncelleme istiyordu.
        js = self._oku("app.js")
        assert "TOZ DÖNÜŞÜMÜ" in js
        assert "AÇIKLANAMAYAN" in js
        assert "exchangeKindLabel" in self._oku("index.html")

    def test_ilk_tarama_siniri_arayuzde_yaziyor(self):
        """Kullanıcı geçmişin neden gelmediğini kodda aramamalı."""
        html = self._oku("index.html")
        assert "başlangıç noktası" in html
        assert "geçmişi geriye dönük getirmez" in html

    def test_tarayici_diyalogu_kullanilmaz(self):
        js = self._oku("app.js")
        blok = js[js.index("BORSA İŞLEMLERİ (FAZ F7)"):js.index("PİYASA VERİSİ (FAZ M1)")]
        for yasak in ("confirm(", "alert(", "prompt("):
            assert yasak not in blok
        assert "askConfirm" in blok

    def test_islemeden_once_onay_istenir(self):
        js = self._oku("app.js")
        blok = js[js.index("async applyExchangeTrade"):js.index("async dismissExchangeTrade")]
        assert "askConfirm" in blok
        assert blok.index("askConfirm") < blok.index("fetch(")


# =====================================================================
class TestEarnVeParaHareketleri:
    """FAZ F7b. Çıkış noktası yine somut bir olay.

    7 Eylül 2026 gecesi gelen kutusunda `+0.00040177 APT` göründü ve
    "açıklanamayan" diye işaretlendi. Doğruydu — ama Simple Earn her gün
    faiz ödüyor, yani Earn'de duran her varlık her gün böyle bir satır
    üretecekti. Birkaç gün sonra kullanıcı o satırları okumadan kapatmayı
    öğrenir ve açıklanamayan-değişim uyarısı, tam da onu çalışır hâle
    getirmek için uğraştığımız hafta, değerini kaybederdi.

    Aynı şey para giriş/çıkışı için de geçerli. İkisi de bakiyeyi değiştirir,
    ikisi de spot işlem değildir, ikisi de okunmazsa gürültü üretir.
    """

    EARN_CEVABI = {
        "total": 2,
        "rows": [
            {"asset": "APT", "rewards": "0.00040177", "projectId": "APT001",
             "type": "REALTIME", "time": 1757200000000},
            {"asset": "ENA", "rewards": "0.51230000", "projectId": "ENA001",
             "type": "BONUS", "time": 1757200500000},
        ],
    }

    # ------------------------------------------------------- Earn
    def test_earn_cevabi_duz_satirlara_acilir(self):
        satirlar = exchanges.earn_rows(self.EARN_CEVABI)
        apt = next(s for s in satirlar if s["asset"] == "APT")
        assert apt["amount"] == pytest.approx(0.00040177)
        assert apt["time"] == 1757200000000

    def test_vadeli_urunde_miktar_alani_baska_adla_gelir(self):
        """Esnekte `rewards`, vadelide `amount`. Aynı şeyin iki adı olması
        borsanın biçimine ait bir ayrıntıdır ve dışarı sızmamalı."""
        ham = {"rows": [{"asset": "AXS", "amount": "1.25",
                         "positionId": 123, "time": 1757200000000}]}
        satir = exchanges.earn_rows(ham, locked=True)[0]
        assert satir["amount"] == pytest.approx(1.25)
        assert satir["locked"] is True

    def test_earn_bir_gelirdir_karsiligi_yoktur(self):
        satir = exchanges.earn_rows(self.EARN_CEVABI)[0]
        olay = trade_sync.normalize_earn("BINANCE", satir)
        assert olay["kind"] == trade_sync.EARN
        assert olay["side"] == "BUY"
        assert olay["quote_asset"] == ""
        assert olay["quote_qty"] == 0.0
        assert olay["fee_qty"] == 0.0
        # Ödülün KENDİ fiyatı yoktur; fiyat işleme anında belirlenir.
        assert olay["price"] == 0.0

    def test_earn_bakiyeyi_yalnizca_artirir(self):
        satir = exchanges.earn_rows(self.EARN_CEVABI)[0]
        etki = trade_sync.olay_bakiye_etkisi(
            trade_sync.normalize_earn("BINANCE", satir))
        assert etki == {"APT": pytest.approx(0.00040177)}

    def test_earn_apt_vakasini_aciklar(self, servis, kasa_acik, monkeypatch):
        """Asıl vaka: o +0.00040177 APT artık anomali DEĞİL."""
        monkeypatch.setattr(archive, "get_balance_state",
                            lambda ex: {"APT": 44.43896519})
        monkeypatch.setattr(archive, "get_balance_state_ts", lambda ex: 1757100000.0)
        monkeypatch.setattr(exchanges, "read_exchange",
                            lambda k, p=None: _bakiye_okumasi({"APT": 44.43936696}))
        monkeypatch.setattr(exchanges, "fetch_my_trades", lambda *a, **k: [])
        _akislari_sustur(monkeypatch, fetch_earn_rewards=(
            lambda p, locked=False, **k: ([] if locked
                                          else exchanges.earn_rows(self.EARN_CEVABI))))
        archive.set_sync_cursor("BINANCE", trade_sync.EARN_ESNEK_KAPSAMI, cursor=1)

        rapor = servis._borsayi_tara("BINANCE", dict(BINANCE_PROFIL), full=True)
        assert rapor["unexplained"] == []

    def test_mexc_earn_ucu_sunmuyor_ve_bu_gizlenmez(self):
        mexc = exchanges.BUILTIN_PROFILES["MEXC"]
        assert exchanges.supports(mexc, "earn_flexible_path") is False
        assert exchanges.supports(mexc, "earn_locked_path") is False
        with pytest.raises(exchanges.ExchangeError, match="Earn"):
            exchanges.fetch_earn_rewards(mexc)

    def test_earn_sayfa_boyu_acikca_gonderilir(self, monkeypatch):
        """Uç varsayılanı 10'dur. Belirtmezsek 11. ödül sessizce kaybolur ve
        sistem "başka ödül yok" sanır."""
        yakalanan = {}

        def sahte(profil, yol, anahtar, gizli, params):
            yakalanan.update(params)
            return {"rows": []}

        monkeypatch.setattr(exchanges, "signed_get", sahte)
        monkeypatch.setattr(exchanges, "_anahtarlar", lambda *a, **k: ("k", "s"))
        exchanges.fetch_earn_rewards(dict(BINANCE_PROFIL))
        assert yakalanan["size"] == exchanges.EARN_SAYFA_BOYU
        assert yakalanan["size"] > 10

    # ------------------------------------------- Para giriş/çıkışı
    def test_bekleyen_yatirma_olay_uretmez(self):
        """Bekleyen bir yatırma henüz bakiyede değildir; onu saymak olmayan
        bir parayla bir farkı açıklamak olurdu."""
        with pytest.raises(ValueError, match="bakiyeye geçmemiş"):
            trade_sync.normalize_deposit("BINANCE", {
                "coin": "USDT", "amount": "100", "status": 0,
                "insertTime": 1757200000000, "id": "d1"})

    def test_gerceklesmis_yatirma_bakiyeyi_artirir(self):
        olay = trade_sync.normalize_deposit("BINANCE", {
            "coin": "USDT", "amount": "100", "status": 1,
            "insertTime": 1757200000000, "id": "d2"})
        assert trade_sync.olay_bakiye_etkisi(olay) == {"USDT": pytest.approx(100.0)}

    def test_cekmede_ag_komisyonu_da_bakiyeden_cikar(self):
        """İki ayrı tutar var. Yalnızca `amount` sayılırsa komisyon kadar bir
        fark her seferinde "açıklanamayan" olarak kalırdı."""
        olay = trade_sync.normalize_withdraw("BINANCE", {
            "coin": "ETH", "amount": "1.0", "transactionFee": "0.003",
            "status": 6, "applyTime": "2026-09-07 12:00:00", "id": "w1"})
        assert trade_sync.olay_bakiye_etkisi(olay) == {"ETH": pytest.approx(-1.003)}

    def test_iade_edilmis_cekme_olay_uretmez(self):
        for durum in (1, 3, 5):
            with pytest.raises(ValueError, match="iade"):
                trade_sync.normalize_withdraw("BINANCE", {
                    "coin": "ETH", "amount": "1.0", "transactionFee": "0.003",
                    "status": durum, "applyTime": "2026-09-07 12:00:00"})

    def test_tamamlanmamis_cekme_de_sayilir(self):
        """Binance bakiyeyi TALEP ANINDA düşer. "Tamamlandı mı" ölçütüyle
        beklemek, işleme alınmış bir çekmeyi görünmez yapardı."""
        olay = trade_sync.normalize_withdraw("BINANCE", {
            "coin": "ETH", "amount": "1.0", "transactionFee": "0.003",
            "status": 4, "applyTime": "2026-09-07 12:00:00", "id": "w2"})
        assert olay["kind"] == trade_sync.WITHDRAW

    def test_metin_bicimli_zaman_okunur(self):
        """`applyTime` bir sayı değil "2026-09-07 12:00:00" metnidir. İki
        biçimi de kabul etmezsek akışın yarısı sessizce okunamaz."""
        assert exchanges._zaman_ms(1757200000000) == 1757200000000
        assert exchanges._zaman_ms("2026-09-07 12:00:00") > 0
        assert exchanges._zaman_ms("bozuk") == 0
        assert exchanges._zaman_ms(None) == 0

    # ------------------------------------------------- Deftere işleme
    def test_para_girisi_deftere_islenemez(self):
        """Girişi "alım" saymak, maliyeti bilinmeyen bir lot uydurmaktır ve
        maliyet tabanını sessizce bozar."""
        olay = trade_sync.normalize_deposit("BINANCE", {
            "coin": "APT", "amount": "5", "status": 1,
            "insertTime": 1757200000000, "id": "d3"})
        archive.record_exchange_events([olay])
        servis = TradeSyncService()
        with pytest.raises(ValueError, match="Transfer"):
            servis.apply_event(olay["event_uid"])

    def test_para_cikisi_deftere_islenemez(self):
        olay = trade_sync.normalize_withdraw("BINANCE", {
            "coin": "APT", "amount": "5", "transactionFee": "0.1",
            "status": 6, "applyTime": "2026-09-07 12:00:00", "id": "w3"})
        archive.record_exchange_events([olay])
        servis = TradeSyncService()
        with pytest.raises(ValueError, match="Transfer|Zarar Yaz"):
            servis.apply_event(olay["event_uid"])

    def test_earn_alindigi_gunun_fiyatiyla_islenir(self, servis, monkeypatch):
        """Kullanıcının kararı (8 Eylül 2026): gelir, elde edildiği andaki
        değeriyle maliyet tabanına döner."""
        import price_service
        monkeypatch.setattr(price_service.price_service, "gunluk_kapanis",
                            lambda sembol, tarih: 8.25)

        satir = exchanges.earn_rows(self.EARN_CEVABI)[0]
        olay = trade_sync.normalize_earn("BINANCE", satir)
        archive.record_exchange_events([olay])
        sonuc = servis.apply_event(olay["event_uid"])
        assert sonuc["success"] is True

        from data_manager import load_portfolio
        kayit = [t for t in load_portfolio()["transactions"]
                 if t.get("source_ref") == olay["event_uid"]][0]
        assert kayit["status"] == "Aktif"
        assert kayit["cost"] == pytest.approx(8.25)
        assert kayit["qty"] == pytest.approx(0.00040177)
        assert "Earn geliri" in kayit["notes"]

    def test_bugunun_odulu_canli_fiyatla_islenir(self, servis, monkeypatch):
        """Bugünün ödülü için canlı fiyat zaten o günün fiyatıdır; ağa ikinci
        kez çıkılmamalı. Fiyat anahtarı `APTUSDT` biçiminde gelir."""
        import price_service
        monkeypatch.setattr(
            price_service.price_service, "gunluk_kapanis",
            lambda s, t: pytest.fail("bugünün ödülü için ağa çıkılmamalı"))

        from datetime import datetime as dt
        simdi_ms = int(dt.now().timestamp() * 1000)
        olay = trade_sync.normalize_earn("BINANCE", {
            "asset": "APT", "amount": 0.5, "time": simdi_ms, "ref": "x"})
        archive.record_exchange_events([olay])
        servis.apply_event(olay["event_uid"],
                           live_prices={"APTUSDT": {"price": 9.10}})

        from data_manager import load_portfolio
        kayit = [t for t in load_portfolio()["transactions"]
                 if t.get("source_ref") == olay["event_uid"]][0]
        assert kayit["cost"] == pytest.approx(9.10)

    def test_fiyat_bulunamazsa_earn_reddedilir(self, servis, monkeypatch):
        """Uydurma bir fiyatla yazmak, yanlış bir sayıyı doğru gibi deftere
        koymak olurdu. Maliyet tabanı vergi sonucu doğurur."""
        import price_service
        monkeypatch.setattr(price_service.price_service, "gunluk_kapanis",
                            lambda sembol, tarih: None)

        satir = exchanges.earn_rows(self.EARN_CEVABI)[0]
        olay = trade_sync.normalize_earn("BINANCE", satir)
        archive.record_exchange_events([olay])
        with pytest.raises(ValueError, match="fiyat"):
            servis.apply_event(olay["event_uid"], live_prices={})

    # ------------------------------------------------------- Genel
    def test_akis_hatasi_fotografin_tamamini_dondurur(self, servis):
        """Hesap düzeyindeki akışlar hangi varlığı etkilediklerini söylemez;
        biri okunamadıysa hiçbir varlık için "değişimi gördüm" diyemeyiz."""
        for kapsam in trade_sync.HESAP_KAPSAMLARI:
            yazilacak = servis._yazilacak_bakiye(
                {"APT": 1.0}, {"APT": 2.0},
                [{"scope": kapsam, "error": "HTTP 500"}], False)
            assert yazilacak == {"APT": 1.0}, kapsam

    def test_yeni_turler_farki_aciklayabilir(self):
        """Açıklayıcı türler listesi eksik kalırsa yeni akışlar okunur ama
        anomali hesabında sayılmaz — yani gürültü yine sürerdi."""
        for tur in (trade_sync.TRADE, trade_sync.DUST, trade_sync.EARN,
                    trade_sync.DEPOSIT, trade_sync.WITHDRAW):
            assert tur in trade_sync.ACIKLAYICI_TURLER
        assert trade_sync.UNEXPLAINED not in trade_sync.ACIKLAYICI_TURLER

    def test_yeni_uclar_korumali_alanlardir(self):
        """Bu alanlar API anahtarının NEREYE gönderileceğini belirler."""
        for alan in ("earn_flexible_path", "earn_locked_path",
                     "deposit_path", "withdraw_path"):
            with pytest.raises(ValueError):
                exchanges.update_profile_fields("BINANCE",
                                                {alan: "https://kotu.example"})

    def test_arayuz_yeni_turleri_etiketler(self):
        js = open(os.path.join(APP_DIR, "static", "app.js"),
                  encoding="utf-8").read()
        for etiket in ("EARN GELİRİ", "PARA GİRİŞİ", "PARA ÇIKIŞI"):
            assert etiket in js


# =====================================================================
class TestKasaErisimi:
    """Kullanıcı kendi uygulamasında kasayı bulamadı.

    Kasa kartı "Canlı Grafikler & Isı Haritası → Canlı Bağlantılar"
    bölümünün dibinde duruyor. Taramanın çalışmamasının en sık sebebi
    kilitli kasa olduğuna göre, kilidi açmak işin YAPILDIĞI yerden
    erişilebilir olmalı. Kartı taşımıyoruz; erişimi getiriyoruz.
    """

    def _oku(self, ad):
        yol = os.path.join(APP_DIR, "static", ad)
        return open(yol, encoding="utf-8").read()

    def test_hata_metni_olmayan_bir_menu_yolu_tarif_etmez(self):
        """Eski metin "Anahtar Kasası → PIN → Kasayı Aç" diyordu ve kullanıcı
        öyle bir menü aradı. Öyle bir menü yok."""
        kaynak = open(os.path.join(APP_DIR, "trade_sync.py"),
                      encoding="utf-8").read()
        blok = kaynak[kaynak.index("vault_locked"):]
        blok = blok[:blok.index("borsalar = []")]
        assert "Anahtar Kasası →" not in blok
        assert "PIN" in blok

    def test_kutu_kilitliyken_pin_sorar(self):
        html = self._oku("index.html")
        assert "unlockVaultAndScan()" in html
        assert "Kasayı Aç ve Tara" in html

    def test_kilitliyken_kutu_kendiliginden_acilir(self):
        """Kapalı bir kutunun içindeki PIN kutusu görünmez; kilitliyken
        kutunun açık gelmesi bu düzeltmenin çalışması için şart."""
        js = self._oku("app.js")
        blok = js[js.index("get exchangeInboxVisible"):
                  js.index("goToVault()")]
        assert "vaultStatus" in blok
        assert "unlocked" in blok

    def test_kilitliyken_bekleyen_yok_yazilmaz(self):
        """"Bakamadım" ile "işlem yok" ayrı iddialardır."""
        html = self._oku("index.html")
        assert "kasa kilitli" in html
        blok = html[html.index("BORSA İŞLEMLERİ</span>"):]
        blok = blok[:blok.index("Şimdi tara")]
        # Yorum metnini değil, ROZETİN KENDİSİNİ arıyoruz.
        nerede = blok.index(">bekleyen yok<")
        satir = blok[max(0, nerede - 400):nerede]
        assert "vaultStatus" in satir

    def test_ust_barda_kasa_gostergesi_var(self):
        html = self._oku("index.html")
        assert "goToVault()" in html
        assert 'id="anahtar-kasasi"' in html

    def test_kasa_durumu_gelen_kutusu_yanitiyla_gelir(self):
        """Kullanıcı kasanın kilitli olduğunu görmek için başka bir sekmeye
        gitmek zorunda kalmamalı."""
        kaynak = open(os.path.join(APP_DIR, "main.py"), encoding="utf-8").read()
        blok = kaynak[kaynak.index('@app.get("/api/exchange-trades")'):]
        blok = blok[:blok.index('@app.post("/api/exchange-trades/scan")')]
        assert "keyvault.status()" in blok

    def test_kasa_durumu_sir_tasimaz(self):
        """Gösterge yalnızca durum bilgisidir; PIN veya anahtar taşımaz."""
        import keyvault
        durum = keyvault.status()
        for anahtar in durum:
            assert anahtar in ("available", "pin_enabled", "sealed",
                               "unlocked", "entry_count")


# =====================================================================
# FAZ F7f — Soft Staking akışı
# =====================================================================
class TestSoftStakingAkisi:
    """Simple Earn'ün ödül uçları Soft Staking'i göstermiyor.

    Gerçek hesapta ikisi de hatasız çalışıp sıfır satır döndürürken bir APT
    ödülü bakiyeye geçmişti; sistem onu yalnızca "açıklanamayan artış" olarak
    görebiliyordu. Yakalamak ile ADINI KOYMAK farklı şeyler: adı konmayan bir
    gelir deftere işlenemez.
    """

    def _satir(self, **ustler):
        satir = {"asset": "APT", "amount": 0.00040177, "time": 1757200000000,
                 "product": "soft", "ref": "APT", "staked_asset": "APT"}
        satir.update(ustler)
        return satir

    def test_odul_earn_olayina_donusur(self):
        olay = trade_sync.normalize_earn("BINANCE", self._satir())
        assert olay["kind"] == trade_sync.EARN
        assert olay["base_asset"] == "APT"
        assert olay["qty"] == pytest.approx(0.00040177)

    def test_kimlik_uc_urunu_ayirir(self):
        """Aynı varlık ve aynı milisaniye: ürün ayrımı olmasaydı üç ayrı
        ödül tek olay sanılır, ikisi sessizce kaybolurdu."""
        ortak = {"asset": "APT", "amount": 1.0, "time": 1757200000000}
        kimlikler = {
            trade_sync.normalize_earn("BINANCE", dict(ortak, product="soft"))["event_uid"],
            trade_sync.normalize_earn("BINANCE", dict(ortak, product="flex"))["event_uid"],
            trade_sync.normalize_earn("BINANCE", dict(ortak, locked=True))["event_uid"],
        }
        assert len(kimlikler) == 3

    def test_eski_locked_bayragi_hala_calisir(self):
        """Kimlik biçimi değişirse daha önce işlenmiş bir ödül ikinci kez
        "yeni" görünürdü."""
        eski = trade_sync.normalize_earn(
            "BINANCE", {"asset": "APT", "amount": 1.0,
                        "time": 1757200000000, "locked": True})
        assert ":locked:" in eski["event_uid"]

    def test_kapsam_hesap_akislarinda(self):
        assert trade_sync.SOFT_STAKING_KAPSAMI in trade_sync.HESAP_KAPSAMLARI

    def test_akis_taramada_okunur(self, monkeypatch, kayitli_portfoy):
        _akislari_sustur(
            monkeypatch,
            fetch_soft_staking_rewards=lambda *a, **k: [self._satir()])
        monkeypatch.setattr(exchanges, "fetch_my_trades", lambda *a, **k: [])
        monkeypatch.setattr(
            exchanges, "read_exchange",
            lambda konum, profil: {"balances": [{"asset": "APT", "qty": 12.0}]})

        servis = trade_sync.TradeSyncService()
        archive.set_sync_cursor("BINANCE", trade_sync.SOFT_STAKING_KAPSAMI,
                                cursor=1)
        sonuc = servis._akisi_cek("BINANCE", dict(BINANCE_PROFIL),
                                  trade_sync.SOFT_STAKING_KAPSAMI)
        assert sonuc["supported"] is True
        assert [o["base_asset"] for o in sonuc["events"]] == ["APT"]

    def test_ilk_tarama_yalnizca_temel_kurar(self, monkeypatch, kayitli_portfoy):
        """Geçmiş ödülleri gelen kutusuna boca etmek uyarıyı değersizleştirir."""
        _akislari_sustur(
            monkeypatch,
            fetch_soft_staking_rewards=lambda *a, **k: [self._satir()])
        servis = trade_sync.TradeSyncService()
        sonuc = servis._akisi_cek("BINANCE", dict(BINANCE_PROFIL),
                                  trade_sync.SOFT_STAKING_KAPSAMI)
        assert sonuc["events"] == [] and sonuc["baseline"] is True

    def test_desteklenmeyen_borsada_sessizce_atlanir(self, monkeypatch,
                                                     kayitli_portfoy):
        _akislari_sustur(monkeypatch)
        servis = trade_sync.TradeSyncService()
        mexc = dict(exchanges.BUILTIN_PROFILES["MEXC"])
        sonuc = servis._akisi_cek("MEXC", mexc,
                                  trade_sync.SOFT_STAKING_KAPSAMI)
        assert sonuc["supported"] is False and sonuc["events"] == []


# =====================================================================
# Yakalanan alımın nakit ayağı
# =====================================================================
class TestYakalananAlimNakdiDuser:
    """Satışlar nakdi her zaman artırıyordu ama alımlar hiç azaltmıyordu.

    Toplam kasa `pozisyon değeri + nakit` olarak hesaplandığı için bu, aynı
    parayı İKİ KEZ saydırıyordu: alınan coin pozisyon olarak duruyor, onu
    alan para da hâlâ nakit olarak duruyordu. 9 Eylül'deki tek bir ARB alımı
    ekrandaki toplam varlığı 13.79 dolar şişirdi.
    """

    def _defter(self, nakit=1000.0):
        defter = data_manager.load_portfolio()
        defter["transactions"] = []
        defter["wallets"] = {
            "usdt_cash": nakit,
            "exchange_cash": {"BINANCE": nakit, "MEXC": 0.0},
            "futures_balance": 0.0, "margin_balance": 0.0,
        }
        data_manager.save_portfolio(defter)
        return defter

    def _alim(self, **ustler):
        olay = {
            "event_uid": "BINANCE:trade:ARBUSDT:1", "exchange": "BINANCE",
            "kind": trade_sync.TRADE, "symbol": "ARBUSDT",
            "base_asset": "ARB", "quote_asset": "USDT", "side": "BUY",
            "qty": 91.3, "price": 0.151, "quote_qty": 13.7863,
            "fee_asset": "BNB", "fee_qty": 1.399e-05,
            "trade_at": "2026-09-09T19:53:19", "trade_ts": 1789000000.0,
        }
        olay.update(ustler)
        return olay

    def _isle(self, olay, konum="BINANCE", sembol="ARBUSDT", miktar=91.3,
              birim=0.151):
        servis = trade_sync.TradeSyncService()
        return servis._alimi_isle(
            olay, konum, sembol, miktar, birim, "2026-09-09",
            data_manager.load_portfolio, data_manager.save_portfolio,
            data_manager.DEFAULT_CATEGORIES)

    def test_alim_nakdi_azaltir(self):
        self._defter(1000.0)
        self._isle(self._alim())
        c = data_manager.load_portfolio()["wallets"]
        assert c["exchange_cash"]["BINANCE"] == pytest.approx(1000.0 - 13.7863)

    def test_toplam_nakit_de_guncellenir(self):
        self._defter(1000.0)
        self._isle(self._alim())
        c = data_manager.load_portfolio()["wallets"]
        assert c["usdt_cash"] == pytest.approx(sum(c["exchange_cash"].values()))

    def test_ayni_varliktan_komisyon_da_dusulur(self):
        """Komisyon USDT ile ödendiyse hesaptan o kadar daha çıkmıştır."""
        self._defter(1000.0)
        self._isle(self._alim(fee_asset="USDT", fee_qty=0.0138))
        c = data_manager.load_portfolio()["wallets"]
        assert c["exchange_cash"]["BINANCE"] == pytest.approx(
            1000.0 - 13.7863 - 0.0138)

    def test_bnb_komisyonu_nakde_dokunmaz(self):
        """BNB ile ödenen komisyon USDT bakiyesini değiştirmez."""
        self._defter(1000.0)
        self._isle(self._alim())          # fee_asset BNB
        c = data_manager.load_portfolio()["wallets"]
        assert c["exchange_cash"]["BINANCE"] == pytest.approx(1000.0 - 13.7863)

    def test_nakit_olmayan_kotasyonda_nakde_dokunulmaz(self):
        """BTC ile alınan bir altcoinde çıkan şey nakit değil BTC'dir."""
        self._defter(1000.0)
        self._isle(self._alim(symbol="ARBBTC", quote_asset="BTC",
                              quote_qty=0.0002))
        c = data_manager.load_portfolio()["wallets"]
        assert c["exchange_cash"]["BINANCE"] == pytest.approx(1000.0)

    def test_earn_geliri_nakdi_azaltmaz(self):
        """Karşılıksız gelen varlık için para verilmedi."""
        self._defter(1000.0)
        self._isle(self._alim(kind=trade_sync.EARN, quote_asset="",
                              quote_qty=0.0, symbol="APT"),
                   sembol="APTUSDT", miktar=0.0004, birim=0.649)
        c = data_manager.load_portfolio()["wallets"]
        assert c["exchange_cash"]["BINANCE"] == pytest.approx(1000.0)

    def test_dogru_konumun_nakdi_azalir(self):
        """Konum artık olduğu gibi kullanılır; MEXC alımını Binance'ten
        düşmek nakit dağılımını sessizce bozardı."""
        defter = self._defter(1000.0)
        defter["wallets"]["exchange_cash"]["MEXC"] = 500.0
        data_manager.save_portfolio(defter)
        self._isle(self._alim(exchange="MEXC"), konum="MEXC")
        c = data_manager.load_portfolio()["wallets"]["exchange_cash"]
        assert c["MEXC"] == pytest.approx(500.0 - 13.7863)
        assert c["BINANCE"] == pytest.approx(1000.0)

    def test_nakit_yetmezse_sifira_kirpilir_ve_soylenir(self):
        """Eksiye düşmek imkânsız; oraya varıyorsak defterdeki nakit ZATEN
        yanlıştı. Sessiz kırpma bunu düzeltilmiş gibi gösterirdi."""
        self._defter(5.0)
        sonuc = self._isle(self._alim())
        c = data_manager.load_portfolio()["wallets"]
        assert c["exchange_cash"]["BINANCE"] == pytest.approx(0.0)
        assert "UYARI" in sonuc["transaction"]["notes"]
        assert "yetmedi" in sonuc["transaction"]["notes"]

    def test_gercek_senaryo_defter_borsayla_ortusur(self):
        """9 Eylül: defter 1220.31 + 27.60414 satış = 1247.91414 diyordu,
        borsa ise alımı da düşerek 1234.150306 diyordu."""
        self._defter(1247.91414)
        self._isle(self._alim())
        c = data_manager.load_portfolio()["wallets"]
        assert c["exchange_cash"]["BINANCE"] == pytest.approx(
            1247.91414 - 13.7863, abs=1e-6)
