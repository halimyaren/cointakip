r"""
CoinTakip — FAZ F6b Testleri: Borsa API Bağlantıları

En kritik güvenceler:

1. **Yazma yetkili anahtar SAKLANMAZ.** İzin denetimi saklamadan ÖNCE yapılır;
   reddedilen bir anahtar kasaya hiç girmez. Tersi olsaydı reddedilen anahtar
   bir süre diskte durmuş olurdu.

2. **Doğrulayamadığımız şeyi doğrulanmış saymayız.** Bir borsa anahtar
   yetkilerini bildirmiyorsa hesap düzeyindeki `canTrade` alanına BAKILMAZ —
   o anahtarın değil hesabın yetkisidir. Kullanıcıdan açık onay istenir.

3. **Yalnızca GET.** Bu modülün ağa çıkan tek yolu `signed_get`'tir ve emir
   verme veya para çekme çağrısı yoktur.

4. **Anahtar düz metin diske yazılmaz.** `settings.json` içinde yalnızca sır
   olmayan profil alanları durur.

5. **Kasa kilitli** ile **anahtar yok** ayrı raporlanır; ikisi ayrı sorundur ve
   ayrı çözümleri vardır.

Testler ağa ÇIKMAZ: tüm HTTP çağrıları taklit edilir.
"""

import hashlib
import hmac
import json

import pytest

import connections as cx
import data_manager as dm
import exchanges as ex
import keyvault as kv


@pytest.fixture(autouse=True)
def kasa_kilitli():
    kv.lock()
    yield
    kv.lock()
    ex._ZAMAN_FARKI.clear()


def _kasa_ac(pin="1234"):
    dm.set_pin(pin)
    kv.unlock(pin)


BINANCE = dict(ex.BUILTIN_PROFILES["BINANCE"])
MEXC = dict(ex.BUILTIN_PROFILES["MEXC"])


def _hesap_cevabi(bakiyeler=None):
    return {"canTrade": True, "canWithdraw": True,        # HESABIN yetkisi
            "balances": bakiyeler if bakiyeler is not None else [
                {"asset": "BTC", "free": "0.5", "locked": "0.1"},
                {"asset": "USDT", "free": "100.0", "locked": "0"},
                {"asset": "DUST", "free": "0", "locked": "0"},
            ]}


def _sahte_http(monkeypatch, eslem):
    """URL'nin içerdiği yola göre cevap döndüren sahte GET. Çağrıları kaydeder."""
    cagrilar = []

    def sahte(url, headers=None):
        cagrilar.append({"url": url, "headers": headers or {}})
        for parca, cevap in eslem.items():
            if parca in url:
                if isinstance(cevap, Exception):
                    raise cevap
                return cevap
        raise ex.ExchangeError(f"beklenmeyen url: {url}")

    monkeypatch.setattr(ex, "_http_get", sahte)
    return cagrilar


# =====================================================================
# 1) İMZALAMA
# =====================================================================
class TestImzalama:

    def test_binance_imzasi_bilinen_degerle_uyusur(self):
        """İmza bozuksa her istek reddedilir; bunu tahmine bırakmıyoruz."""
        beklenen = hmac.new(b"gizli", b"a=1&b=2", hashlib.sha256).hexdigest()
        assert ex._imzala_binance("gizli", "a=1&b=2") == beklenen

    def test_imza_sorgunun_sonuna_eklenir(self, monkeypatch):
        """
        Sıra önemli: imza, imzalanan dizinin SONUNA eklenmelidir. Araya
        girerse borsa farklı bir diziyi doğrular ve istek reddedilir.
        """
        cagrilar = _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.signed_get(BINANCE, "/api/v3/account", "ANAHTAR", "GIZLI")
        url = cagrilar[0]["url"]
        sorgu = url.split("?", 1)[1]
        imzasiz, imza = sorgu.rsplit("&signature=", 1)
        assert imza == ex._imzala_binance("GIZLI", imzasiz)

    def test_anahtar_baslikta_gider(self, monkeypatch):
        cagrilar = _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.signed_get(BINANCE, "/api/v3/account", "ANAHTAR", "GIZLI")
        assert cagrilar[0]["headers"]["X-MBX-APIKEY"] == "ANAHTAR"

    def test_gizli_anahtar_url_de_gecmez(self, monkeypatch):
        """Sır asla adres satırına yazılmaz; loglara ve geçmişe düşerdi."""
        cagrilar = _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.signed_get(BINANCE, "/api/v3/account", "ANAHTAR", "COKGIZLI")
        assert "COKGIZLI" not in cagrilar[0]["url"]

    def test_anahtarsiz_istek_reddedilir(self):
        with pytest.raises(ex.ExchangeError):
            ex.signed_get(BINANCE, "/api/v3/account", "", "")

    def test_sunucu_saati_farki_uygulanir(self, monkeypatch):
        """
        Borsa kendi saatinden çok sapan isteği reddeder. Kullanıcının
        makinesindeki birkaç saniyelik kayma tüm okumaları düşürürdü.
        """
        _sahte_http(monkeypatch, {"/api/v3/time": {"serverTime": 10 ** 13},
                                  "/api/v3/account": _hesap_cevabi()})
        fark = ex.server_time_offset(BINANCE, yenile=True)
        assert fark != 0


# =====================================================================
# 2) PROFİL DOĞRULAMA
# =====================================================================
class TestProfilDogrulama:

    def test_hazir_profiller_gecerli(self):
        for hazir in ex.builtin_profiles():
            temiz, hata = ex.validate_profile(hazir)
            assert hata is None, hazir["location"]
            assert temiz["location"] == hazir["location"]

    def test_zorunlu_alan_eksikse_reddedilir(self):
        _, hata = ex.validate_profile({"location": "X", "family": "binance"})
        assert hata and "base_url" in hata

    def test_bilinmeyen_aile_reddedilir(self):
        _, hata = ex.validate_profile({**BINANCE, "family": "sihirli"})
        assert hata and "aile" in hata.lower()

    def test_http_reddedilir(self):
        """Anahtar bu bağlantıdan geçiyor; şifresiz taşımak kabul edilemez."""
        _, hata = ex.validate_profile({**BINANCE, "base_url": "http://api.x.com"})
        assert hata and "https" in hata.lower()

    def test_yollar_normallestirilir(self):
        temiz, hata = ex.validate_profile({**BINANCE, "account_path": "api/v3/account",
                                           "base_url": "https://api.x.com/"})
        assert hata is None
        assert temiz["account_path"] == "/api/v3/account"
        assert temiz["base_url"] == "https://api.x.com"

    def test_konum_buyuk_harfe_cevrilir(self):
        temiz, _ = ex.validate_profile({**BINANCE, "location": "binance"})
        assert temiz["location"] == "BINANCE"


# =====================================================================
# 3) İZİN DENETİMİ — FAZIN ASIL GÜVENCESİ
# =====================================================================
class TestIzinDenetimi:

    def test_salt_okunur_anahtar_kabul_edilir(self, monkeypatch):
        _sahte_http(monkeypatch, {"apiRestrictions": {
            "enableReading": True, "enableWithdrawals": False,
            "enableSpotAndMarginTrading": False, "ipRestrict": True}})
        izin = ex.check_permissions(BINANCE, "K", "S")
        assert izin["status"] == ex.PERM_READONLY
        assert izin["ip_restricted"] is True

    def test_para_cekme_yetkisi_yazma_sayilir(self, monkeypatch):
        _sahte_http(monkeypatch, {"apiRestrictions": {
            "enableReading": True, "enableWithdrawals": True,
            "enableSpotAndMarginTrading": False}})
        izin = ex.check_permissions(BINANCE, "K", "S")
        assert izin["status"] == ex.PERM_WRITE
        assert "para çekme" in izin["detail"]

    def test_emir_verme_yetkisi_yazma_sayilir(self, monkeypatch):
        _sahte_http(monkeypatch, {"apiRestrictions": {
            "enableReading": True, "enableWithdrawals": False,
            "enableSpotAndMarginTrading": True}})
        assert ex.check_permissions(BINANCE, "K", "S")["status"] == ex.PERM_WRITE

    def test_data_ile_sarili_cevap_da_okunur(self, monkeypatch):
        _sahte_http(monkeypatch, {"apiRestrictions": {"data": {
            "enableReading": True, "enableWithdrawals": False,
            "enableSpotAndMarginTrading": False}}})
        assert ex.check_permissions(BINANCE, "K", "S")["status"] == ex.PERM_READONLY

    def test_yetki_ucu_yoksa_dogrulanamaz_denir(self, monkeypatch):
        """
        MEXC'in durumu. Hesap düzeyindeki `canTrade` alanına BAKILMAZ: o
        anahtarın değil hesabın yetkisidir ve onu anahtar yetkisi saymak
        kullanıcıya veremeyeceğimiz bir güvence vermek olurdu.
        """
        cagrilar = _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        izin = ex.check_permissions(MEXC, "K", "S")
        assert izin["status"] == ex.PERM_UNKNOWN
        assert izin["can_trade"] is None
        assert cagrilar == []                 # hiç istek atılmadı
        assert "DOĞRULAYAMIYORUZ" in izin["detail"]


# =====================================================================
# 4) SAKLAMA — ÖNCE DENETLE, SONRA YAZ
# =====================================================================
class TestAnahtarSaklama:

    def test_yazma_yetkili_anahtar_kasaya_HIC_girmez(self, monkeypatch):
        _kasa_ac()
        _sahte_http(monkeypatch, {"apiRestrictions": {
            "enableReading": True, "enableWithdrawals": True,
            "enableSpotAndMarginTrading": False}})
        with pytest.raises(ex.WriteCapableKey):
            ex.save_credentials(BINANCE, "ANAHTAR", "GIZLI")
        # Fazın asıl güvencesi: reddedilen anahtar kasada iz bırakmadı.
        assert not kv.has(ex.key_name("BINANCE"))
        assert not kv.has(ex.secret_name("BINANCE"))
        assert "BINANCE" not in ex.list_profiles()

    def test_salt_okunur_anahtar_kasaya_yazilir(self, monkeypatch):
        _kasa_ac()
        _sahte_http(monkeypatch, {"apiRestrictions": {
            "enableReading": True, "enableWithdrawals": False,
            "enableSpotAndMarginTrading": False}})
        sonuc = ex.save_credentials(BINANCE, "ANAHTAR", "GIZLI")
        assert sonuc["permission"]["status"] == ex.PERM_READONLY
        assert kv.get(ex.key_name("BINANCE")) == "ANAHTAR"
        assert kv.get(ex.secret_name("BINANCE")) == "GIZLI"
        assert "BINANCE" in ex.list_profiles()

    def test_anahtar_settings_json_a_duz_metin_yazilmaz(self, monkeypatch):
        """Profil sır olmayan alanları taşır; sır yalnızca şifreli kasadadır."""
        _kasa_ac()
        _sahte_http(monkeypatch, {"apiRestrictions": {
            "enableReading": True, "enableWithdrawals": False,
            "enableSpotAndMarginTrading": False}})
        ex.save_credentials(BINANCE, "COK-GIZLI-ANAHTAR", "COK-GIZLI-SIR")
        ham = json.dumps(dm.load_settings(), ensure_ascii=False)
        assert "COK-GIZLI-ANAHTAR" not in ham
        assert "COK-GIZLI-SIR" not in ham

    def test_dogrulanamayan_izin_onaysiz_kaydedilmez(self):
        _kasa_ac()
        with pytest.raises(ex.ExchangeError):
            ex.save_credentials(MEXC, "ANAHTAR", "GIZLI")
        assert not kv.has(ex.key_name("MEXC"))

    def test_dogrulanamayan_izin_acik_onayla_kaydedilir(self):
        _kasa_ac()
        sonuc = ex.save_credentials(MEXC, "ANAHTAR", "GIZLI",
                                    acknowledge_unverified=True)
        assert sonuc["permission"]["status"] == ex.PERM_UNKNOWN
        assert kv.get(ex.key_name("MEXC")) == "ANAHTAR"
        # Durum profile yazılıyor ki arayüz rozeti gösterebilsin.
        assert ex.list_profiles()["MEXC"]["permission_status"] == ex.PERM_UNKNOWN

    def test_bos_anahtar_reddedilir(self):
        _kasa_ac()
        with pytest.raises(ValueError):
            ex.save_credentials(MEXC, "", "GIZLI", acknowledge_unverified=True)

    def test_profil_silinince_anahtar_da_unutulur(self):
        """
        "Sildim" dediği bir sırrın diskte şifreli olarak durmaya devam etmesi
        kullanıcıyı yanıltırdı.
        """
        _kasa_ac()
        ex.save_credentials(MEXC, "ANAHTAR", "GIZLI", acknowledge_unverified=True)
        assert ex.delete_profile("MEXC") is True
        assert not kv.has(ex.key_name("MEXC"))
        assert not kv.has(ex.secret_name("MEXC"))

    def test_olmayan_profil_silinemez(self):
        assert ex.delete_profile("YOK") is False


# =====================================================================
# 5) BAKİYE OKUMA
# =====================================================================
class TestBakiyeOkuma:

    def _hazirla(self, monkeypatch, cevap=None):
        _kasa_ac()
        ex.save_credentials(MEXC, "ANAHTAR", "GIZLI", acknowledge_unverified=True)
        _sahte_http(monkeypatch, {"/api/v3/account": cevap or _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)

    def test_serbest_ve_kilitli_toplanir(self, monkeypatch):
        """Emirde bekleyen bakiye de sizindir; yok saymak varlığı eksik gösterir."""
        self._hazirla(monkeypatch)
        okuma = ex.read_exchange("MEXC")
        btc = next(b for b in okuma["balances"] if b["asset"] == "BTC")
        assert btc["qty"] == pytest.approx(0.6)
        assert btc["free"] == pytest.approx(0.5)
        assert btc["locked"] == pytest.approx(0.1)

    def test_sifir_bakiye_listeye_girmez(self, monkeypatch):
        self._hazirla(monkeypatch)
        assert all(b["asset"] != "DUST"
                   for b in ex.read_exchange("MEXC")["balances"])

    def test_borsa_bakiyesi_dogrulanmis_sayilir(self, monkeypatch):
        """Borsa "bu senin" diyorsa dayanak budur; zincirdeki spam sorunu yok."""
        self._hazirla(monkeypatch)
        assert all(b["trust"] == "verified"
                   for b in ex.read_exchange("MEXC")["balances"])

    def test_bos_bakiye_hata_degil_bilgi(self, monkeypatch):
        """Borsa cevap verdiyse okuma başarılıdır; boşluk bir hata değildir."""
        self._hazirla(monkeypatch, cevap={"balances": []})
        okuma = ex.read_exchange("MEXC")
        assert okuma["ok"] is True
        assert okuma["incomplete"] is False
        assert [n["level"] for n in okuma["notes"]] == [ex.NOTE_INFO]

    def test_bakiye_alani_bulunamazsa_anlasilir_hata(self, monkeypatch):
        self._hazirla(monkeypatch, cevap={"baska_alan": []})
        okuma = ex.read_exchange("MEXC")
        assert okuma["ok"] is False
        assert "alan eşlemesi" in okuma["notes"][0]["message"]

    def test_anahtar_yoksa_soylenir(self):
        _kasa_ac()
        ex.save_profile(MEXC)
        okuma = ex.read_exchange("MEXC")
        assert okuma["ok"] is False
        assert "anahtar" in okuma["notes"][0]["message"].lower()

    def test_kasa_kilitliyken_ayri_mesaj_verilir(self, monkeypatch):
        """
        "Anahtar yok" ile "anahtar var ama kasa kilitli" ayrı sorunlardır.
        Kullanıcıyı zaten yaptığı bir işe göndermek F6'da bir kez yaşandı.
        """
        _kasa_ac()
        ex.save_credentials(MEXC, "ANAHTAR", "GIZLI", acknowledge_unverified=True)
        kv.lock()
        okuma = ex.read_exchange("MEXC")
        assert okuma["ok"] is False
        assert "kilitli" in okuma["notes"][0]["message"]

    def test_profil_yoksa_okuma_dusmez(self):
        okuma = ex.read_exchange("YOKBORSA")
        assert okuma["ok"] is False
        assert okuma["balances"] == []

    def test_ag_hatasi_istisna_degil_rapordur(self, monkeypatch):
        _kasa_ac()
        ex.save_credentials(MEXC, "ANAHTAR", "GIZLI", acknowledge_unverified=True)
        _sahte_http(monkeypatch, {"/api/v3/account": ex.ExchangeError("HTTP 401")})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        okuma = ex.read_exchange("MEXC")
        assert okuma["ok"] is False
        assert "401" in okuma["notes"][0]["message"]

    def test_read_all_biri_dusse_digeri_kalir(self, monkeypatch):
        _kasa_ac()
        ex.save_credentials(MEXC, "A", "S", acknowledge_unverified=True)
        ex.save_credentials({**BINANCE, "restrictions_path": ""}, "A", "S",
                            acknowledge_unverified=True)

        def sahte(url, headers=None):
            if "binance" in url:
                raise ex.ExchangeError("HTTP 418")
            return _hesap_cevabi()

        monkeypatch.setattr(ex, "_http_get", sahte)
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        okumalar = ex.read_all()
        assert okumalar["MEXC"]["ok"] is True
        assert okumalar["BINANCE"]["ok"] is False


# =====================================================================
# 6) DEFTERLE BİRLEŞME
# =====================================================================
class TestKarsilastirmayaKarisma:
    """
    Borsa okuması, zincir okumasıyla AYNI biçimde döner; karşılaştırma tablosu
    ve arayüz ikisini ayırt etmek zorunda değildir. Bunun karşılığı, F6'da
    yazılan her şeyin (yanlış konum tespiti, deftere ekleme, not seviyeleri)
    borsalarda da bedavaya çalışmasıdır.
    """

    def _kur(self, monkeypatch, defter_qty, borsa_qty):
        _kasa_ac()
        ex.save_credentials(MEXC, "A", "S", acknowledge_unverified=True)
        _sahte_http(monkeypatch, {"/api/v3/account": {"balances": [
            {"asset": "BTC", "free": str(borsa_qty), "locked": "0"}]}})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        monkeypatch.setattr(cx, "read_all", lambda only_enabled=True: {})

        data = dm.load_portfolio()
        data["transactions"] = [{
            "id": 1, "date": "2026-01-01", "coin": "BTCUSDT", "exchange": "MEXC",
            "qty": defter_qty, "cost": 60000.0, "status": dm.ACTIVE_STATUS}]
        dm.save_portfolio(data)
        return cx.compare_with_ledger()

    def test_borsa_bakiyesi_defterle_karsilastirilir(self, monkeypatch):
        rapor = self._kur(monkeypatch, 0.5, 0.5)
        satir = next(r for r in rapor["rows"] if r["asset"] == "BTC")
        assert satir["location"] == "MEXC"
        assert satir["status"] == "match"

    def test_borsadaki_fazlalik_fark_olarak_gorunur(self, monkeypatch):
        rapor = self._kur(monkeypatch, 0.5, 0.8)
        satir = next(r for r in rapor["rows"] if r["asset"] == "BTC")
        assert satir["status"] == "mismatch"
        assert satir["diff_qty"] == pytest.approx(0.3)

    def test_okuma_kaynagi_raporda_yazar(self, monkeypatch):
        """Aynı tabloda iki kaynak var; satırın nereden geldiği görünmeli."""
        rapor = self._kur(monkeypatch, 0.5, 0.5)
        okuma = rapor["connections"]["ex:MEXC"]
        assert okuma["source"] == "exchange"
        assert okuma["name"] == "MEXC"

    def test_borsa_dusse_zincir_okumasi_kalir(self, monkeypatch):
        """Borsa profilindeki bir sorun cüzdan okumalarını kaybettirmemeli."""
        monkeypatch.setattr(cx, "read_all", lambda only_enabled=True: {
            "c1": {"id": "c1", "location": "METAMASK", "ok": True, "chain": "bsc",
                   "address": "0x11", "notes": [], "incomplete": False,
                   "balances": [{"asset": "BNB", "qty": 1.0}]}})

        def patlayan(only_enabled=True):
            raise RuntimeError("borsa modülü çöktü")

        monkeypatch.setattr(ex, "read_all", patlayan)
        okumalar = cx.all_readings()
        assert okumalar["c1"]["ok"] is True


# =====================================================================
# 7) API UÇLARI
# =====================================================================
class TestApiUclari:

    def test_durum_ucu(self, client):
        govde = client.get("/api/exchanges").json()
        assert "profiles" in govde and "families" in govde and "builtin" in govde
        # Hazır profiller arayüze veri olarak gidiyor, koda gömülü değil.
        assert any(p["location"] == "BINANCE" for p in govde["builtin"])

    def test_yazma_yetkili_anahtar_403_doner(self, client, monkeypatch):
        _kasa_ac()
        _sahte_http(monkeypatch, {"apiRestrictions": {
            "enableReading": True, "enableWithdrawals": True,
            "enableSpotAndMarginTrading": False}})
        r = client.post("/api/exchanges", json={
            "profile": BINANCE, "api_key": "A", "api_secret": "S"})
        assert r.status_code == 403
        assert not kv.has(ex.key_name("BINANCE"))

    def test_gecersiz_profil_400_doner(self, client):
        r = client.post("/api/exchanges", json={
            "profile": {**BINANCE, "base_url": "http://api.x.com"},
            "api_key": "A", "api_secret": "S"})
        assert r.status_code == 400

    def test_kilitli_kasaya_anahtar_yazilamaz(self, client):
        r = client.post("/api/exchanges", json={
            "profile": MEXC, "api_key": "A", "api_secret": "S",
            "acknowledge_unverified": True})
        assert r.status_code == 423

    def test_kaydetme_ve_silme(self, client):
        _kasa_ac()
        r = client.post("/api/exchanges", json={
            "profile": MEXC, "api_key": "A", "api_secret": "S",
            "acknowledge_unverified": True})
        assert r.status_code == 200
        assert r.json()["credentials"]["MEXC"] is True

        r2 = client.delete("/api/exchanges/MEXC")
        assert r2.status_code == 200
        assert "MEXC" not in r2.json()["profiles"]

    def test_olmayan_profil_silinince_404(self, client):
        assert client.delete("/api/exchanges/YOK").status_code == 404

    def test_bakiye_ucu_salt_okunur_isaretli(self, client):
        assert client.get("/api/exchanges/balances").json()["read_only"] is True
