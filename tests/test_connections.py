r"""
CoinTakip — FAZ F6 Testleri: Anahtar Kasası ve Zincir Üstü Bağlantılar

En kritik güvenceler:

1. **Kasa gerçekten şifreliyor.** Sır düz metin olarak diske yazılmıyor ve
   yanlış PIN ile çözülemiyor. Base64 obfuscation bilinçli olarak kullanılmadı.

2. **PIN değişince anahtarlar kaybolmuyor.** Kasa PIN'e bağlı; yeniden
   mühürleme olmazsa kullanıcı bütün anahtarlarını sessizce kaybederdi.
   Kurtarılamayacak durumda ise kasa temizleniyor ve bu açıkça bildiriliyor —
   çözülemeyen şifreli çöp saklamak "anahtarım duruyor" yanılgısı verir.

3. **Sır asla adres kutusuna girmiyor.** Seed phrase veya özel anahtar
   yapıştırıldığında sistem kabul etmiyor ve kullanıcıyı uyarıyor.

4. **Okunamayan bağlantı boş sanılmıyor.** `None` (bilmiyorum) ile `0.0`
   (orada yok) ayrı tutuluyor; ikisini karıştırmak kullanıcının varlığını
   silmeye kalkmak demektir.

Testler ağa ÇIKMAZ: tüm zincir çağrıları taklit edilir.
"""

import json
import time

import pytest

import connections as cx
import data_manager as dm
import keyvault as kv


@pytest.fixture(autouse=True)
def kasa_kilitli():
    """Her test kilitli kasayla başlasın; oturum anahtarı testler arası sızmasın."""
    kv.lock()
    yield
    kv.lock()


def _pin_kur(pin="1234"):
    dm.set_pin(pin)
    return pin


# =====================================================================
# BÖLÜM 1 — ANAHTAR KASASI
# =====================================================================
class TestKasa:

    def test_pin_yoksa_kasa_acilmaz(self):
        with pytest.raises(kv.VaultError, match="PIN"):
            kv.unlock("1234")

    def test_hatali_pin_reddedilir(self):
        _pin_kur("1234")
        with pytest.raises(kv.VaultError, match="Hatalı PIN"):
            kv.unlock("9999")

    def test_sir_yazilip_okunur(self):
        _pin_kur()
        kv.unlock("1234")
        kv.put("etherscan_api_key", "GIZLI-ANAHTAR-123")
        assert kv.get("etherscan_api_key") == "GIZLI-ANAHTAR-123"

    def test_sir_diske_duz_metin_yazilmaz(self):
        """Kasanın tek işi bu. Dosyada düz metin görünüyorsa kasa yoktur."""
        _pin_kur()
        kv.unlock("1234")
        kv.put("etherscan_api_key", "GIZLI-ANAHTAR-123")
        ham = open(dm.SETTINGS_FILE, encoding="utf-8").read()
        assert "GIZLI-ANAHTAR-123" not in ham
        # Base64 ile gizlenmiş hâli de bulunmamalı — o şifreleme değildir.
        import base64
        assert base64.b64encode(b"GIZLI-ANAHTAR-123").decode() not in ham

    def test_kilitliyken_okunamaz(self):
        _pin_kur()
        kv.unlock("1234")
        kv.put("etherscan_api_key", "GIZLI")
        kv.lock()
        with pytest.raises(kv.VaultLocked):
            kv.get("etherscan_api_key")

    def test_kilitliyken_varligi_sorulabilir(self):
        """Arayüz 'anahtar tanımlı ama kasa kilitli' diyebilmeli."""
        _pin_kur()
        kv.unlock("1234")
        kv.put("etherscan_api_key", "GIZLI")
        kv.lock()
        assert kv.has("etherscan_api_key") is True
        assert kv.is_unlocked() is False

    def test_bos_deger_kaydi_siler(self):
        _pin_kur()
        kv.unlock("1234")
        kv.put("etherscan_api_key", "GIZLI")
        kv.put("etherscan_api_key", "")
        assert kv.has("etherscan_api_key") is False

    def test_pin_degisince_anahtarlar_korunur(self):
        """Yeniden mühürleme olmazsa kullanıcı anahtarını SESSİZCE kaybeder."""
        _pin_kur("1234")
        kv.unlock("1234")
        kv.put("etherscan_api_key", "GIZLI-ANAHTAR-123")

        assert dm.change_pin("1234", "5678") is True

        kv.lock()
        kv.unlock("5678")
        assert kv.get("etherscan_api_key") == "GIZLI-ANAHTAR-123"

    def test_kurtarma_ile_sifirlamada_kasa_temizlenir(self):
        """
        Eski PIN elde olmadığı için kasa çözülemez. Şifreli çöpü saklamak
        kullanıcıya 'anahtarım duruyor' yanılgısı verirdi.
        """
        sonuc = dm.set_pin("1234")
        kv.unlock("1234")
        kv.put("etherscan_api_key", "GIZLI")

        yeni = dm.reset_pin_with_recovery(sonuc["recovery_key"], "4321")
        assert yeni["success"] is True
        assert yeni["vault_cleared"] == 1
        assert kv.has("etherscan_api_key") is False

    def test_pin_kapatilinca_kasa_temizlenir(self):
        _pin_kur("1234")
        kv.unlock("1234")
        kv.put("etherscan_api_key", "GIZLI")
        assert dm.disable_pin("1234") is True
        assert kv.has("etherscan_api_key") is False

    def test_durum_icerik_sizdirmaz(self):
        _pin_kur()
        kv.unlock("1234")
        kv.put("etherscan_api_key", "GIZLI-ANAHTAR-123")
        durum = kv.status()
        assert durum["unlocked"] is True and durum["entry_count"] == 1
        assert "GIZLI-ANAHTAR-123" not in json.dumps(durum)


# =====================================================================
# BÖLÜM 2 — ADRES DOĞRULAMA VE SIR KORUMASI
# =====================================================================
class TestAdresDogrulama:

    def test_gecerli_evm_adresi_kabul_edilir(self):
        adres, hata = cx.validate_address("ethereum", "0x" + "aB" * 20)
        assert hata is None and adres == "0x" + "ab" * 20

    def test_gecerli_solana_adresi_kabul_edilir(self):
        adres, hata = cx.validate_address(
            "solana", "So11111111111111111111111111111111111111112")
        assert hata is None and adres

    def test_seed_phrase_reddedilir_ve_uyarilir(self):
        """
        Kullanıcı korunmalı. Sessizce reddetmek yetmez — ne yaptığını ve
        neden tehlikeli olduğunu görmeli.
        """
        ifade = " ".join(["abandon"] * 12)
        adres, hata = cx.validate_address("ethereum", ifade)
        assert adres is None
        assert "kurtarma ifadesi" in hata and "asla" in hata

    def test_ozel_anahtar_reddedilir(self):
        adres, hata = cx.validate_address("ethereum", "0x" + "a" * 64)
        assert adres is None and "özel anahtar" in hata

    def test_bozuk_adres_reddedilir(self):
        assert cx.validate_address("ethereum", "0x123")[0] is None
        assert cx.validate_address("solana", "0xabc")[0] is None

    def test_bilinmeyen_zincir_reddedilir(self):
        assert cx.validate_address("dogecoin", "abc")[0] is None


# =====================================================================
# BÖLÜM 3 — KAYIT DEFTERİ
# =====================================================================
class TestKayitDefteri:

    def test_baglanti_kaydedilir_ve_okunur(self):
        cx.save_connection("METAMASK", {
            "type": "onchain", "chain": "ethereum", "address": "0x" + "11" * 20})
        kayitlar = list(cx.list_connections().values())
        assert len(kayitlar) == 1
        assert kayitlar[0]["chain"] == "ethereum"
        assert kayitlar[0]["location"] == "METAMASK"

    def test_ayni_zincirde_iki_hesap_birbirini_EZMEZ(self):
        """
        GERCEK HATA (2): kimlik (konum, zincir) cifti yapilinca da yetmedi.
        Kullanicinin Phantom cuzdaninda Hesap 2 ve Hesap 3 var, ikisi de Solana
        aginda ve her birinin kendi tokenlari var. Benzersiz olan tek sey ADRESTIR.
        """
        cx.save_connection("PHANTOM", {
            "chain": "solana", "label": "Hesap 2",
            "address": "So11111111111111111111111111111111111111112"})
        cx.save_connection("PHANTOM", {
            "chain": "solana", "label": "Hesap 3",
            "address": "TestHesapUcAdresiAAAAAAAAAAAAAAAAAAAAAAAAAAA"})
        kayitlar = cx.list_connections()
        assert len(kayitlar) == 2
        assert {v["label"] for v in kayitlar.values()} == {"Hesap 2", "Hesap 3"}
        assert all(v["location"] == "PHANTOM" for v in kayitlar.values())

    def test_ayni_konum_farkli_zincir_birbirini_EZMEZ(self):
        """
        GERÇEK HATA: kayıt defteri yalnızca konum adıyla anahtarlanıyordu.
        Kullanıcı PHANTOM'u önce Solana, sonra Ethereum olarak kaydedince
        Solana bağlantısı SESSİZCE kayboldu. Bir cüzdan birden çok zincirde
        yaşar; kimlik (konum, zincir) çiftidir.
        """
        cx.save_connection("PHANTOM", {
            "chain": "solana", "address": "So11111111111111111111111111111111111111112"})
        cx.save_connection("PHANTOM", {
            "chain": "ethereum", "address": "0x" + "11" * 20})
        zincirler = {v["chain"] for v in cx.list_connections().values()}
        assert zincirler == {"solana", "ethereum"}

    def test_ayni_konum_ayni_zincir_guncellenir(self):
        """Aynı çift ikinci kez kaydedilirse yeni adres eskisinin yerine geçer."""
        adres = "0x" + "11" * 20
        cx.save_connection("METAMASK", {"chain": "bsc", "address": adres})
        cx.save_connection("METAMASK", {"chain": "bsc", "address": adres,
                                        "label": "Ana hesap"})
        kayitlar = cx.list_connections()
        assert len(kayitlar) == 1
        assert list(kayitlar.values())[0]["label"] == "Ana hesap"

    def test_tek_zincir_silinince_digeri_kalir(self):
        cx.save_connection("PHANTOM", {
            "chain": "solana", "address": "So11111111111111111111111111111111111111112"})
        cx.save_connection("PHANTOM", {
            "chain": "ethereum", "address": "0x" + "11" * 20})
        kimlik = list(cx.list_connections())[0]
        assert cx.delete_connection(kimlik) is True
        assert len(cx.list_connections()) == 1

    def test_eski_bicimli_kayit_yeni_bicime_cevrilir(self):
        """Önceki sürümde kaydedilmiş bağlantılar elle düzeltme gerektirmemeli."""
        settings = dm.load_settings()
        settings["connections"] = {
            "METAMASK": {"type": "onchain", "chain": "arbitrum",
                         "address": "0x" + "33" * 20, "enabled": True,
                         "label": "", "tokens": []},
            "PHANTOM@solana": {"type": "onchain", "chain": "solana",
                               "address": "So11111111111111111111111111111111111111112",
                               "enabled": True, "label": "", "tokens": []},
        }
        dm.save_settings(settings)
        kayitlar = cx.list_connections()
        assert len(kayitlar) == 2
        assert {v["location"] for v in kayitlar.values()} == {"METAMASK", "PHANTOM"}

    def test_gecersiz_tanim_kaydedilmez(self):
        with pytest.raises(ValueError):
            cx.save_connection("METAMASK", {"type": "onchain", "chain": "ethereum",
                                            "address": "bozuk"})
        assert "METAMASK" not in cx.list_connections()

    def test_borsa_turu_bu_fazda_reddedilir(self):
        """Yapılmayan bir şeyi yapıyormuş gibi göstermek yalan olurdu."""
        temiz, hata = cx.validate_connection({"type": "cex", "chain": "ethereum",
                                              "address": "0x" + "11" * 20})
        assert temiz is None and "borsa API" in hata

    def test_baglanti_silinir(self):
        kayit = cx.save_connection("PHANTOM", {
            "chain": "solana", "address": "So11111111111111111111111111111111111111112"})
        kimlik = list(kayit)[0]
        assert cx.delete_connection(kimlik) is True
        assert cx.delete_connection(kimlik) is False

    def test_kayit_ayarlarin_geri_kalanini_bozmaz(self):
        """merge_settings hatası bir kez PIN'i sessizce silmişti; tekrarlamasın."""
        _pin_kur()
        cx.save_connection("METAMASK", {
            "chain": "bsc", "address": "0x" + "22" * 20})
        assert dm.load_settings()["security"]["pin_enabled"] is True

    def test_ayni_adres_iki_konumda_uyari_uretir(self):
        """
        GERÇEK DURUM: kullanıcı aynı hesabı hem MetaMask'e hem Phantom'a almış,
        iki cüzdan da aynı 0x adresini gösteriyor. İki konum olarak kaydetmek
        AYNI PARAYI İKİ KEZ saydırır. Engellenmiyor ama sessiz de kalınmıyor.
        """
        adres = "0x" + "99" * 20
        cx.save_connection("METAMASK", {"chain": "ethereum", "address": adres})
        cx.save_connection("PHANTOM", {"chain": "ethereum", "address": adres})
        uyarilar = cx.duplicate_address_warnings()
        assert len(uyarilar) == 1
        assert "iki kez" in uyarilar[0]
        assert "METAMASK" in uyarilar[0] and "PHANTOM" in uyarilar[0]

    def test_ayni_adres_tek_konumda_uyari_uretmez(self):
        """Aynı adresin farklı zincirlerde olması normaldir; uyarı çıkmamalı."""
        adres = "0x" + "99" * 20
        cx.save_connection("METAMASK", {"chain": "ethereum", "address": adres})
        cx.save_connection("METAMASK", {"chain": "bsc", "address": adres})
        assert cx.duplicate_address_warnings() == []

    def test_konum_onerileri_yaygin_cuzdanlari_icerir(self):
        """
        Kullanıcı haklıydı: öneri listesinde yalnızca defterinde geçenler vardı,
        PHANTOM yoktu. Öneriler VERİ DEĞİLDİR — seçilmedikçe hiçbir yere yazılmaz.
        """
        oneriler = cx.location_suggestions()
        assert "PHANTOM" in oneriler and "METAMASK" in oneriler
        assert len(oneriler) == len(set(oneriler))          # tekrarsız
        # Öneri listesi defteri değiştirmemeli.
        assert dm.load_portfolio()["transactions"] == []

    def test_desteklenen_zincirler_koddan_turer(self):
        idler = {z["id"] for z in cx.supported_chains()}
        assert {"ethereum", "bsc", "arbitrum", "solana"} <= idler


# =====================================================================
# BÖLÜM 4 — ZİNCİR OKUMA (ağ taklit edilir)
# =====================================================================
class TestZincirOkuma:

    def test_evm_yerel_bakiye_okunur(self, monkeypatch):
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p: hex(int(1.5e18)))
        bakiyeler, uyarilar = cx.read_evm("ethereum", "0x" + "11" * 20)
        assert bakiyeler[0]["asset"] == "ETH"
        assert bakiyeler[0]["qty"] == pytest.approx(1.5)
        # Anahtar yoksa token keşfi yapılamaz; bu SÖYLENMELİ, gizlenmemeli.
        # Kullanıcı BNB Chain tokenının neden gelmediğini soramadan anlamalı.
        assert any(n["level"] == "warn" and "etherscan.io" in n["message"]
                   for n in uyarilar)

    def test_evm_token_bakiyesi_ondaligi_dogru_uygular(self, monkeypatch):
        cagrilar = []

        def sahte_rpc(url, method, params):
            cagrilar.append(method)
            if method == "eth_getBalance":
                return "0x0"
            return hex(1234500)          # 6 haneli token → 1.2345

        monkeypatch.setattr(cx, "_rpc", sahte_rpc)
        bakiyeler, _ = cx.read_evm(
            "polygon", "0x" + "11" * 20,
            tokens=[{"contract": "0x" + "cc" * 20, "symbol": "USDC", "decimals": 6}])
        assert bakiyeler[0]["asset"] == "USDC"
        assert bakiyeler[0]["qty"] == pytest.approx(1.2345)
        assert "eth_call" in cagrilar

    def test_evm_token_kesfi_anahtarla_calisir(self, monkeypatch):
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p: "0x0" if m == "eth_getBalance"
                            else hex(5 * 10 ** 18))
        monkeypatch.setattr(cx, "_etherscan", lambda cid, params, key: [
            {"contractAddress": "0x" + "dd" * 20, "tokenSymbol": "rdnt",
             "tokenDecimal": "18"},
            {"contractAddress": "0x" + "dd" * 20, "tokenSymbol": "rdnt",
             "tokenDecimal": "18"},
        ])
        bakiyeler, uyarilar = cx.read_evm("arbitrum", "0x" + "11" * 20,
                                          api_key="ANAHTAR")
        assert [b["asset"] for b in bakiyeler] == ["RDNT"]   # mükerrer teklendi
        assert bakiyeler[0]["qty"] == pytest.approx(5.0)
        # Keşif başarılı: hiçbir HATA veya EKSİKLİK notu yok.
        assert not cx.is_incomplete(uyarilar)
        # Ama token yalnızca keşiften geldi; defterde geçmiyor ve elle
        # tanımlanmadı. Bu "spam" hükmü değil "dayanağım yok" hükmüdür ve
        # bir BİLGİ notuyla söylenir.
        assert bakiyeler[0]["trust"] == cx.TRUST_UNKNOWN
        assert [n["level"] for n in uyarilar] == [cx.NOTE_INFO]

    def test_solana_spl_tokenlari_okunur(self, monkeypatch):
        def sahte_rpc(url, method, params):
            if method == "getBalance":
                return {"value": 2_500_000_000}          # 2.5 SOL
            return {"value": [{"account": {"data": {"parsed": {"info": {
                "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "tokenAmount": {"uiAmount": 42.5}}}}}}]}

        monkeypatch.setattr(cx, "_rpc", sahte_rpc)
        monkeypatch.setattr(cx, "_solana_symbols",
                            lambda: {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC"})
        bakiyeler, uyarilar = cx.read_solana("So11111111111111111111111111111111111111112")
        assert uyarilar == []
        assert {b["asset"]: b["qty"] for b in bakiyeler} == pytest.approx(
            {"SOL": 2.5, "USDC": 42.5})

    def test_bilinmeyen_mint_uydurulmaz(self, monkeypatch):
        """Sembol bulunamazsa ham mint gösterilir; uydurma sembol yazılmaz."""
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p:
                            {"value": 0} if m == "getBalance" else
                            {"value": [{"account": {"data": {"parsed": {"info": {
                                "mint": "MintAdresi1111111111111111111111111111111111",
                                "tokenAmount": {"uiAmount": 7.0}}}}}}]})
        monkeypatch.setattr(cx, "_solana_symbols", lambda: {})
        bakiyeler, _ = cx.read_solana("So11111111111111111111111111111111111111112")
        assert "…" in bakiyeler[0]["asset"]

    def test_ag_hatasi_istisna_degil_rapordur(self, monkeypatch):
        def patlat(*a, **k):
            raise RuntimeError("bağlantı reddedildi")

        monkeypatch.setattr(cx, "_rpc", patlat)
        kayit = cx.save_connection("METAMASK", {"chain": "ethereum",
                                                "address": "0x" + "11" * 20})
        sonuc = cx.read_connection(list(kayit)[0])
        assert sonuc["ok"] is True          # bağlantı tanımı geçerli
        assert sonuc["balances"] == []
        assert sonuc["incomplete"] is True
        assert any("okunamadı" in n["message"] for n in sonuc["notes"])


# =====================================================================
# BÖLÜM 5 — DEFTERLE KARŞILAŞTIRMA
# =====================================================================
class TestKarsilastirma:

    def _defter(self, lotlar):
        data = dm.load_portfolio()
        data["transactions"] = [
            {"id": i, "date": "2026-01-01", "coin": coin, "exchange": konum,
             "qty": qty, "cost": 1.0, "status": dm.ACTIVE_STATUS}
            for i, (coin, konum, qty) in enumerate(lotlar, start=1)
        ]
        dm.save_portfolio(data)
        return data

    def _baglanti(self, monkeypatch, bakiyeler):
        cx.save_connection("METAMASK", {"chain": "ethereum", "address": "0x" + "11" * 20})
        monkeypatch.setattr(cx, "read_connection", lambda k, spec=None: {
            "id": k, "location": "METAMASK", "ok": True, "chain": "ethereum",
            "address": "0x" + "11" * 20, "balances": bakiyeler, "notes": [],
        })

    def test_uyusan_bakiye_eslesme_sayilir(self, monkeypatch):
        self._defter([("RDNTUSDT", "METAMASK", 100.0)])
        self._baglanti(monkeypatch, [{"asset": "RDNT", "qty": 100.0}])
        rapor = cx.compare_with_ledger()
        assert rapor["status_counts"].get("match") == 1

    def test_zincirde_var_defterde_yok(self, monkeypatch):
        self._defter([])
        self._baglanti(monkeypatch, [{"asset": "RDNT", "qty": 100.0}])
        satir = cx.compare_with_ledger()["rows"][0]
        assert satir["status"] == "only_chain"

    def test_defterde_var_zincirde_yok(self, monkeypatch):
        self._defter([("RDNTUSDT", "METAMASK", 100.0)])
        self._baglanti(monkeypatch, [])
        satir = cx.compare_with_ledger()["rows"][0]
        assert satir["status"] == "only_ledger"
        assert satir["chain_qty"] == 0.0

    def test_okunamayan_baglanti_fark_sayilmaz(self, monkeypatch):
        """
        Okunamayan cüzdanı boş sanmak, kullanıcının varlığını silmeye
        kalkmak demektir — F5b'de düzeltilen hatanın aynısı.
        """
        self._defter([("RDNTUSDT", "METAMASK", 100.0)])
        cx.save_connection("METAMASK", {"chain": "ethereum", "address": "0x" + "11" * 20})
        monkeypatch.setattr(cx, "read_connection", lambda konum, spec=None: {
            "location": "METAMASK", "ok": False, "balances": [],
            "notes": [{"level": "error", "message": "Bağlantı okunamadı"}], "incomplete": True})
        satir = cx.compare_with_ledger()["rows"][0]
        assert satir["status"] == "unreadable"
        assert satir["chain_qty"] is None
        assert satir["diff_qty"] is None

    def test_live_balance_bilinmiyor_ile_sifiri_ayirir(self, monkeypatch):
        cx.save_connection("METAMASK", {"chain": "ethereum", "address": "0x" + "11" * 20})
        monkeypatch.setattr(cx, "read_connection", lambda k, spec=None: {
            "id": k, "location": "METAMASK", "ok": True,
            "chain": "ethereum", "balances": [{"asset": "RDNT", "qty": 12.0}],
            "notes": []})
        assert cx.live_balance("RDNT", "METAMASK") == pytest.approx(12.0)
        assert cx.live_balance("XYZ", "METAMASK") == 0.0     # okundu, yok
        assert cx.live_balance("RDNT", "BINANCE") is None    # bağlantı yok

    def test_konumun_zincirleri_toplanir(self, monkeypatch):
        """Bir cüzdanın farklı zincirlerdeki aynı varlığı tek bakiyedir."""
        cx.save_connection("PHANTOM", {"chain": "ethereum", "address": "0x" + "11" * 20})
        cx.save_connection("PHANTOM", {
            "chain": "arbitrum", "address": "0x" + "22" * 20})
        monkeypatch.setattr(cx, "read_connection", lambda k, spec=None: {
            "id": k, "location": "PHANTOM", "ok": True,
            "chain": (spec or {}).get("chain"), "notes": [],
            "balances": [{"asset": "ETH", "qty": 1.5}]})
        assert cx.live_balance("ETH", "PHANTOM") == pytest.approx(3.0)

    def test_bir_zincir_okunamazsa_sifir_denmez(self, monkeypatch):
        """
        Okunamayan zincirde o varlık duruyor olabilir. 'Sıfır' demek, kullanıcının
        varlığını yok saymaktır — F5b'de düzeltilen hatanın aynısı.
        """
        cx.save_connection("PHANTOM", {"chain": "ethereum", "address": "0x" + "11" * 20})
        cx.save_connection("PHANTOM", {
            "chain": "solana", "address": "So11111111111111111111111111111111111111112"})

        def sahte(k, spec=None):
            zincir = (spec or {}).get("chain")
            if zincir == "solana":
                return {"id": k, "location": "PHANTOM", "ok": False,
                        "chain": zincir, "balances": [], "notes": [{"level": "error", "message": "patladı"}], "incomplete": True}
            return {"id": k, "location": "PHANTOM", "ok": True, "chain": zincir,
                    "balances": [{"asset": "ETH", "qty": 1.0}], "notes": []}

        monkeypatch.setattr(cx, "read_connection", sahte)
        assert cx.live_balance("ETH", "PHANTOM") == pytest.approx(1.0)
        # SOL yalnızca okunamayan zincirde olabilir → "bilmiyorum".
        assert cx.live_balance("SOL", "PHANTOM") is None

    def test_baglantisiz_konum_karsilastirmaya_girmez(self, monkeypatch):
        """Bağlantısı olmayan konum için 'fark' demek gürültüdür."""
        self._defter([("BTCUSDT", "BINANCE", 1.0)])
        self._baglanti(monkeypatch, [])
        assert all(r["location"] == "METAMASK" for r in cx.compare_with_ledger()["rows"])


# =====================================================================
# BÖLÜM 6 — API UÇLARI
# =====================================================================
class TestApi:

    def test_baglanti_listesi_ucu(self, client):
        r = client.get("/api/connections")
        assert r.status_code == 200
        govde = r.json()
        assert "connections" in govde and "chains" in govde

    def test_kasa_durumu_ucu(self, client):
        r = client.get("/api/vault/status")
        assert r.status_code == 200
        assert r.json()["unlocked"] is False

    def test_kilitli_kasaya_yazilamaz(self, client):
        r = client.post("/api/vault/secret/etherscan_api_key", json={"value": "X"})
        assert r.status_code == 423

    def test_gecersiz_adres_400_doner(self, client):
        r = client.post("/api/connections",
                        json={"location": "METAMASK", "chain": "ethereum",
                              "address": "bozuk"})
        assert r.status_code == 400

    def test_olmayan_baglanti_silinemez(self, client):
        assert client.delete("/api/connections/c99").status_code == 404

    def test_karsilastirma_ucu_salt_okunurdur(self, client):
        r = client.get("/api/connections/reconcile")
        assert r.status_code == 200 and r.json()["read_only"] is True

    def test_deneme_ucu_kaydetme_ucuna_dusmez(self, client, monkeypatch):
        """
        GERÇEK HATA: `{location:path}` açgözlü olduğu için `/PHANTOM/test`
        isteği KAYDETME ucuna düşüyordu. Kullanıcı "Önce Dene" derken farkında
        olmadan `PHANTOM/TEST` adında sahte bir bağlantı kaydediliyor, ekranda
        ise sebepsiz bir hata görünüyordu.
        """
        monkeypatch.setattr(cx, "read_solana", lambda adres: ([], []))
        adres = "So11111111111111111111111111111111111111112"
        r = client.post("/api/connections/test",
                        json={"location": "PHANTOM", "chain": "solana",
                              "address": adres})
        assert r.status_code == 200
        # Deneme KAYDETMEZ.
        assert cx.list_connections() == {}
        # Cevap deneme sonucudur; `ok` alanı taşımalı ki arayüz yorumlayabilsin.
        assert "ok" in r.json()

    def test_egik_cizgili_konum_kaydedilemez(self):
        """Yol çözümlemesi yanlış uca düşerse kayıt sessizce oluşmasın."""
        with pytest.raises(ValueError, match="eğik çizgi"):
            cx.save_connection("PHANTOM/TEST", {
                "chain": "solana",
                "address": "So11111111111111111111111111111111111111112"})


# =====================================================================
# BÖLÜM 7 — SOLANA SPAM TOKENLARI
# =====================================================================
class TestSpamTokenlari:
    """
    Gerçek bir Solana cüzdanında 134 bakiye okundu ve büyük kısmı istenmeden
    gönderilmiş spam'di. Gizlemek yalan olurdu; hepsini eşit göstermek ise
    gerçek farkları gürültüde kaybederdi. Çözüm: işaretle, katla, açılabilir bırak.
    """

    def _oku(self, monkeypatch, mintler, eslem):
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p:
                            {"value": 0} if m == "getBalance" else
                            {"value": [{"account": {"data": {"parsed": {"info": {
                                "mint": mint, "tokenAmount": {"uiAmount": 1.0}}}}}}
                                for mint in mintler]})
        monkeypatch.setattr(cx, "_solana_symbols", lambda: eslem)
        return cx.read_solana("So11111111111111111111111111111111111111112")

    def test_dogrulanmamis_token_isaretlenir(self, monkeypatch):
        bakiyeler, uyarilar = self._oku(monkeypatch, ["IyiMint", "SpamMint"],
                                        {"IyiMint": "USDC"})
        durum = {b["asset"]: b["verified"] for b in bakiyeler}
        assert durum["USDC"] is True
        assert any(v is False for v in durum.values())
        # Spam bildirimi BİLGİdir, eksiklik değil: bu tokenlar okundu ve
        # tabloda duruyorlar. "Eksik okundu" saymak yanlış alarm üretiyordu.
        spam = [n for n in uyarilar if "spam" in n["message"]]
        assert spam and spam[0]["level"] == "info"
        assert cx.is_incomplete(uyarilar) is False

    def test_spam_satirlari_sayimdan_dislanir(self, monkeypatch):
        """130 spam token '130 fark var' diye görünmemeli."""
        cx.save_connection("PHANTOM", {
            "chain": "solana", "address": "So11111111111111111111111111111111111111112"})
        monkeypatch.setattr(cx, "read_connection", lambda k, spec=None: {
            "id": k, "location": "PHANTOM", "ok": True, "chain": "solana",
            "address": "So1111", "notes": [], "balances": [
                {"asset": "SOL", "qty": 2.0, "verified": True},
                {"asset": "SPAM1", "qty": 1.0, "verified": False},
                {"asset": "SPAM2", "qty": 1.0, "verified": False},
            ]})
        rapor = cx.compare_with_ledger()
        assert rapor["spam_count"] == 2
        assert sum(rapor["status_counts"].values()) == 1      # yalnızca SOL
        assert len(rapor["rows"]) == 3                        # ama satır silinmedi

    def test_defterdeki_varlik_dogrulanmamis_olsa_da_gizlenmez(self, monkeypatch):
        """
        Kullanıcının defterine girdiği bir coin, tanınmış listede olmasa bile
        onun için anlamlıdır. 'Doğrulanmamış' spam demek değildir.
        """
        data = dm.load_portfolio()
        data["transactions"] = [{
            "id": 1, "date": "2026-01-01", "coin": "SCMUSDT", "exchange": "PHANTOM",
            "qty": 500.0, "cost": 1.0, "status": dm.ACTIVE_STATUS}]
        dm.save_portfolio(data)
        cx.save_connection("PHANTOM", {
            "chain": "solana", "address": "So11111111111111111111111111111111111111112"})
        monkeypatch.setattr(cx, "read_connection", lambda k, spec=None: {
            "id": k, "location": "PHANTOM", "ok": True, "chain": "solana",
            "address": "So1111", "notes": [], "balances": [
                {"asset": "SCM", "qty": 500.0, "verified": False}]})
        rapor = cx.compare_with_ledger()
        satir = next(r for r in rapor["rows"] if r["asset"] == "SCM")
        assert satir["likely_spam"] is False
        assert rapor["spam_count"] == 0


# =====================================================================
# BÖLÜM 8 — ÜCRETLİ ZİNCİRLER VE ELLE TOKEN TANIMI (FAZ F6c)
# =====================================================================
def _abi_string(metin):
    """`symbol()` dönüşünün dinamik string kodlaması: offset, uzunluk, veri."""
    ham = metin.encode("utf-8")
    return ("0x"
            + f"{32:064x}"
            + f"{len(ham):064x}"
            + ham.hex().ljust(64, "0"))


def _kontrat_rpc(sembol_ham, ondalik=18, bakiye=None):
    """`decimals()` / `symbol()` / `balanceOf()` çağrılarını ayırt eden sahte RPC."""
    def sahte(url, method, params):
        if method == "eth_getBalance":
            return "0x0"
        veri = params[0]["data"]
        if veri.startswith("0x313ce567"):
            return hex(ondalik)
        if veri.startswith("0x95d89b41"):
            return sembol_ham
        return hex(bakiye if bakiye is not None else 0)
    return sahte


class TestUcretliZincirVeElleToken:
    """
    GERÇEK HATA: kullanıcıya "ücretsiz Etherscan anahtarı tüm EVM zincirlerinde
    çalışır" dendi. Anahtar her zincirde KABUL ediliyor ama ücretsiz plan hepsini
    KAPSAMIYOR; BNB Chain isteği "Free API access is not supported for this
    chain" diye döndü ve kullanıcının tokenları yine gelmedi.

    Çözüm ücretli plan değil: bakiye okumak zaten ücretsiz. Eksik olan tek şey
    "hangi tokenlara sahipsin" bilgisiydi ve onu kullanıcı zaten biliyor.
    """

    def test_zincir_listesi_kesif_kapsamini_soyler(self):
        zincirler = {z["id"]: z for z in cx.supported_chains()}
        assert zincirler["ethereum"]["discovery"] == "free"
        assert zincirler["bsc"]["discovery"] == "paid"
        assert zincirler["solana"]["discovery"] == "builtin"

    def test_ucretli_zincirde_kesif_denenmez(self, monkeypatch):
        """Başarısız olacağı bilinen istek atılmaz; sebebi kullanıcıya söylenir."""
        def patlat(*a, **k):
            raise AssertionError("ücretli zincirde Etherscan'a gidilmemeliydi")

        monkeypatch.setattr(cx, "_etherscan", patlat)
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p: hex(int(1e18)))
        bakiyeler, notlar = cx.read_evm("bsc", "0x" + "11" * 20, api_key="ANAHTAR")
        assert [b["asset"] for b in bakiyeler] == ["BNB"]
        uyari = next(n for n in notlar if n["level"] == "warn")
        assert "ÜCRETLİ" in uyari["message"]
        assert "kontrat adresiyle" in uyari["message"]

    def test_elle_token_tanimliysa_kesif_eksikligi_alarm_degildir(self, monkeypatch):
        """
        Kullanıcı tokenlarını elle tanımlamışsa keşfin kapalı olması bir
        eksiklik değil, bilinçli tercihtir. Alarm üretmek yanlış olurdu.
        """
        monkeypatch.setattr(cx, "_rpc", _kontrat_rpc(_abi_string("CPL"),
                                                     bakiye=7 * 10 ** 18))
        bakiyeler, notlar = cx.read_evm(
            "bsc", "0x" + "11" * 20, api_key="ANAHTAR",
            tokens=[{"contract": "0x" + "cc" * 20, "symbol": "CPL", "decimals": 18}])
        assert {b["asset"] for b in bakiyeler} == {"CPL"}
        assert bakiyeler[0]["qty"] == pytest.approx(7.0)
        assert cx.is_incomplete(notlar) is False

    def test_elle_tanim_kesfin_yerine_gecmez_eklenir(self, monkeypatch):
        """
        Önceki sürümde keşif başarılı olduğunda elle tanımlananlar sessizce
        düşüyordu: keşif penceresi dışında kalmış bir tokenı kullanıcı elle
        eklemiş olsa bile göremezdi.
        """
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p:
                            "0x0" if m == "eth_getBalance" else hex(10 ** 18))
        monkeypatch.setattr(cx, "_etherscan", lambda cid, params, key: [
            {"contractAddress": "0x" + "dd" * 20, "tokenSymbol": "ARB",
             "tokenDecimal": "18"}])
        bakiyeler, _ = cx.read_evm(
            "arbitrum", "0x" + "11" * 20, api_key="ANAHTAR",
            tokens=[{"contract": "0x" + "ee" * 20, "symbol": "ESKI", "decimals": 18}])
        assert {b["asset"] for b in bakiyeler} == {"ARB", "ESKI"}

    def test_bakiyesi_sifir_cikan_elle_token_soylenir(self, monkeypatch):
        """Kullanıcı 'ekledim ama gelmedi' demesin: sıfır bakiye yutulmaz."""
        monkeypatch.setattr(cx, "_rpc", _kontrat_rpc(_abi_string("CPL"), bakiye=0))
        _, notlar = cx.read_evm(
            "bsc", "0x" + "11" * 20,
            tokens=[{"contract": "0x" + "cc" * 20, "symbol": "CPL", "decimals": 18}])
        assert any("bakiyesi yok" in n["message"] for n in notlar)

    def test_token_bilgisi_zincirden_okunur(self, monkeypatch):
        """Kullanıcıdan ondalık hane istemek anlamsız; zincir zaten biliyor."""
        monkeypatch.setattr(cx, "_rpc", _kontrat_rpc(_abi_string("cpl"), ondalik=8))
        bilgi = cx.evm_token_info("bsc", "0x" + "CC" * 20)
        assert bilgi == {"contract": "0x" + "cc" * 20, "symbol": "CPL",
                         "decimals": 8}

    def test_eski_bytes32_sembol_de_okunur(self, monkeypatch):
        """Eski tokenların bir kısmı `symbol()` için bytes32 döndürür."""
        ham = "0x" + b"OLD".hex().ljust(64, "0")
        monkeypatch.setattr(cx, "_rpc", _kontrat_rpc(ham, ondalik=18))
        assert cx.evm_token_info("ethereum", "0x" + "cc" * 20)["symbol"] == "OLD"

    def test_token_olmayan_adres_reddedilir(self, monkeypatch):
        """Yanlış zincir seçmek en olası hata; sessizce sıfır göstermeyelim."""
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p: "0x")
        with pytest.raises(ValueError, match="ERC-20"):
            cx.evm_token_info("bsc", "0x" + "cc" * 20)

    def test_sembol_kontrat_adresi_yerine_girilemez(self):
        with pytest.raises(ValueError, match="kontrat adresini girin"):
            cx.evm_token_info("bsc", "CPL")

    def test_solanada_elle_token_tanimlanmaz(self):
        with pytest.raises(ValueError, match="elle token tanımlanamaz"):
            cx.evm_token_info("solana", "0x" + "cc" * 20)

    def test_bozuk_ondalik_reddedilir(self):
        _, hata = cx.validate_connection({
            "chain": "bsc", "address": "0x" + "11" * 20,
            "tokens": [{"contract": "0x" + "cc" * 20, "symbol": "X", "decimals": 99}]})
        assert "0-36" in hata

    def test_ayni_token_iki_kez_sayilmaz(self):
        temiz, hata = cx.validate_connection({
            "chain": "bsc", "address": "0x" + "11" * 20,
            "tokens": [{"contract": "0x" + "CC" * 20, "symbol": "X", "decimals": 18},
                       {"contract": "0x" + "cc" * 20, "symbol": "X", "decimals": 18}]})
        assert hata is None and len(temiz["tokens"]) == 1

    def test_token_sayisi_sinirlidir(self):
        cok = [{"contract": "0x" + f"{i:040x}", "symbol": "X", "decimals": 18}
               for i in range(cx.MAX_MANUAL_TOKENS + 1)]
        _, hata = cx.validate_connection({
            "chain": "bsc", "address": "0x" + "11" * 20, "tokens": cok})
        assert str(cx.MAX_MANUAL_TOKENS) in hata

    def test_elle_tokenlar_kayitta_kalir(self):
        kayit = cx.save_connection("METAMASK", {
            "chain": "bsc", "address": "0x" + "11" * 20,
            "tokens": [{"contract": "0x" + "cc" * 20, "symbol": "CPL",
                        "decimals": 18}]})
        kimlik = list(kayit)[0]
        saklanan = cx.list_connections()[kimlik]["tokens"]
        assert saklanan == [{"contract": "0x" + "cc" * 20, "symbol": "CPL",
                             "decimals": 18}]

    def test_okuma_elle_token_sayisini_bildirir(self, monkeypatch):
        monkeypatch.setattr(cx, "_rpc", _kontrat_rpc(_abi_string("CPL"),
                                                     bakiye=10 ** 18))
        kayit = cx.save_connection("METAMASK", {
            "chain": "bsc", "address": "0x" + "11" * 20,
            "tokens": [{"contract": "0x" + "cc" * 20, "symbol": "CPL",
                        "decimals": 18}]})
        sonuc = cx.read_connection(list(kayit)[0])
        assert sonuc["token_count"] == 1

    def test_token_bilgisi_ucu(self, client, monkeypatch):
        monkeypatch.setattr(cx, "_rpc", _kontrat_rpc(_abi_string("CPL"), ondalik=18))
        r = client.post("/api/connections/token-info",
                        json={"chain": "bsc", "contract": "0x" + "cc" * 20})
        assert r.status_code == 200
        assert r.json()["token"]["symbol"] == "CPL"
        # Bu uç hiçbir şey KAYDETMEZ.
        assert cx.list_connections() == {}

    def test_token_bilgisi_ucu_bozuk_adresi_400_ile_reddeder(self, client):
        r = client.post("/api/connections/token-info",
                        json={"chain": "bsc", "contract": "CPL"})
        assert r.status_code == 400


class TestNotSeviyeleri:
    """
    GERÇEK HATA: arayüz her notu "eksik okundu" saydı. Kullanıcı üç bağlantının
    eksik okunduğunu sandı; ikisi Solana'nın spam token BİLGİSİYDİ, gerçekte
    eksik olan bir taneydi. Alarmı şişirmek gerçek sorunu gürültüde kaybettirir.
    """

    def test_bilgi_notu_eksiklik_sayilmaz(self):
        assert cx.is_incomplete([{"level": "info", "message": "x"}]) is False

    def test_uyari_ve_hata_eksikliktir(self):
        assert cx.is_incomplete([{"level": "warn", "message": "x"}]) is True
        assert cx.is_incomplete([{"level": "error", "message": "x"}]) is True

    def test_bos_not_listesi_eksiklik_degildir(self):
        assert cx.is_incomplete([]) is False

    def test_raporda_eksik_bayragi_tasinir(self, monkeypatch):
        cx.save_connection("PHANTOM", {
            "chain": "solana",
            "address": "So11111111111111111111111111111111111111112"})
        monkeypatch.setattr(cx, "read_connection", lambda k, spec=None: {
            "id": k, "location": "PHANTOM", "ok": True, "chain": "solana",
            "address": "So1111", "balances": [],
            "notes": [{"level": "info", "message": "spam"}],
            "incomplete": False, "token_count": 0})
        rapor = cx.compare_with_ledger()
        kayit = list(rapor["connections"].values())[0]
        assert kayit["incomplete"] is False
        assert kayit["notes"][0]["level"] == "info"


# =====================================================================
# BÖLÜM 9 — KİLİTLİ KASA, PARALEL OKUMA VE TARİHLİ KAYIT (FAZ F6a)
# =====================================================================
class TestKilitliKasaAyrimi:
    """
    GERÇEK HATA: kullanıcı Etherscan anahtarını girdi, uygulamayı yeniden
    başlattı ve tokenları yine gelmedi. Sebep anahtarın yokluğu değil, kasanın
    KİLİTLİ olmasıydı — çözme anahtarı diskte durmuyor. Sistem ikisini aynı
    cümleyle anlatınca kullanıcı zaten yapmış olduğu işi (anahtar girmeyi)
    tekrar yapmaya yönlendiriliyordu.
    """

    def test_anahtar_yokken_mesaj_anahtar_ister(self, monkeypatch):
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p: hex(int(1e18)))
        _, notlar = cx.read_evm("ethereum", "0x" + "11" * 20, key_stored=False)
        mesaj = " ".join(n["message"] for n in notlar)
        assert "etherscan.io" in mesaj
        assert "kasa kilitli" not in mesaj.lower()

    def test_anahtar_varken_kilitliyse_kasayi_ac_der(self, monkeypatch):
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p: hex(int(1e18)))
        _, notlar = cx.read_evm("ethereum", "0x" + "11" * 20, key_stored=True)
        mesaj = " ".join(n["message"] for n in notlar)
        assert "kasa kilitli" in mesaj.lower()
        assert "Kasayı Aç" in mesaj

    def test_okuma_kasadaki_anahtari_kilitliyken_kullanmaz(self, monkeypatch):
        """Kilitli kasadan sır okunamaz; okuma yine de yapılır, eksik olduğu söylenir."""
        _pin_kur("4242")
        kv.unlock("4242")
        kv.put(cx.ETHERSCAN_KEY_NAME, "GIZLI")
        kv.lock()
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p: hex(int(1e18)))
        monkeypatch.setattr(cx, "_etherscan", lambda *a, **k:
                            pytest.fail("kilitli kasayla Etherscan'a gidilmemeliydi"))
        kayit = cx.save_connection("METAMASK", {
            "chain": "ethereum", "address": "0x" + "11" * 20})
        sonuc = cx.read_connection(list(kayit)[0])
        assert sonuc["ok"] is True and sonuc["incomplete"] is True
        assert any("kasa kilitli" in n["message"].lower() for n in sonuc["notes"])

    def test_karsilastirma_raporu_kasa_durumunu_tasir(self, client):
        """Arayüz uyarıyı okumadan ÖNCE verebilsin diye rapora ekli."""
        govde = client.get("/api/connections/reconcile").json()
        assert "vault" in govde
        assert govde["vault"]["unlocked"] is False
        assert "provider_key_set" in govde["vault"]


class TestParalelOkuma:
    """
    Kullanıcı "okunuyor süreci uzun" dedi ve haklıydı: her token için bir tur
    ağ gecikmesi sırayla bekleniyordu. İşin tamamı ağ beklemesi olduğu için
    paralel okumak doğru çözüm.
    """

    def test_sonuc_sirasi_korunur(self):
        ogeler = list(range(20))
        sonuc = cx._paralel(ogeler, lambda x: x * 2)
        assert [o for o, _, _ in sonuc] == ogeler
        assert [s for _, s, _ in sonuc] == [x * 2 for x in ogeler]

    def test_tek_ogenin_hatasi_digerlerini_dusurmez(self):
        def is_fn(x):
            if x == 2:
                raise RuntimeError("patladı")
            return x

        sonuc = dict((o, (s, h)) for o, s, h in cx._paralel([1, 2, 3], is_fn))
        assert sonuc[1][0] == 1 and sonuc[1][1] is None
        assert sonuc[2][0] is None and "patladı" in str(sonuc[2][1])
        assert sonuc[3][0] == 3

    def test_bos_liste_havuz_acmaz(self):
        assert cx._paralel([], lambda x: x) == []

    def test_token_bakiyeleri_paralel_okunur(self, monkeypatch):
        """Sıralı olsaydı 12 tokenlık okuma 12 tur gecikme beklerdi."""
        import threading
        esanli, tepe, kilit = [0], [0], threading.Lock()

        def yavas_rpc(url, m, p):
            if m == "eth_getBalance":
                return "0x0"
            with kilit:
                esanli[0] += 1
                tepe[0] = max(tepe[0], esanli[0])
            time.sleep(0.02)
            with kilit:
                esanli[0] -= 1
            return hex(10 ** 18)

        monkeypatch.setattr(cx, "_rpc", yavas_rpc)
        tokenlar = [{"contract": "0x" + f"{i:040x}", "symbol": f"T{i}",
                     "decimals": 18} for i in range(12)]
        bakiyeler, _ = cx.read_evm("bsc", "0x" + "11" * 20, tokens=tokenlar)
        assert len(bakiyeler) == 12
        assert tepe[0] > 1, "token bakiyeleri sırayla okunmuş"

    def test_baglantilar_paralel_okunur(self, monkeypatch):
        import threading
        esanli, tepe, kilit = [0], [0], threading.Lock()

        def sahte(k, spec=None):
            with kilit:
                esanli[0] += 1
                tepe[0] = max(tepe[0], esanli[0])
            time.sleep(0.03)
            with kilit:
                esanli[0] -= 1
            return {"id": k, "location": (spec or {}).get("location"), "ok": True,
                    "chain": (spec or {}).get("chain"), "balances": [],
                    "notes": [], "incomplete": False}

        for i, zincir in enumerate(["ethereum", "bsc", "polygon", "arbitrum"]):
            cx.save_connection("METAMASK", {
                "chain": zincir, "address": "0x" + f"{i:040x}"})
        monkeypatch.setattr(cx, "read_connection", sahte)
        okumalar = cx.read_all()
        assert len(okumalar) == 4
        assert tepe[0] > 1, "bağlantılar sırayla okunmuş"

    def test_beklenmedik_istisna_yutulmaz(self, monkeypatch):
        """`read_connection` kendi hatalarını rapora çevirir; buraya düşen bir
        istisna beklenmedik demektir ve sessizce kaybolmamalı."""
        cx.save_connection("METAMASK", {
            "chain": "ethereum", "address": "0x" + "11" * 20})
        cx.save_connection("PHANTOM", {
            "chain": "solana",
            "address": "So11111111111111111111111111111111111111112"})

        def sahte(k, spec=None):
            if (spec or {}).get("chain") == "solana":
                raise RuntimeError("beklenmedik")
            return {"id": k, "location": "METAMASK", "ok": True,
                    "chain": "ethereum", "balances": [], "notes": [],
                    "incomplete": False}

        monkeypatch.setattr(cx, "read_connection", sahte)
        okumalar = cx.read_all()
        patlayan = [o for o in okumalar.values() if not o["ok"]]
        assert len(patlayan) == 1
        assert patlayan[0]["incomplete"] is True
        assert "beklenmedik" in patlayan[0]["notes"][0]["message"]


class TestDeftereEkleAkisi:
    """
    FAZ F6a. Zincirde duran ama deftere girmemiş varlık tek tıkla kaydedilir —
    ama OTOMATİK DEĞİL. Zincir miktarı bilir, maliyeti bilmez; sıfır maliyetle
    yazmak %100 kâr uydurmak olurdu (F5b'de düzeltilen hatanın aynısı).

    Sunucu tarafında yeni bir uç yok: kayıt normal işlem ucundan geçiyor.
    Buradaki testler o akışın dayandığı garantileri koruyor.
    """

    def test_cuzdan_konumuna_usdt_eklenmez(self, client):
        """
        BINANCE'e `BNB` yazınca `BNBUSDT` olur, çünkü orada işlem çifti vardır.
        Cüzdanda çift yoktur; sembolü bozmak zincirle karşılaştırmayı kırardı.
        """
        r = client.post("/api/transactions", json={
            "coin": "BNB", "exchange": "METAMASK", "qty": 0.05, "cost": 640.0})
        assert r.status_code == 200
        tx = dm.load_portfolio()["transactions"][-1]
        assert tx["coin"] == "BNB"
        assert tx["exchange"] == "METAMASK"

    def test_gecmis_tarihle_kayit_yapilabilir(self, client):
        """
        Arayüzde tarih alanı yoktu ve her kayıt BUGÜNÜN tarihiyle açılıyordu.
        Cüzdandaki varlık genelde geçmişte alınmıştır; FIFO tarihe bağlı
        olduğu için yanlış tarih sonraki satışların maliyetini bozar.
        """
        r = client.post("/api/transactions", json={
            "coin": "BNB", "exchange": "METAMASK", "qty": 0.05,
            "cost": 640.0, "date": "2025-11-03"})
        assert r.status_code == 200
        assert dm.load_portfolio()["transactions"][-1]["date"] == "2025-11-03"

    def test_tarih_bos_birakilinca_bugun_kullanilir(self, client):
        from datetime import datetime
        client.post("/api/transactions", json={
            "coin": "BNB", "exchange": "METAMASK", "qty": 0.05, "cost": 640.0})
        assert (dm.load_portfolio()["transactions"][-1]["date"]
                == datetime.now().strftime("%Y-%m-%d"))

    def test_ekleme_sonrasi_satir_eslesmeye_doner(self, client, monkeypatch):
        """Kullanıcı işin bittiğini görmeli: satır 'Zincirde var'dan çıkmalı."""
        cx.save_connection("METAMASK", {
            "chain": "bsc", "address": "0x" + "11" * 20})
        monkeypatch.setattr(cx, "read_connection", lambda k, spec=None: {
            "id": k, "location": "METAMASK", "ok": True, "chain": "bsc",
            "address": "0x11", "notes": [], "incomplete": False,
            "balances": [{"asset": "BNB", "qty": 0.050404}]})

        once = cx.compare_with_ledger()["rows"][0]
        assert once["status"] == "only_chain"

        client.post("/api/transactions", json={
            "coin": "BNB", "exchange": "METAMASK", "qty": 0.050404,
            "cost": 640.0, "date": "2025-11-03"})

        sonra = cx.compare_with_ledger()["rows"][0]
        assert sonra["status"] == "match"
        assert sonra["ledger_qty"] == pytest.approx(0.050404)


class TestSembolDuzeltmesiSonrasiKarsilastirma:
    """
    F6d'nin sembol düzeltmesi zincir karşılaştırmasını bozmamalı: `BNBUSDT`
    kırpılıp `BNB` olduktan sonra da defter satırı zincirle eşleşmeli.
    """

    def test_ek_kirpildiktan_sonra_da_eslesir(self, monkeypatch):
        data = dm.load_portfolio()
        data["transactions"] = [{
            "id": 1, "date": "2026-01-01", "coin": "BNBUSDT",
            "exchange": "METAMASK", "qty": 0.05, "cost": 690.0,
            "status": dm.ACTIVE_STATUS, "type": "TRANSFER"}]
        dm.save_portfolio(data)
        assert dm.normalize_wallet_symbols()

        cx.save_connection("METAMASK", {"chain": "bsc", "address": "0x" + "11" * 20})
        monkeypatch.setattr(cx, "read_connection", lambda k, spec=None: {
            "id": k, "location": "METAMASK", "ok": True, "chain": "bsc",
            "address": "0x11", "notes": [], "incomplete": False,
            "balances": [{"asset": "BNB", "qty": 0.05}]})
        satir = next(r for r in cx.compare_with_ledger()["rows"]
                     if r["asset"] == "BNB")
        assert satir["status"] == "match"


# =====================================================================
# 10) FAZ F6e — YANLIŞ KONUM, KONUM DÜZELTME, EVM SPAM SÜZGECİ
# =====================================================================
def _tek_okuma(konum, zincir, bakiyeler):
    """Tek bağlantılık sahte okuma üretir."""
    return {"id": "c1", "location": konum, "ok": True, "chain": zincir,
            "address": "0x11", "notes": [], "incomplete": False,
            "balances": bakiyeler}


class TestYanlisKonumTespiti:
    """
    Aynı varlık bir konumda `only_ledger`, başka bir konumda `only_chain` ve
    miktarlar yakınsa bu iki ayrı eksiklik değil, YANLIŞ RAFA YAZILMIŞ TEK bir
    varlıktır.

    Ayrım kozmetik değil: sistem bunu görmezse zincir tarafında "+ Deftere
    Ekle" düğmesi gösterir, kullanıcı basar ve varlığını İKİ KEZ sayar.
    Gerçek bir kullanımda buna ramak kalmıştı; kullanıcı düğmeye basmadan
    kendisi fark etti.
    """

    def _kur(self, monkeypatch, defter_qty, zincir_qty):
        data = dm.load_portfolio()
        data["transactions"] = [{
            "id": 1, "date": "2026-01-01", "coin": "ETHUSDT",
            "exchange": "PHANTOM", "qty": defter_qty, "cost": 2400.0,
            "status": dm.ACTIVE_STATUS, "type": "TRANSFER"}]
        dm.save_portfolio(data)
        okumalar = {
            "c1": _tek_okuma("PHANTOM", "solana", []),
            "c2": _tek_okuma("METAMASK", "ethereum",
                             [{"asset": "ETH", "qty": zincir_qty}]),
        }
        monkeypatch.setattr(cx, "read_all", lambda only_enabled=True: okumalar)
        return cx.compare_with_ledger()

    def test_yakin_miktarlar_yanlis_konum_sayilir(self, monkeypatch):
        rapor = self._kur(monkeypatch, 0.00219, 0.00219)
        defter_satir = next(r for r in rapor["rows"] if r["location"] == "PHANTOM")
        zincir_satir = next(r for r in rapor["rows"] if r["location"] == "METAMASK")

        assert defter_satir["status"] == "only_ledger"
        assert zincir_satir["status"] == "only_chain"
        # İki satır da işaretlenmeli ve ikisi de AYNI doğru konumu göstermeli.
        assert defter_satir["misplaced"]["role"] == "ledger"
        assert zincir_satir["misplaced"]["role"] == "chain"
        assert defter_satir["misplaced"]["correct_location"] == "METAMASK"
        assert zincir_satir["misplaced"]["correct_location"] == "METAMASK"
        assert zincir_satir["misplaced"]["ledger_location"] == "PHANTOM"
        # Düzeltilecek kaydın kimliği taşınıyor ki arayüz onu düzeltebilsin.
        assert defter_satir["misplaced"]["tx_ids"] == [1]
        # İki satır ama TEK sorun.
        assert rapor["misplaced_count"] == 1

    def test_uzak_miktarlar_eslenmez(self, monkeypatch):
        """
        Miktarlar birbirinden uzaksa bu yanlış konum değildir. Zorlama bir
        eşleşme, gerçek bir eksiği gizlerdi.
        """
        rapor = self._kur(monkeypatch, 0.00219, 5.0)
        for r in rapor["rows"]:
            assert r["misplaced"] is None
        assert rapor["misplaced_count"] == 0

    def test_yanlis_konumda_deftere_ekleme_onerilmez(self, monkeypatch):
        """
        Arayüzün `chainAddableQty` kuralının sunucu tarafındaki dayanağı:
        işaretli satır ekleme adayı olmamalı. Bu testin koruduğu şey tam
        olarak çift sayma tuzağıdır.
        """
        rapor = self._kur(monkeypatch, 0.00219, 0.00219)
        zincir_satir = next(r for r in rapor["rows"] if r["location"] == "METAMASK")
        assert zincir_satir["chain_qty"] > 0          # eklenebilir görünüyor
        assert zincir_satir["misplaced"] is not None  # ama eklenmemeli


class TestKonumDuzeltme:
    """`relocate_asset`: yanlış yazılmış kaydı düzeltir, transfer üretmez."""

    def _defter(self, kayitlar):
        data = dm.load_portfolio()
        data["transactions"] = kayitlar
        dm.save_portfolio(data)

    def test_konum_ve_sembol_birlikte_duzelir(self):
        self._defter([{"id": 1, "date": "2026-01-01", "coin": "SOLUSDT",
                       "exchange": "PHANTOM", "qty": 0.08, "cost": 93.0,
                       "status": dm.ACTIVE_STATUS}])
        sonuc = dm.relocate_asset("SOL", "PHANTOM", "METAMASK")
        assert sonuc["count"] == 1
        tx = dm.load_portfolio()["transactions"][0]
        assert tx["exchange"] == "METAMASK"
        assert tx["coin"] == "SOL"          # cüzdanda çift yazımı olmaz

    def test_borsaya_tasinirsa_cift_yazimi_geri_gelir(self):
        self._defter([{"id": 1, "date": "2026-01-01", "coin": "SOL",
                       "exchange": "PHANTOM", "qty": 0.08, "cost": 93.0,
                       "status": dm.ACTIVE_STATUS}])
        dm.relocate_asset("SOL", "PHANTOM", "BINANCE")
        assert dm.load_portfolio()["transactions"][0]["coin"] == "SOLUSDT"

    def test_miktar_maliyet_tarih_degismez(self):
        self._defter([{"id": 1, "date": "2026-01-01", "coin": "ETHUSDT",
                       "exchange": "PHANTOM", "qty": 0.00219, "cost": 2420.0,
                       "status": dm.ACTIVE_STATUS, "notes": "elle yazıldı"}])
        dm.relocate_asset("ETH", "PHANTOM", "METAMASK")
        tx = dm.load_portfolio()["transactions"][0]
        assert tx["qty"] == 0.00219
        assert tx["cost"] == 2420.0
        assert tx["date"] == "2026-01-01"
        assert tx["notes"] == "elle yazıldı"

    def test_kapali_kayitlara_dokunulmaz(self):
        """
        Kapalı kayıt geçmişin kaydıdır; şimdi yeniden yazmak muhasebe izini
        bozar. Kullanıcının aktif tablosunu düzeltmek yeterlidir.
        """
        self._defter([
            {"id": 1, "coin": "ETHUSDT", "exchange": "PHANTOM", "qty": 1.0,
             "cost": 100.0, "status": "Kapandı / İzleme"},
            {"id": 2, "coin": "ETHUSDT", "exchange": "PHANTOM", "qty": 2.0,
             "cost": 100.0, "status": dm.ACTIVE_STATUS},
        ])
        sonuc = dm.relocate_asset("ETH", "PHANTOM", "METAMASK")
        assert sonuc["count"] == 1
        kayitlar = {t["id"]: t for t in dm.load_portfolio()["transactions"]}
        assert kayitlar[1]["exchange"] == "PHANTOM"      # kapalı: dokunulmadı
        assert kayitlar[2]["exchange"] == "METAMASK"

    def test_ayni_konuma_tasima_reddedilir(self):
        self._defter([{"id": 1, "coin": "ETH", "exchange": "METAMASK",
                       "qty": 1.0, "cost": 100.0, "status": dm.ACTIVE_STATUS}])
        with pytest.raises(ValueError):
            dm.relocate_asset("ETH", "METAMASK", "METAMASK")

    def test_kayit_yoksa_hata_verir(self):
        """Sessizce 'başarılı' demek, kullanıcıya olmayan bir iş yaptırırdı."""
        self._defter([])
        with pytest.raises(ValueError):
            dm.relocate_asset("ETH", "PHANTOM", "METAMASK")

    def test_birden_cok_lot_birlikte_tasinir(self):
        """Elle düzeltmeye göre asıl faydası bu: tekrarlayan el emeğini kaldırır."""
        self._defter([
            {"id": i, "coin": "ETHUSDT", "exchange": "PHANTOM", "qty": 1.0,
             "cost": 100.0, "status": dm.ACTIVE_STATUS} for i in (1, 2, 3)])
        assert dm.relocate_asset("ETH", "PHANTOM", "METAMASK")["count"] == 3
        assert all(t["exchange"] == "METAMASK"
                   for t in dm.load_portfolio()["transactions"])


class TestEvmSpamSuzgeci:
    """
    EVM tarafında kürasyonlu bir doğrulanmış-token listesi YOK. Bu yüzden
    olumlu sinyali olmayan token "spam" değil **"bilmiyorum"** sayılır.

    Ayrım şart: ikisi birleştirilseydi, Ethereum'da gerçek USDC tutan ve onu
    henüz deftere yazmamış bir kullanıcının tokenları spam diye katlanır,
    "+ Deftere Ekle" düğmesi de kaybolurdu — yani zincirden deftere ekleme
    özelliği ilk kullanımda çalışmaz hâle gelirdi.
    """

    def _kesif(self, monkeypatch, sembol="ACT"):
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p: "0x0"
                            if m == "eth_getBalance" else hex(7 * 10 ** 18))
        monkeypatch.setattr(cx, "_etherscan", lambda cid, params, key: [
            {"contractAddress": "0x" + "ab" * 20, "tokenSymbol": sembol,
             "tokenDecimal": "18"}])
        return cx.read_evm("arbitrum", "0x" + "11" * 20, api_key="ANAHTAR")

    def test_kesiften_gelen_bilinmeyen_token_isaretlenir(self, monkeypatch):
        bakiyeler, _ = self._kesif(monkeypatch)
        assert bakiyeler[0]["trust"] == cx.TRUST_UNKNOWN
        assert bakiyeler[0]["verified"] is False

    def test_elle_tanimlanan_token_dogrulanmis_sayilir(self, monkeypatch):
        """Kullanıcı kontratı kendi yazdıysa niyet açıktır."""
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p: "0x0"
                            if m == "eth_getBalance" else hex(7 * 10 ** 18))
        bakiyeler, _ = cx.read_evm(
            "bsc", "0x" + "11" * 20,
            tokens=[{"contract": "0x" + "ab" * 20, "symbol": "CPL",
                     "decimals": 18}])
        assert bakiyeler[0]["trust"] == cx.TRUST_VERIFIED

    def test_defterde_gecen_sembol_dogrulanmis_sayilir(self, monkeypatch):
        data = dm.load_portfolio()
        data["transactions"] = [{"id": 1, "coin": "ACTUSDT",
                                 "exchange": "BINANCE", "qty": 1.0,
                                 "cost": 1.0, "status": dm.ACTIVE_STATUS}]
        dm.save_portfolio(data)
        bakiyeler, _ = self._kesif(monkeypatch, sembol="ACT")
        assert bakiyeler[0]["trust"] == cx.TRUST_VERIFIED

    def test_elle_spam_isareti_her_seyi_ezer(self, monkeypatch):
        """Defterde geçse bile kullanıcı 'bu spam' diyebilmeli."""
        data = dm.load_portfolio()
        data["transactions"] = [{"id": 1, "coin": "ACTUSDT",
                                 "exchange": "BINANCE", "qty": 1.0,
                                 "cost": 1.0, "status": dm.ACTIVE_STATUS}]
        dm.save_portfolio(data)
        cx.set_token_mark("arbitrum", "0x" + "ab" * 20, cx.TOKEN_MARK_SPAM)
        bakiyeler, _ = self._kesif(monkeypatch, sembol="ACT")
        assert bakiyeler[0]["trust"] == cx.TRUST_UNLISTED

    def test_elle_gercek_isareti_her_seyi_ezer(self, monkeypatch):
        """Gerçek bir airdrop da başlangıçta dayanaksız görünür."""
        cx.set_token_mark("arbitrum", "0x" + "AB" * 20, cx.TOKEN_MARK_REAL)
        bakiyeler, _ = self._kesif(monkeypatch)
        assert bakiyeler[0]["trust"] == cx.TRUST_VERIFIED

    def test_isaret_kaldirilabilir(self, monkeypatch):
        cx.set_token_mark("arbitrum", "0x" + "ab" * 20, cx.TOKEN_MARK_REAL)
        cx.set_token_mark("arbitrum", "0x" + "ab" * 20, None)
        bakiyeler, _ = self._kesif(monkeypatch)
        assert bakiyeler[0]["trust"] == cx.TRUST_UNKNOWN

    def test_gecersiz_isaret_reddedilir(self):
        with pytest.raises(ValueError):
            cx.set_token_mark("bsc", "0x" + "ab" * 20, "belki")

    def test_yerel_para_her_zaman_dogrulanmistir(self, monkeypatch):
        """Kimse size sahte ETH gönderemez."""
        monkeypatch.setattr(cx, "_rpc", lambda url, m, p: hex(10 ** 18))
        bakiyeler, _ = cx.read_evm("ethereum", "0x" + "11" * 20)
        assert bakiyeler[0]["asset"] == "ETH"
        assert bakiyeler[0]["trust"] == cx.TRUST_VERIFIED


class TestGuvenDerecesiKarsilastirmada:
    """`unknown` GÖRÜNÜR kalır ama eklenmez; `unlisted` katlanır."""

    def _rapor(self, monkeypatch, trust):
        monkeypatch.setattr(cx, "read_all", lambda only_enabled=True: {
            "c1": _tek_okuma("METAMASK", "bsc", [
                {"asset": "ACT", "qty": 500.0, "contract": "0x" + "ab" * 20,
                 "chain": "bsc", "trust": trust,
                 "verified": trust == cx.TRUST_VERIFIED}])})
        return cx.compare_with_ledger()

    def test_bilinmeyen_token_katlanmaz_ama_incelenir(self, monkeypatch):
        rapor = self._rapor(monkeypatch, cx.TRUST_UNKNOWN)
        satir = next(r for r in rapor["rows"] if r["asset"] == "ACT")
        assert satir["needs_review"] is True
        assert satir["likely_spam"] is False      # GİZLENMİYOR
        assert rapor["review_count"] == 1
        assert "Bu gerçek" in satir["note"]

    def test_listede_olmayan_token_katlanir(self, monkeypatch):
        rapor = self._rapor(monkeypatch, cx.TRUST_UNLISTED)
        satir = next(r for r in rapor["rows"] if r["asset"] == "ACT")
        assert satir["likely_spam"] is True
        assert satir["needs_review"] is False
        assert rapor["spam_count"] == 1

    def test_kontrat_adresi_satira_tasinir(self, monkeypatch):
        """İşaret sembole değil kontrata bağlanır; sembol taklit edilebilir."""
        rapor = self._rapor(monkeypatch, cx.TRUST_UNKNOWN)
        satir = next(r for r in rapor["rows"] if r["asset"] == "ACT")
        assert satir["contracts"] == [{"chain": "bsc",
                                       "contract": "0x" + "ab" * 20}]

    def test_defterde_gecen_varlik_hicbir_zaman_katlanmaz(self, monkeypatch):
        """
        Defterinizde olan bir şey şüpheli olsa bile gizlenmez; kullanıcının
        varlığını kullanıcıdan saklamak en kötü seçenektir.
        """
        data = dm.load_portfolio()
        data["transactions"] = [{"id": 1, "coin": "ACT", "exchange": "METAMASK",
                                 "qty": 500.0, "cost": 0.01,
                                 "status": dm.ACTIVE_STATUS}]
        dm.save_portfolio(data)
        rapor = self._rapor(monkeypatch, cx.TRUST_UNLISTED)
        satir = next(r for r in rapor["rows"] if r["asset"] == "ACT")
        assert satir["likely_spam"] is False
        assert satir["needs_review"] is False


class TestF6eApiUclari:

    def test_konum_duzeltme_ucu(self, client):
        data = dm.load_portfolio()
        data["transactions"] = [{"id": 1, "coin": "SOLUSDT",
                                 "exchange": "PHANTOM", "qty": 0.08,
                                 "cost": 93.0, "status": dm.ACTIVE_STATUS}]
        dm.save_portfolio(data)
        r = client.post("/api/connections/relocate",
                        json={"asset": "SOL", "from_location": "PHANTOM",
                              "to_location": "METAMASK"})
        assert r.status_code == 200
        assert r.json()["count"] == 1
        assert dm.load_portfolio()["transactions"][0]["coin"] == "SOL"

    def test_bulunamayan_kayit_400_doner(self, client):
        r = client.post("/api/connections/relocate",
                        json={"asset": "XYZ", "from_location": "PHANTOM",
                              "to_location": "METAMASK"})
        assert r.status_code == 400

    def test_token_isaret_ucu(self, client):
        r = client.post("/api/connections/token-mark",
                        json={"chain": "bsc", "contract": "0x" + "ab" * 20,
                              "mark": "spam"})
        assert r.status_code == 200
        assert r.json()["token_marks"]["bsc:0x" + "ab" * 20] == "spam"

    def test_gecersiz_isaret_400_doner(self, client):
        r = client.post("/api/connections/token-mark",
                        json={"chain": "bsc", "contract": "0x" + "ab" * 20,
                              "mark": "belki"})
        assert r.status_code == 400

    def test_kontratsiz_isaret_400_doner(self, client):
        r = client.post("/api/connections/token-mark",
                        json={"chain": "bsc", "mark": "spam"})
        assert r.status_code == 400


# =====================================================================
# 11) KARŞILAŞTIRMADA PARASAL DEĞER
# =====================================================================
class TestSatirDegerleri:
    """
    Miktar tek başına "buna bakmalı mıyım?" sorusunu cevaplamıyor. Kullanıcı
    bunu doğrudan söyledi: *"0,002 dolarlık bir farkı görünce hiç bakmam."*
    Borsa bağlantısı geldikten sonra tablo ücret kırıntılarıyla dolduğu için
    bu bir konfor değil, tablonun kullanılabilirlik şartı.
    """

    def _rapor(self, monkeypatch, defter, zincir, coin="ETHUSDT",
               konum="METAMASK", varlik="ETH"):
        data = dm.load_portfolio()
        data["transactions"] = [{
            "id": 1, "date": "2026-01-01", "coin": coin, "exchange": konum,
            "qty": defter, "cost": 1000.0, "status": dm.ACTIVE_STATUS}]
        dm.save_portfolio(data)
        monkeypatch.setattr(cx, "read_all", lambda only_enabled=True: {
            "c1": _tek_okuma(konum, "ethereum",
                             [{"asset": varlik, "qty": zincir}])})
        return cx.compare_with_ledger()

    def test_miktarlarin_usd_karsiligi_yazilir(self, monkeypatch):
        rapor = self._rapor(monkeypatch, 1.0, 1.5)
        satir = next(r for r in rapor["rows"] if r["asset"] == "ETH")
        assert satir["price"] == pytest.approx(2000.0)
        assert satir["ledger_value"] == pytest.approx(2000.0)
        assert satir["chain_value"] == pytest.approx(3000.0)
        assert satir["diff_value"] == pytest.approx(1000.0)

    def test_eksi_fark_eksi_deger_uretir(self, monkeypatch):
        rapor = self._rapor(monkeypatch, 2.0, 1.0)
        satir = next(r for r in rapor["rows"] if r["asset"] == "ETH")
        assert satir["diff_value"] == pytest.approx(-2000.0)

    def test_nano_fiyat_bozulmadan_carpilir(self, monkeypatch):
        """CPL gibi 1e-9 fiyatlı tokenlar yuvarlamayla sıfıra düşmemeli."""
        rapor = self._rapor(monkeypatch, 1_000_000_000.0, 1_000_000_000.0,
                            coin="CPL", varlik="CPL")
        satir = next(r for r in rapor["rows"] if r["asset"] == "CPL")
        assert satir["ledger_value"] == pytest.approx(2.0)

    def test_fiyati_bilinmeyen_varlikta_deger_none(self, monkeypatch):
        """
        Sıfır değil `None`. Bilinmeyen değeri sıfır yazmak, gerçekten değerli
        bir varlığı "önemsiz" sanıp katlanmasına yol açardı — projede birkaç
        kez düzeltilen hatanın aynısı.
        """
        rapor = self._rapor(monkeypatch, 5.0, 7.0, coin="ZZZ", varlik="ZZZ")
        satir = next(r for r in rapor["rows"] if r["asset"] == "ZZZ")
        assert satir["price"] is None
        assert satir["ledger_value"] is None
        assert satir["diff_value"] is None

    def test_kaynaksiz_fiyat_bilinmiyor_sayilir(self, monkeypatch):
        """
        `no_source` bayraklı kayıt, değerleme için maliyete düşürülmüş bir
        VARSAYIMDIR — gerçek fiyat değildir. Burada ona güvenmek, kullanıcıya
        uydurma bir tutar göstermek olurdu.
        """
        from price_service import price_service
        monkeypatch.setattr(price_service, "prices", {
            "ZZZUSDT": {"price": 42.0, "no_source": True}})
        rapor = self._rapor(monkeypatch, 5.0, 7.0, coin="ZZZ", varlik="ZZZ")
        satir = next(r for r in rapor["rows"] if r["asset"] == "ZZZ")
        assert satir["price"] is None

    def test_fiyatsiz_varlik_fiyat_takibine_alinir(self, monkeypatch):
        """
        İzleme listesi yalnızca DEFTERDEN kuruluyordu. Borsa bağlantısı gelince
        bu bir boşluğa dönüştü: borsada durup deftere yazılmamış varlıklar hiç
        fiyat almıyordu — oysa "bunu eklemeye değer mi?" sorusu tam olarak o
        satırlarda soruluyor.
        """
        from price_service import price_service
        kaydedilen = []
        monkeypatch.setattr(price_service, "register_external_symbols",
                            lambda s: kaydedilen.extend(s))
        self._rapor(monkeypatch, 0.0, 7.0, coin="ZZZ", varlik="ZZZ")
        assert "ZZZ" in kaydedilen

    def test_spam_token_fiyat_takibine_alinmaz(self, monkeypatch):
        """Kimsenin umursamadığı token için ücretsiz uçları yormak anlamsız."""
        from price_service import price_service
        kaydedilen = []
        monkeypatch.setattr(price_service, "register_external_symbols",
                            lambda s: kaydedilen.extend(s))
        monkeypatch.setattr(cx, "read_all", lambda only_enabled=True: {
            "c1": _tek_okuma("PHANTOM", "solana", [
                {"asset": "SPAMCOIN", "qty": 500.0, "contract": "m1",
                 "chain": "solana", "trust": cx.TRUST_UNLISTED,
                 "verified": False}])})
        rapor = cx.compare_with_ledger()
        assert rapor["spam_count"] == 1
        assert "SPAMCOIN" not in kaydedilen

    def test_okunamayan_baglantida_zincir_degeri_none(self, monkeypatch):
        data = dm.load_portfolio()
        data["transactions"] = [{"id": 1, "coin": "ETHUSDT",
                                 "exchange": "METAMASK", "qty": 1.0,
                                 "cost": 1000.0, "status": dm.ACTIVE_STATUS}]
        dm.save_portfolio(data)
        monkeypatch.setattr(cx, "read_all", lambda only_enabled=True: {
            "c1": {"id": "c1", "location": "METAMASK", "ok": False,
                   "chain": "ethereum", "balances": [], "notes": [],
                   "incomplete": True}})
        satir = next(r for r in cx.compare_with_ledger()["rows"]
                     if r["asset"] == "ETH")
        assert satir["chain_value"] is None       # bilinmiyor
        assert satir["ledger_value"] == pytest.approx(2000.0)


class TestOnemeGoreSiralama:
    """
    Kullanıcının sorusu "hangi fark var?" değil "hangi fark ÖNEMLİ?".
    Parasal büyüklük sıralamayı belirler.
    """

    def _rapor(self, monkeypatch, kayitlar, bakiyeler):
        data = dm.load_portfolio()
        data["transactions"] = kayitlar
        dm.save_portfolio(data)
        monkeypatch.setattr(cx, "read_all", lambda only_enabled=True: {
            "c1": _tek_okuma("METAMASK", "ethereum", bakiyeler)})
        return cx.compare_with_ledger()

    def test_buyuk_fark_kucugun_ustunde_durur(self, monkeypatch):
        rapor = self._rapor(monkeypatch, [
            {"id": 1, "coin": "ETHUSDT", "exchange": "METAMASK", "qty": 1.0,
             "cost": 1.0, "status": dm.ACTIVE_STATUS},
            {"id": 2, "coin": "BTCUSDT", "exchange": "METAMASK", "qty": 1.0,
             "cost": 1.0, "status": dm.ACTIVE_STATUS},
        ], [{"asset": "ETH", "qty": 1.5},          # +0,5 ETH  = +$1.000
            {"asset": "BTC", "qty": 1.5}])         # +0,5 BTC  = +$50.000
        farklar = [r["asset"] for r in rapor["rows"] if r["status"] == "mismatch"]
        assert farklar == ["BTC", "ETH"]

    def test_fiyati_bilinmeyen_satir_grubun_sonuna_gider(self, monkeypatch):
        """
        En üste koymak gerçek parayı dust'ın altında bırakırdı; katlamak ise
        değerli ama fiyat kaynağı olmayan bir varlığı gizlemek olurdu. Doğru
        yer: görünür, ama parası bilinenlerin ardında.
        """
        rapor = self._rapor(monkeypatch, [
            {"id": 1, "coin": "ZZZ", "exchange": "METAMASK", "qty": 1.0,
             "cost": 1.0, "status": dm.ACTIVE_STATUS},
            {"id": 2, "coin": "ETHUSDT", "exchange": "METAMASK", "qty": 1.0,
             "cost": 1.0, "status": dm.ACTIVE_STATUS},
        ], [{"asset": "ZZZ", "qty": 2.0}, {"asset": "ETH", "qty": 1.5}])
        farklar = [r["asset"] for r in rapor["rows"] if r["status"] == "mismatch"]
        assert farklar == ["ETH", "ZZZ"]

    def test_durum_sirasi_paradan_once_gelir(self, monkeypatch):
        """
        Para sıralamayı grup İÇİNDE belirler, grupları değil. Küçük bir
        "fark var" satırı, büyük bir "eşleşiyor" satırının üstünde kalmalı.
        """
        rapor = self._rapor(monkeypatch, [
            {"id": 1, "coin": "BTCUSDT", "exchange": "METAMASK", "qty": 1.0,
             "cost": 1.0, "status": dm.ACTIVE_STATUS},
            {"id": 2, "coin": "ETHUSDT", "exchange": "METAMASK", "qty": 1.0,
             "cost": 1.0, "status": dm.ACTIVE_STATUS},
        ], [{"asset": "BTC", "qty": 1.0},          # eşleşiyor, $100.000
            {"asset": "ETH", "qty": 1.02}])        # fark var, yalnızca $40
        satirlar = {r["asset"]: r["status"] for r in rapor["rows"]}
        assert satirlar["BTC"] == "match" and satirlar["ETH"] == "mismatch"
        assert [r["asset"] for r in rapor["rows"]] == ["ETH", "BTC"]
