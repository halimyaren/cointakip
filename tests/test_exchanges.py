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


# =====================================================================
# 8) ANAHTAR BAŞLIĞI BORSAYA AİTTİR, AİLEYE DEĞİL
#
# MEXC, Binance'in imzalama şemasını birebir klonlar ama anahtarı kendi
# başlığında bekler. Başlık adı imzalama ailesine bağlandığı sürece MEXC
# profili hiçbir zaman kimlik doğrulayamaz — ve bunu hiçbir test yakalamaz,
# çünkü sahte HTTP hangi başlığın gönderildiğine bakmıyorsa her şey geçer.
#
# Canlı olarak doğrulandı (3 Eylül 2026, sahte anahtarla):
#   X-MBX-APIKEY  → {"code":400,"msg":"api key required"}   (başlıksızla aynı)
#   X-MEXC-APIKEY → {"code":10072,"msg":"Api key info invalid"}
# =====================================================================
class TestAnahtarBasligi:

    def test_mexc_kendi_basligini_kullanir(self, monkeypatch):
        cagrilar = _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.signed_get(MEXC, "/api/v3/account", "ANAHTAR", "GIZLI")
        basliklar = cagrilar[0]["headers"]
        assert basliklar["X-MEXC-APIKEY"] == "ANAHTAR"
        assert "X-MBX-APIKEY" not in basliklar

    def test_binance_kendi_basligini_kullanir(self, monkeypatch):
        cagrilar = _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.signed_get(BINANCE, "/api/v3/account", "ANAHTAR", "GIZLI")
        basliklar = cagrilar[0]["headers"]
        assert basliklar["X-MBX-APIKEY"] == "ANAHTAR"
        assert "X-MEXC-APIKEY" not in basliklar

    def test_iki_borsa_ayni_ailede_ama_farkli_baslikta(self):
        """Düzeltmenin özü: aynı imzalama ailesi, farklı başlık."""
        assert BINANCE["family"] == MEXC["family"] == "binance"
        assert ex.key_header(BINANCE) != ex.key_header(MEXC)

    def test_profilin_kendi_degeri_onceliklidir(self):
        profil = dict(MEXC, key_header="X-OZEL-KEY")
        assert ex.key_header(profil) == "X-OZEL-KEY"

    def test_eski_kayitli_profil_konumdan_toparlanir(self):
        """
        Bu düzeltmeden ÖNCE kaydedilmiş bir MEXC profilinde `key_header`
        alanı yoktur. Aile varsayılanına düşerse bozuk kalır; hazır profile
        düşerse çalışır.
        """
        eski = {k: v for k, v in MEXC.items() if k != "key_header"}
        assert ex.key_header(eski) == "X-MEXC-APIKEY"

    def test_tanimsiz_borsa_aile_varsayilanina_duser(self):
        profil = {"location": "YENIBORSA", "family": "binance"}
        assert ex.key_header(profil) == "X-MBX-APIKEY"

    def test_baslik_profil_dogrulamasindan_gecer(self):
        """
        `permission_status` bir kez beyaz listede unutulmuş ve sessizce
        düşmüştü. Aynı tuzak burada tekrarlanmamalı.
        """
        temiz, hata = ex.validate_profile(dict(MEXC))
        assert hata is None
        assert temiz["key_header"] == "X-MEXC-APIKEY"

    def test_bozuk_baslik_adi_reddedilir(self):
        temiz, hata = ex.validate_profile(dict(MEXC, key_header="X-Key: kotu\r\nX-Baska"))
        assert temiz is None and "başlık" in hata

    def test_bosluklu_baslik_adi_reddedilir(self):
        temiz, hata = ex.validate_profile(dict(MEXC, key_header="X Key"))
        assert temiz is None

    def test_bos_baslik_kabul_edilir_ve_toparlanir(self):
        """Boş bırakmak geçerlidir; `key_header()` hazır profile düşer."""
        temiz, hata = ex.validate_profile(dict(MEXC, key_header=""))
        assert hata is None
        assert ex.key_header(temiz) == "X-MEXC-APIKEY"


# =====================================================================
# 9) ANAHTAR ÖMRÜ
#
# Hiçbir borsa API'si bir anahtarın bitiş tarihini bildirmiyor, bu yüzden
# tarih kullanıcıdan gelir ve isteğe bağlıdır. MEXC dinamik IP'de anahtara
# 90 gün ömür veriyor; süre dolduğunda anahtar SESSİZCE ölür ve okuma
# "başarısız" görünür. Kullanıcı sebebini bağlantıda, ağda veya kodda arar.
#
# En kritik güvence: girilmemiş tarih "sonsuz geçerli" DEĞİL "bilinmiyor"dur.
# =====================================================================
class TestAnahtarOmru:

    def _tarih(self, gun_sonra):
        from datetime import datetime, timedelta
        return (datetime.now().date() + timedelta(days=gun_sonra)).strftime("%Y-%m-%d")

    def test_tarih_yoksa_bilinmiyor_doner(self):
        """Boş bırakmak 'sonsuz geçerli' anlamına GELMEZ."""
        d = ex.key_expiry_state(dict(MEXC))
        assert d["state"] == "unknown"
        assert d["days_left"] is None

    def test_uzak_tarih_sorunsuz(self):
        d = ex.key_expiry_state(dict(MEXC, key_expires_at=self._tarih(89)))
        assert d["state"] == "ok" and d["days_left"] == 89

    def test_esik_icindeki_tarih_uyarir(self):
        d = ex.key_expiry_state(dict(MEXC, key_expires_at=self._tarih(10)))
        assert d["state"] == "expiring" and d["days_left"] == 10

    def test_esigin_tam_ustu_uyarmaz(self):
        d = ex.key_expiry_state(
            dict(MEXC, key_expires_at=self._tarih(ex.KEY_EXPIRY_WARN_DAYS + 1)))
        assert d["state"] == "ok"

    def test_esigin_tam_kendisi_uyarir(self):
        d = ex.key_expiry_state(
            dict(MEXC, key_expires_at=self._tarih(ex.KEY_EXPIRY_WARN_DAYS)))
        assert d["state"] == "expiring"

    def test_bugun_biten_anahtar_henuz_dolmamis(self):
        d = ex.key_expiry_state(dict(MEXC, key_expires_at=self._tarih(0)))
        assert d["state"] == "expiring" and d["days_left"] == 0

    def test_gecmis_tarih_dolmus(self):
        d = ex.key_expiry_state(dict(MEXC, key_expires_at=self._tarih(-3)))
        assert d["state"] == "expired" and d["days_left"] == -3

    def test_bozuk_tarih_bilinmiyor_sayilir(self):
        """Bozuk tarihi 'dolmuş' saymak yanlış alarm, 'geçerli' saymak yalan olurdu."""
        d = ex.key_expiry_state({"key_expires_at": "yarin"})
        assert d["state"] == "unknown"

    def test_bozuk_tarih_kaydedilemez(self):
        temiz, hata = ex.validate_profile(dict(MEXC, key_expires_at="31/12/2026"))
        assert temiz is None and "YYYY-AA-GG" in hata

    def test_gecerli_tarih_profilde_saklanir(self):
        """`permission_status` bir kez beyaz listede unutulmuştu; tuzak tekrarlanmasın."""
        temiz, hata = ex.validate_profile(dict(MEXC, key_expires_at="2026-12-31"))
        assert hata is None and temiz["key_expires_at"] == "2026-12-31"

    def test_bos_tarih_kabul_edilir(self):
        temiz, hata = ex.validate_profile(dict(MEXC, key_expires_at=""))
        assert hata is None and temiz["key_expires_at"] == ""

    def test_status_yalnizca_anahtari_olan_profili_bildirir(self):
        """Anahtarsız profilde 'süresi doldu' demek kafa karıştırırdı."""
        _kasa_ac()
        ex.save_profile(dict(MEXC, key_expires_at=self._tarih(-1)))
        durum = ex.status()
        assert "MEXC" in durum["profiles"]
        assert "MEXC" not in durum["key_expiry"]      # anahtar yok

    def test_status_anahtar_varken_sure_bildirir(self, monkeypatch):
        _kasa_ac()
        _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.save_credentials(dict(MEXC, key_expires_at=self._tarih(5)),
                            "A", "S", acknowledge_unverified=True)
        durum = ex.status()
        assert durum["key_expiry"]["MEXC"]["state"] == "expiring"
        assert durum["expiry_warn_days"] == ex.KEY_EXPIRY_WARN_DAYS

    def test_okuma_basarili_ama_sure_yaklasiyorsa_soylenir(self, monkeypatch):
        """Uyarının değeri, anahtar HÂLÂ çalışırken görülmesindedir."""
        _kasa_ac()
        _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.save_credentials(dict(MEXC, key_expires_at=self._tarih(3)),
                            "A", "S", acknowledge_unverified=True)
        okuma = ex.read_exchange("MEXC")
        assert okuma["ok"] is True
        assert any("3 gün sonra doluyor" in n["message"] for n in okuma["notes"])

    def test_okuma_hatasinda_dolmus_anahtar_sebep_olarak_soylenir(self, monkeypatch):
        """
        Borsanın hatası genellikle anlamsız görünür ("Api key info invalid").
        Sebebi biliyorsak söyleriz; kullanıcı ağda veya kodda aramasın.
        """
        _kasa_ac()
        _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.save_credentials(dict(MEXC), "A", "S", acknowledge_unverified=True)
        ex.save_profile(dict(MEXC, key_expires_at=self._tarih(-2)))

        _sahte_http(monkeypatch, {"/api/v3/account":
                                  ex.ExchangeError("Api key info invalid")})
        okuma = ex.read_exchange("MEXC")
        assert okuma["ok"] is False
        metin = " ".join(n["message"] for n in okuma["notes"])
        assert "süresi" in metin and "doldu" in metin
        assert "Api key info invalid" in metin      # ham hata da kaybolmuyor

    def test_suresi_bilinmeyen_anahtarin_hatasi_uydurulmaz(self, monkeypatch):
        _kasa_ac()
        _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.save_credentials(dict(MEXC), "A", "S", acknowledge_unverified=True)

        _sahte_http(monkeypatch, {"/api/v3/account": ex.ExchangeError("ag hatasi")})
        okuma = ex.read_exchange("MEXC")
        metin = " ".join(n["message"] for n in okuma["notes"])
        assert "süresi" not in metin


# =====================================================================
# 10) ANAHTARA DOKUNMADAN PROFİL GÜNCELLEME
#
# Gizli anahtar borsada yalnızca oluşturulurken BİR KEZ gösterilir. Sadece
# bitiş tarihi girmek için anahtarın tamamını yeniden istemek, elinde secret
# olmayan kullanıcıyı yepyeni bir API anahtarı almaya zorlardı.
#
# Ama kolaylık güvenliği yemez: `base_url`, `account_path`, `key_header` ve
# `family` anahtarın NEREYE ve NASIL gönderileceğini belirler. Bunlar anahtar
# yeniden denetlenmeden değiştirilebilseydi, kasadaki anahtar bir sonraki
# okumada başka bir sunucuya gönderilebilirdi.
# =====================================================================
class TestAyarlariAnahtarsizGuncelleme:

    @pytest.fixture
    def kayitli(self, monkeypatch):
        _kasa_ac()
        _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.save_credentials(dict(MEXC), "A", "S", acknowledge_unverified=True)
        return "MEXC"

    def test_bitis_tarihi_anahtarsiz_yazilir(self, kayitli):
        p = ex.update_profile_fields("MEXC", {"key_expires_at": "2026-12-01"})
        assert p["key_expires_at"] == "2026-12-01"

    def test_anahtar_kasada_kalir(self, kayitli):
        ex.update_profile_fields("MEXC", {"key_expires_at": "2026-12-01"})
        assert ex.credentials_stored("MEXC") is True
        assert ex._kasadan("MEXC") == ("A", "S")

    def test_izin_durumu_korunur(self, kayitli):
        """Bu güncelleme izin denetimi yapmadı; sonucu da uydurmamalı."""
        ex.update_profile_fields("MEXC", {"key_expires_at": "2026-12-01"})
        assert ex.list_profiles()["MEXC"]["permission_status"] == ex.PERM_UNKNOWN

    def test_ad_ve_etiket_guncellenebilir(self, kayitli):
        p = ex.update_profile_fields("MEXC", {"name": "MEXC Ana", "label": "ana hesap"})
        assert p["name"] == "MEXC Ana" and p["label"] == "ana hesap"

    def test_taban_adres_degistirilemez(self, kayitli):
        """En kritik güvence: anahtar başka bir sunucuya yönlendirilemez."""
        with pytest.raises(ValueError, match="base_url"):
            ex.update_profile_fields("MEXC", {"base_url": "https://kotu.example.com"})

    def test_hesap_ucu_degistirilemez(self, kayitli):
        with pytest.raises(ValueError, match="account_path"):
            ex.update_profile_fields("MEXC", {"account_path": "/baska/uc"})

    def test_anahtar_basligi_degistirilemez(self, kayitli):
        with pytest.raises(ValueError, match="key_header"):
            ex.update_profile_fields("MEXC", {"key_header": "X-BASKA"})

    def test_imzalama_ailesi_degistirilemez(self, kayitli):
        with pytest.raises(ValueError, match="family"):
            ex.update_profile_fields("MEXC", {"family": "baska_aile"})

    def test_ayni_degeri_gondermek_engel_degil(self, kayitli):
        """Arayüz formun tamamını yolluyor; değişmemiş alan hata sayılmamalı."""
        p = ex.update_profile_fields("MEXC", dict(MEXC, key_expires_at="2026-12-01"))
        assert p["key_expires_at"] == "2026-12-01"

    def test_olmayan_profil_reddedilir(self):
        with pytest.raises(ValueError, match="tanımlı bir borsa profili yok"):
            ex.update_profile_fields("YOKBORSA", {"label": "x"})

    def test_bozuk_tarih_yine_reddedilir(self, kayitli):
        with pytest.raises(ValueError, match="YYYY-AA-GG"):
            ex.update_profile_fields("MEXC", {"key_expires_at": "01.12.2026"})

    def test_kasa_kilitliyken_de_calisir(self, kayitli):
        """Burada hiçbir sır okunmuyor; kasayı açtırmak gereksiz sürtünme olurdu."""
        kv.lock()
        p = ex.update_profile_fields("MEXC", {"key_expires_at": "2026-12-01"})
        assert p["key_expires_at"] == "2026-12-01"


class TestAyarGuncellemeUcu:

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        import main
        return TestClient(main.app)

    def test_patch_ucu_tarihi_yazar(self, client, monkeypatch):
        _kasa_ac()
        _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.save_credentials(dict(MEXC), "A", "S", acknowledge_unverified=True)

        r = client.patch("/api/exchanges/MEXC", json={"key_expires_at": "2026-12-01"})
        assert r.status_code == 200
        assert r.json()["profile"]["key_expires_at"] == "2026-12-01"
        assert r.json()["credentials"]["MEXC"] is True

    def test_patch_taban_adresi_reddeder(self, client, monkeypatch):
        _kasa_ac()
        _sahte_http(monkeypatch, {"/api/v3/account": _hesap_cevabi()})
        monkeypatch.setattr(ex, "server_time_offset", lambda p, yenile=False: 0)
        ex.save_credentials(dict(MEXC), "A", "S", acknowledge_unverified=True)

        r = client.patch("/api/exchanges/MEXC",
                         json={"base_url": "https://kotu.example.com"})
        assert r.status_code == 400

    def test_patch_olmayan_profilde_400(self, client):
        assert client.patch("/api/exchanges/YOK", json={"label": "x"}).status_code == 400
