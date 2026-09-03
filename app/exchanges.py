"""
CoinTakip — Borsa API Bağlantıları (FAZ F6b)
============================================

NE YAPAR
--------
Borsadaki bakiyeyi doğrudan borsanın API'sinden okur. Amaç, her ay tekrarlanan
el emeğini kaldırmaktır: tarayıcıda dışa aktarım isteyip dosyayı indirmek,
bulmak, uygulamaya vermek. `connections.py` bunu zincir tarafında kaldırdı; bu
modül borsa tarafında kaldırıyor.

**Okuma salt okunurdur.** Bu modül yalnızca GET isteği yapar; emir verme, para
çekme veya herhangi bir yazma çağrısı YOKTUR ve eklenmemelidir.

NEDEN "İMZALAMA AİLESİ", NEDEN BORSA BAŞINA ADAPTÖR DEĞİL
----------------------------------------------------------
Cüzdanlarda tek bir genel adres yeter ve adaptör zincir başına yazılır. Borsalar
öyle değil: her biri isteği farklı imzalar (Binance sorgu dizisi üzerinden
HMAC-SHA256, Gate.io gövde özetiyle HMAC-SHA512, OKX ailesi base64, Bybit ayrı)
ve bakiye JSON'unun şekli de farklıdır. Kullanıcı bir kutuya URL yapıştırarak
borsa ekleyemez.

Çözüm: adaptörü **borsaya değil imzalama ailesine** yaz, borsayı `settings.json`
içinde bir **profil** olarak tanımla (taban adres, uç noktalar, aile, alan
eşlemesi). O zaman yeni bir borsa eklemek kod değil form doldurmak olur.

Şu an gönderilen aile bir tane: `binance`. MEXC'in v3 API'si Binance'in
klonudur ve aynı imzalamayı kullanır — yani ilk aile iki borsayı birden
kapsıyor. Diğer aileler (OKX, Gate.io, Bybit) bu mekanizmanın üstüne profil ve
küçük birer imzalama işleviyle eklenir.

**Dürüstlük notu:** "her borsa çalışır" demiyoruz. Egzotik imzalama şeması olan
bir borsa yine kod ister. Kullanıcıya söylenen şey bu.

ANAHTAR GERÇEK BİR SIRDIR
-------------------------
Cüzdan adresi herkese açıktır; borsa API anahtarı değildir. Salt okunur bile
olsa tüm işlem geçmişinizi açar. Bu yüzden:

* Anahtar ve gizli anahtar **yalnızca şifreli kasada** durur (`keyvault`),
  `settings.json` içinde asla düz metin bulunmaz.
* Anahtar **saklanmadan önce izinleri denetlenir**. Para çekme veya emir verme
  yetkisi olan bir anahtar kabul EDİLMEZ.
* İzinler doğrulanamıyorsa bu **gizlenmez**: kullanıcıya doğrulayamadığımız
  söylenir ve açık onayı istenir. Veremediğimiz bir güvenceyi vermeyiz.
"""

import concurrent.futures
import hashlib
import hmac
import json
import re
import time
from datetime import datetime
import urllib.error
import urllib.parse
import urllib.request

from log_config import get_logger

logger = get_logger("exchanges")

HTTP_TIMEOUT = 15
DUST_EPSILON = 1e-12
PARALEL_ISCI = 4

# Not seviyeleri `connections` ile aynı sözlüğü kullanır; arayüz tek bir
# gösterim mantığıyla ikisini de çizebilsin diye.
NOTE_ERROR = "error"
NOTE_WARN = "warn"
NOTE_INFO = "info"


def _not(seviye, mesaj):
    return {"level": seviye, "message": str(mesaj)}


def is_incomplete(notlar) -> bool:
    return any(n.get("level") in (NOTE_ERROR, NOTE_WARN) for n in (notlar or []))


class ExchangeError(Exception):
    """Borsa isteği başarısız. Mesaj kullanıcıya gösterilecek kadar açıktır."""


class WriteCapableKey(ExchangeError):
    """Anahtar yazma yetkisi taşıyor. Saklanmadan önce reddedilir."""


# =====================================================================
# İzin durumu
# =====================================================================
# Üç ayrı durum var ve üçünü aynı kefeye koymak ya kullanıcıyı boşuna
# engellerdi ya da veremeyeceğimiz bir güvence vermiş olurduk:
#
#   verified_readonly — borsa, ANAHTARIN yetkilerini bize söyledi ve anahtar
#                       yalnızca okuma yapabiliyor. Güvenli.
#   write_capable     — borsa söyledi ve anahtar emir verebiliyor veya para
#                       çekebiliyor. REDDEDİLİR, saklanmaz.
#   unverifiable      — borsanın anahtar yetkilerini bildiren bir ucu yok
#                       (MEXC böyle). Hesap düzeyindeki `canTrade` alanı
#                       ANAHTARIN değil HESABIN yetkisidir; onu anahtar yetkisi
#                       sanmak yanlış bir güvence olurdu.
#
# Son durumda kullanıcıdan açık onay isteniyor. Bilmediğimizi bilmek, yanlış
# bilmekten iyidir — projenin `None` != `0.0` ayrımıyla aynı çizgi.
PERM_READONLY = "verified_readonly"
PERM_WRITE = "write_capable"
PERM_UNKNOWN = "unverifiable"


# =====================================================================
# İmzalama aileleri
# =====================================================================
def _imzala_binance(secret: str, sorgu: str) -> str:
    """Sorgu dizisinin HMAC-SHA256 özeti, onaltılık. Binance ve MEXC v3."""
    return hmac.new(secret.encode("utf-8"), sorgu.encode("utf-8"),
                    hashlib.sha256).hexdigest()


SIGNING_FAMILIES = {
    "binance": {
        "name": "Binance tipi (HMAC-SHA256, sorgu dizisi)",
        "sign": _imzala_binance,
        # Ailenin VARSAYILANI, kuralı değil. Başlık adı imzalama şemasının
        # değil BORSANIN özelliğidir — bkz. `key_header()`.
        "key_header": "X-MBX-APIKEY",
        # İmza sorgu dizisinin SONUNA eklenir; sırayı değiştirmek imzayı bozar.
        "signature_param": "signature",
        "exchanges": "Binance, MEXC ve v3 API'sini birebir klonlayan borsalar",
    },
}


# =====================================================================
# Hazır profiller
# =====================================================================
# Bunlar kod değil VERİ: kullanıcı bir borsa eklediğinde profil
# `settings.json`'a kopyalanır ve oradan düzenlenebilir. Buradaki liste
# yalnızca "elle doldurmak zorunda kalma" kolaylığıdır.
#
# `restrictions_path` — ANAHTARIN yetkilerini söyleyen uç. Varsa izin denetimi
# kesindir. Yoksa (MEXC) denetim yapılamaz ve bu kullanıcıya söylenir.
BUILTIN_PROFILES = {
    "BINANCE": {
        "location": "BINANCE",
        "name": "Binance",
        "family": "binance",
        "base_url": "https://api.binance.com",
        "account_path": "/api/v3/account",
        "time_path": "/api/v3/time",
        "restrictions_path": "/sapi/v1/account/apiRestrictions",
        "key_header": "X-MBX-APIKEY",
        "balances_field": "balances",
        "asset_field": "asset",
        "free_field": "free",
        "locked_field": "locked",
    },
    "MEXC": {
        "location": "MEXC",
        "name": "MEXC",
        "family": "binance",
        "base_url": "https://api.mexc.com",
        "account_path": "/api/v3/account",
        "time_path": "/api/v3/time",
        # MEXC'te anahtar yetkilerini bildiren belgelenmiş bir uç yok.
        "restrictions_path": "",
        # MEXC imzalamayı Binance'ten birebir klonlar AMA anahtarı kendi
        # başlığında bekler. `X-MBX-APIKEY` gönderilirse başlık okunmaz ve
        # borsa, hiç başlık yollanmamış gibi `400 api key required` döner.
        # Canlı olarak doğrulandı (3 Eylül 2026, sahte anahtarla):
        #   X-MBX-APIKEY  → {"code":400,"msg":"api key required"}   (= başlıksuz)
        #   X-MEXC-APIKEY → {"code":10072,"msg":"Api key info invalid"}
        # İkincisi başlığın OKUNDUĞUNU, anahtarın sahte olduğu için
        # reddedildiğini gösterir.
        "key_header": "X-MEXC-APIKEY",
        "balances_field": "balances",
        "asset_field": "asset",
        "free_field": "free",
        "locked_field": "locked",
    },
}

REQUIRED_FIELDS = ("location", "family", "base_url", "account_path")


def key_header(profil: dict) -> str:
    """
    Anahtarın hangi HTTP başlığıyla gönderileceği.

    Bu, imzalama ailesinin değil **borsanın** özelliğidir. MEXC, Binance'in
    imzalama şemasını birebir klonlar ama başlığı `X-MEXC-APIKEY` bekler;
    başlık adı aileye bağlanırsa MEXC hiçbir zaman kimlik doğrulayamaz.

    Sıra: profilin kendi değeri → o konumun hazır profili → ailenin
    varsayılanı. Ortadaki adım, bu düzeltmeden ÖNCE kaydedilmiş (ve bu yüzden
    `key_header` alanı taşımayan) bir profilin çalışmaya devam etmesi içindir.
    """
    kendi = str((profil or {}).get("key_header") or "").strip()
    if kendi:
        return kendi

    konum = str((profil or {}).get("location") or "").upper().strip()
    hazir = str(BUILTIN_PROFILES.get(konum, {}).get("key_header") or "").strip()
    if hazir:
        return hazir

    aile = SIGNING_FAMILIES.get((profil or {}).get("family")) or {}
    return aile.get("key_header") or "X-MBX-APIKEY"


def builtin_profiles() -> list:
    """Arayüzün "hazır borsa" listesi."""
    return [dict(p) for p in BUILTIN_PROFILES.values()]


def signing_families() -> list:
    return [{"id": k, "name": v["name"], "exchanges": v["exchanges"]}
            for k, v in SIGNING_FAMILIES.items()]


# =====================================================================
# Kasa anahtarları
# =====================================================================
def key_name(location: str) -> str:
    return f"exchange:{str(location or '').upper().strip()}:key"


def secret_name(location: str) -> str:
    return f"exchange:{str(location or '').upper().strip()}:secret"


def _kasadan(location):
    """(api_key, api_secret). Kasa kilitliyse (None, None)."""
    import keyvault
    if not keyvault.is_unlocked():
        return None, None
    return keyvault.get(key_name(location)), keyvault.get(secret_name(location))


def credentials_stored(location) -> bool:
    """Kasa KİLİTLİYKEN de çalışır: "anahtar yok" ile "kasa kilitli" ayrıdır."""
    import keyvault
    return keyvault.has(key_name(location)) and keyvault.has(secret_name(location))


# =====================================================================
# Profil kayıt defteri
# =====================================================================
def list_profiles() -> dict:
    from data_manager import load_settings
    ham = load_settings().get("exchange_profiles") or {}
    cikti = {}
    for anahtar, spec in ham.items():
        if isinstance(spec, dict):
            spec = dict(spec)
            spec.setdefault("location", str(anahtar).upper())
            cikti[str(anahtar).upper()] = spec
    return cikti


def _kaydet(profiller):
    from data_manager import load_settings, save_settings
    settings = load_settings()
    settings["exchange_profiles"] = profiller
    save_settings(settings)


def validate_profile(spec: dict) -> tuple:
    """(temiz_profil, hata). Hata varsa profil None."""
    if not isinstance(spec, dict):
        return None, "Profil bilgisi okunamadı."
    temiz = {}
    for alan in ("location", "name", "family", "base_url", "account_path",
                 "time_path", "restrictions_path", "balances_field",
                 "asset_field", "free_field", "locked_field", "label",
                 "key_header", "key_expires_at"):
        deger = spec.get(alan)
        temiz[alan] = str(deger).strip() if deger is not None else ""

    temiz["location"] = temiz["location"].upper()
    for alan in REQUIRED_FIELDS:
        if not temiz.get(alan):
            return None, f"Zorunlu alan eksik: {alan}"

    if temiz["family"] not in SIGNING_FAMILIES:
        aileler = ", ".join(sorted(SIGNING_FAMILIES))
        return None, (f"Bilinmeyen imzalama ailesi: {temiz['family']}. "
                      f"Tanımlı aileler: {aileler}.")

    # Anahtar ağ üzerinden gidiyor; düz HTTP'de araya giren okur.
    if not temiz["base_url"].lower().startswith("https://"):
        return None, ("Taban adres https:// ile başlamalı. API anahtarınız bu "
                      "bağlantı üzerinden gidiyor; şifresiz HTTP'de araya giren "
                      "biri onu okuyabilir.")
    temiz["base_url"] = temiz["base_url"].rstrip("/")

    for alan in ("account_path", "time_path", "restrictions_path"):
        if temiz[alan] and not temiz[alan].startswith("/"):
            temiz[alan] = "/" + temiz[alan]

    # Başlık adı isteğe bağlıdır (boşsa `key_header()` hazır profile veya
    # aile varsayılanına düşer) ama yazıldıysa geçerli bir HTTP başlık adı
    # olmalıdır. Serbest metin bırakmak satır sonu karakteriyle isteğe
    # başka başlık enjekte etmeye açık kapı bırakırdı.
    if temiz["key_header"] and not re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}",
                                                temiz["key_header"]):
        return None, ("Anahtar başlığı geçerli bir HTTP başlık adı değil "
                      "(örn. X-MBX-APIKEY). Boşluk veya satır sonu içeremez.")

    # Anahtarın bitiş tarihi isteğe bağlıdır ama yazıldıysa gerçek bir tarih
    # olmalı. Bozuk bir tarihi sessizce kabul edip "süresi dolmuş" ya da
    # "sonsuz geçerli" diye yorumlamak, uyarının kendisini güvenilmez yapardı.
    if temiz["key_expires_at"]:
        try:
            datetime.strptime(temiz["key_expires_at"], "%Y-%m-%d")
        except ValueError:
            return None, "Anahtar bitiş tarihi YYYY-AA-GG biçiminde olmalı."

    temiz["name"] = temiz["name"] or temiz["location"].title()
    temiz["balances_field"] = temiz["balances_field"] or "balances"
    temiz["asset_field"] = temiz["asset_field"] or "asset"
    temiz["free_field"] = temiz["free_field"] or "free"
    temiz["locked_field"] = temiz["locked_field"] or "locked"
    temiz["enabled"] = bool(spec.get("enabled", True))

    # Son izin denetiminin sonucu profille birlikte taşınır ki arayüz
    # "izin doğrulanamadı" rozetini gösterebilsin. Beyaz liste dışındaki bir
    # değer sessizce kabul edilmez; uydurma bir durum rozeti yanlış güven verir.
    durum = str(spec.get("permission_status") or "").strip()
    if durum in (PERM_READONLY, PERM_WRITE, PERM_UNKNOWN):
        temiz["permission_status"] = durum
    return temiz, None


def save_profile(spec: dict) -> dict:
    temiz, hata = validate_profile(spec)
    if hata:
        raise ValueError(hata)
    profiller = list_profiles()
    profiller[temiz["location"]] = temiz
    _kaydet(profiller)
    logger.info("Borsa profili kaydedildi: %s (%s)",
                temiz["location"], temiz["family"])
    return temiz


# Anahtar yeniden girilmeden değiştirilebilecek alanlar.
#
# Sınır güvenlik sınırıdır, kolaylık sınırı değil: `base_url`, `account_path`,
# `key_header`, `family` ve `restrictions_path` anahtarın NEREYE ve NASIL
# gönderileceğini belirler. Bunlardan biri anahtar yeniden denetlenmeden
# değiştirilebilseydi, kasadaki anahtar bir sonraki okumada başka bir sunucuya
# gönderilebilirdi. Bu alanları değiştirmek anahtarı yeniden girmeyi ve izin
# denetiminden geçmeyi gerektirir.
SAFE_PROFILE_FIELDS = ("name", "label", "key_expires_at", "enabled")


def update_profile_fields(location: str, alanlar: dict) -> dict:
    """
    Var olan bir profilin **anahtara dokunmayan** alanlarını günceller.

    Buna neden ihtiyaç var: anahtarın bitiş tarihi profilde duruyor ama gizli
    anahtar (secret) borsada yalnızca oluşturulurken bir kez gösterilir.
    Sadece tarih girmek için anahtarın tamamını yeniden istemek, elinde secret
    olmayan kullanıcıyı yepyeni bir API anahtarı almaya zorlardı.

    Kasa gerekmez: burada hiçbir sır okunmaz veya yazılmaz.
    """
    konum = str(location or "").upper().strip()
    profiller = list_profiles()
    mevcut = profiller.get(konum)
    if not mevcut:
        raise ValueError(f"{konum} için tanımlı bir borsa profili yok.")

    istek = dict(alanlar or {})
    # Korumalı bir alan FARKLI bir değerle gelirse sessizce yok sayılmaz.
    # Yok saymak, kullanıcının kaydettiğini sandığı bir değişikliğin hiç
    # olmaması demekti; bunu söylemek zorundayız.
    for alan in ("location", "family", "base_url", "account_path",
                 "time_path", "restrictions_path", "key_header"):
        if alan not in istek:
            continue
        yeni = str(istek[alan] or "").strip()
        eski = str(mevcut.get(alan) or "").strip()
        if alan == "location":
            yeni = yeni.upper()
        if yeni and yeni != eski:
            raise ValueError(
                f"'{alan}' alanı anahtar yeniden girilmeden değiştirilemez. "
                "Bu alanlar anahtarınızın nereye gönderileceğini belirler; "
                "değiştirmek için API anahtarını ve gizli anahtarı yeniden "
                "girip Kaydet'e basın.")

    guncel = dict(mevcut)
    for alan in SAFE_PROFILE_FIELDS:
        if alan in istek:
            guncel[alan] = istek[alan]

    temiz, hata = validate_profile(guncel)
    if hata:
        raise ValueError(hata)
    # Son izin denetiminin sonucu korunur; bu güncelleme onu doğrulamadı.
    if mevcut.get("permission_status"):
        temiz["permission_status"] = mevcut["permission_status"]

    profiller[konum] = temiz
    _kaydet(profiller)
    logger.info("Borsa profili guncellendi (anahtara dokunulmadi): %s", konum)
    return temiz


def delete_profile(location: str, forget_keys: bool = True) -> bool:
    """
    Profili siler. Varsayılan olarak kasadaki anahtarları da unutur.

    Anahtarı geride bırakmak, kullanıcının "sildim" sandığı bir sırrın diskte
    şifreli olarak durmaya devam etmesi demek olurdu.
    """
    konum = str(location or "").upper().strip()
    profiller = list_profiles()
    if konum not in profiller:
        return False
    profiller.pop(konum)
    _kaydet(profiller)
    if forget_keys:
        try:
            import keyvault
            if keyvault.is_unlocked():
                keyvault.forget(key_name(konum))
                keyvault.forget(secret_name(konum))
        except Exception as e:
            logger.warning("Borsa anahtarları unutulamadı (%s): %s", konum, e)
    logger.info("Borsa profili silindi: %s", konum)
    return True


# =====================================================================
# İmzalı istek — YALNIZCA GET
# =====================================================================
_ZAMAN_FARKI = {}          # konum → sunucu saati farkı (ms)


def _http_get(url, headers=None):
    istek = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(istek, timeout=HTTP_TIMEOUT) as cevap:
            return json.loads(cevap.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Borsanın kendi hata mesajı, genel bir "500" cümlesinden çok daha
        # yararlı: yanlış anahtar, IP kısıtı ve saat kayması ayrı ayrı anlaşılır.
        govde = ""
        try:
            govde = e.read().decode("utf-8")[:400]
        except Exception:
            pass
        raise ExchangeError(f"HTTP {e.code}: {govde or e.reason}") from e
    except Exception as e:
        raise ExchangeError(str(e)) from e


def server_time_offset(profil, yenile=False) -> int:
    """
    Borsa saati ile yerel saat arasındaki fark (ms).

    Binance ailesi her imzalı isteğe `timestamp` ister ve kendi saatinden çok
    sapan isteği reddeder. Kullanıcının makinesindeki birkaç saniyelik kayma
    tüm okumaları düşürürdü; bu yüzden fark bir kez ölçülüp uygulanıyor.
    """
    konum = profil.get("location", "")
    if not yenile and konum in _ZAMAN_FARKI:
        return _ZAMAN_FARKI[konum]
    fark = 0
    yol = profil.get("time_path")
    if yol:
        try:
            cevap = _http_get(profil["base_url"] + yol)
            sunucu = int(cevap.get("serverTime") or 0)
            if sunucu:
                fark = sunucu - int(time.time() * 1000)
        except Exception as e:
            logger.debug("Sunucu saati alınamadı (%s): %s", konum, e)
    _ZAMAN_FARKI[konum] = fark
    return fark


def signed_get(profil, path, api_key, api_secret, params=None):
    """
    İmzalı GET. Bu modülün ağa çıkan TEK yolu ve yalnızca GET yapar.

    Yazma çağrısı eklenmemelidir: kullanıcıya verilen söz, bağlantının hiçbir
    koşulda emir veremeyeceği veya para çekemeyeceğidir.
    """
    aile = SIGNING_FAMILIES.get(profil.get("family"))
    if not aile:
        raise ExchangeError(f"Bilinmeyen imzalama ailesi: {profil.get('family')}")
    if not api_key or not api_secret:
        raise ExchangeError("API anahtarı veya gizli anahtar yok.")

    p = dict(params or {})
    p["timestamp"] = int(time.time() * 1000) + server_time_offset(profil)
    p.setdefault("recvWindow", 10000)
    sorgu = urllib.parse.urlencode(p)
    imza = aile["sign"](api_secret, sorgu)
    url = f"{profil['base_url']}{path}?{sorgu}&{aile['signature_param']}={imza}"
    return _http_get(url, {key_header(profil): api_key})


# =====================================================================
# İzin denetimi
# =====================================================================
def check_permissions(profil, api_key, api_secret) -> dict:
    """
    Anahtarın yetkilerini sorar. **Hiçbir şey saklamaz.**

    Dönen `status` üç değerden biridir: `verified_readonly`, `write_capable`,
    `unverifiable`. Son durumda hesap düzeyindeki alanlara BAKILMAZ — onlar
    anahtarın değil hesabın yetkisidir ve onları anahtar yetkisi saymak
    kullanıcıya veremeyeceğimiz bir güvence vermek olurdu.
    """
    yol = profil.get("restrictions_path")
    if not yol:
        return {
            "status": PERM_UNKNOWN,
            "can_trade": None, "can_withdraw": None, "ip_restricted": None,
            "detail": (
                f"{profil.get('name') or profil.get('location')} API'si bir "
                "anahtarın yetkilerini bildiren uç sunmuyor, bu yüzden "
                "anahtarınızın gerçekten salt okunur olduğunu DOĞRULAYAMIYORUZ. "
                "Anahtarı borsada oluştururken yalnızca okuma iznini açtığınızdan "
                "ve para çekme iznini kapalı bıraktığınızdan siz emin olmalısınız."),
        }

    ham = signed_get(profil, yol, api_key, api_secret)
    # Binance cevabı bazı sürümlerde `data` içine sarılı geliyor.
    veri = ham.get("data") if isinstance(ham.get("data"), dict) else ham

    cekebilir = bool(veri.get("enableWithdrawals"))
    islem = bool(veri.get("enableSpotAndMarginTrading")
                 or veri.get("enableFutures")
                 or veri.get("enableMargin"))
    ip_kisitli = veri.get("ipRestrict")

    if cekebilir or islem:
        durum = PERM_WRITE
        yetkiler = []
        if cekebilir:
            yetkiler.append("para çekme")
        if islem:
            yetkiler.append("emir verme")
        aciklama = ("Bu anahtar " + " ve ".join(yetkiler) + " yetkisi taşıyor.")
    else:
        durum = PERM_READONLY
        aciklama = "Anahtar yalnızca okuma yapabiliyor."

    return {"status": durum, "can_trade": islem, "can_withdraw": cekebilir,
            "ip_restricted": None if ip_kisitli is None else bool(ip_kisitli),
            "detail": aciklama}


def _yazma_yetkisi_reddi(izin, profil):
    return WriteCapableKey(
        izin.get("detail", "Bu anahtar yazma yetkisi taşıyor.") +
        " CoinTakip bu anahtarı SAKLAMAZ: portföy takibi için okuma yetkisi "
        "yeterlidir ve yazma yetkili bir anahtarın burada durması gereksiz bir "
        "risktir. " + str(profil.get("name") or profil.get("location")) +
        " hesabınızda yeni bir API anahtarı oluşturup yalnızca okuma iznini "
        "açın, para çekme ve emir verme izinlerini kapalı bırakın.")


# =====================================================================
# Bakiye okuma
# =====================================================================
def _bakiyeleri_ayikla(profil, ham):
    alan = profil.get("balances_field") or "balances"
    liste = ham.get(alan)
    if liste is None and isinstance(ham.get("data"), dict):
        liste = ham["data"].get(alan)
    if not isinstance(liste, list):
        raise ExchangeError(
            f"Bakiye listesi bulunamadı (beklenen alan: '{alan}'). "
            "Profildeki alan eşlemesi bu borsayla uyuşmuyor olabilir.")

    varlik_a = profil.get("asset_field") or "asset"
    serbest_a = profil.get("free_field") or "free"
    kilitli_a = profil.get("locked_field") or "locked"

    bakiyeler = []
    for b in liste:
        if not isinstance(b, dict):
            continue
        sembol = str(b.get(varlik_a) or "").upper().strip()
        if not sembol:
            continue
        try:
            serbest = float(b.get(serbest_a) or 0.0)
            kilitli = float(b.get(kilitli_a) or 0.0)
        except (TypeError, ValueError):
            continue
        toplam = serbest + kilitli
        if toplam <= DUST_EPSILON:
            continue
        bakiyeler.append({
            "asset": sembol, "qty": toplam,
            "free": serbest, "locked": kilitli,
            "contract": None,
            # Borsa "bu senin bakiyende" diyorsa dayanak budur; zincirdeki
            # doğrulanmamış token sorunu burada yok.
            "trust": "verified", "verified": True,
        })
    return bakiyeler


def read_exchange(location, profil=None):
    """
    Bir borsanın canlı bakiyesi. **Hiçbir şey yazmaz.**

    Dönen sözlük `connections.read_connection` ile AYNI şekildedir; böylece
    karşılaştırma tablosu ve arayüz ikisini ayırt etmek zorunda kalmaz.
    """
    from data_manager import normalize_location
    konum = normalize_location(str(location or ""))
    if profil is None:
        profil = list_profiles().get(konum)

    temel = {"id": konum, "location": konum, "source": "exchange",
             "chain": None, "address": None,
             "label": (profil or {}).get("label", ""),
             "name": (profil or {}).get("name", konum)}

    if not profil:
        return {**temel, "ok": False, "balances": [], "incomplete": True,
                "notes": [_not(NOTE_ERROR, "Tanımlı borsa profili bulunamadı.")]}

    import keyvault
    if not credentials_stored(konum):
        return {**temel, "ok": False, "balances": [], "incomplete": True,
                "notes": [_not(NOTE_ERROR,
                    f"{profil.get('name', konum)} için API anahtarı tanımlı "
                    "değil. Borsa bağlantıları bölümünden ekleyebilirsiniz.")]}
    if not keyvault.is_unlocked():
        # Anahtar VAR ama kasa kilitli. Bu ikisini aynı cümleyle anlatmak,
        # kullanıcıyı zaten yaptığı bir işi tekrar yapmaya gönderirdi.
        return {**temel, "ok": False, "balances": [], "incomplete": True,
                "notes": [_not(NOTE_ERROR,
                    f"{profil.get('name', konum)} anahtarınız kasada duruyor ama "
                    "**kasa kilitli**. Çözme anahtarı diskte durmadığı için "
                    "uygulama her açıldığında kasayı açmanız gerekir: "
                    "Anahtar Kasası → PIN → Kasayı Aç.")]}

    api_key, api_secret = _kasadan(konum)
    baslangic = time.time()
    try:
        ham = signed_get(profil, profil["account_path"], api_key, api_secret)
        bakiyeler = _bakiyeleri_ayikla(profil, ham)
        notlar = []
        if not bakiyeler:
            # Boş bakiye "okunamadı" değildir; borsa cevap verdi ve orada bir
            # şey yok dedi. Bunu hata gibi göstermek yanlış alarm olurdu.
            notlar.append(_not(NOTE_INFO,
                "Borsa cevap verdi ama spot bakiyeniz boş görünüyor. "
                "Varlıklarınız vadeli, kaldıraçlı veya Earn hesabında olabilir; "
                "bu okuma yalnızca spot cüzdanı kapsıyor."))
        # Okuma başarılı olsa bile süresi yaklaşan anahtar söylenir: uyarının
        # değeri, anahtar HÂLÂ çalışırken görülmesindedir.
        sure = key_expiry_state(profil)
        if sure["state"] == "expiring":
            notlar.append(_not(NOTE_INFO,
                f"{profil.get('name', konum)} API anahtarınızın süresi "
                f"{sure['days_left']} gün sonra doluyor ({sure['expires_at']}). "
                "Dolduğunda bu okuma sessizce başarısız olmaya başlar; "
                "borsadan yeni bir salt-okunur anahtar alıp buradan "
                "güncelleyin."))
        return {**temel, "ok": True, "balances": bakiyeler, "notes": notlar,
                "incomplete": is_incomplete(notlar),
                "elapsed_ms": int((time.time() - baslangic) * 1000),
                "read_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    except Exception as e:
        logger.warning("Borsa okunamadı (%s): %s", konum, e)
        # Süresi dolmuş bir anahtarın hatası genellikle anlamsız görünür
        # ("Api key info invalid"). Sebebi biliyorsak söyleriz; kullanıcı
        # sebebi ağda, bağlantıda veya kodda aramasın.
        sure = key_expiry_state(profil)
        if sure["state"] == "expired":
            aciklama = (
                f"{profil.get('name', konum)} okunamadı ve muhtemel sebep belli: "
                f"API anahtarınızın süresi {sure['expires_at']} tarihinde doldu "
                f"({abs(sure['days_left'])} gün önce). Borsadan yeni bir "
                f"salt-okunur anahtar alıp buradan güncelleyin. "
                f"Borsanın verdiği hata: {e}")
        else:
            aciklama = f"{profil.get('name', konum)} okunamadı: {e}"
        return {**temel, "ok": False, "balances": [], "incomplete": True,
                "notes": [_not(NOTE_ERROR, aciklama)]}


def test_profile(profil, api_key, api_secret) -> dict:
    """
    Profili ve anahtarı dener. **Hiçbir şey saklamaz.**

    Önce izinlere bakar: yazma yetkili bir anahtarla bakiye okumaya bile
    girişmeyiz, çünkü o anahtarın burada işi yoktur.
    """
    temiz, hata = validate_profile(profil)
    if hata:
        raise ValueError(hata)

    # Deneme hataları LOGLANIR. Önceki sürümde yalnızca ekrana yazılıyordu;
    # kullanıcı sayfayı kapattığı an hata kayboluyor ve sonradan teşhis
    # edilemiyordu. Gerçek bir kullanımda tam olarak bu yaşandı: ilk deneme
    # hata verdi, ikincisi çalıştı ve hatanın ne olduğu bir daha bilinemedi.
    try:
        izin = check_permissions(temiz, api_key, api_secret)
    except Exception as e:
        logger.warning("Borsa denemesi başarısız (%s, izin denetimi): %s",
                       temiz["location"], e)
        raise
    if izin["status"] == PERM_WRITE:
        logger.warning("Borsa denemesi reddedildi (%s): yazma yetkili anahtar.",
                       temiz["location"])
        raise _yazma_yetkisi_reddi(izin, temiz)

    try:
        ham = signed_get(temiz, temiz["account_path"], api_key, api_secret)
        bakiyeler = _bakiyeleri_ayikla(temiz, ham)
    except Exception as e:
        logger.warning("Borsa denemesi başarısız (%s, bakiye okuma): %s",
                       temiz["location"], e)
        raise
    logger.info("Borsa denemesi başarılı: %s (%d varlık, izin: %s)",
                temiz["location"], len(bakiyeler), izin["status"])
    return {"ok": True, "location": temiz["location"],
            "name": temiz["name"], "permission": izin,
            "asset_count": len(bakiyeler),
            "assets": sorted(b["asset"] for b in bakiyeler)[:20]}


def save_credentials(profil, api_key, api_secret, acknowledge_unverified=False):
    """
    Anahtarı denetler ve **ancak geçerse** kasaya yazar.

    Sıra bilinçli: önce denetle, sonra sakla. Tersi olsaydı reddedilen bir
    anahtar bir süre diskte durmuş olurdu.
    """
    temiz, hata = validate_profile(profil)
    if hata:
        raise ValueError(hata)
    api_key = str(api_key or "").strip()
    api_secret = str(api_secret or "").strip()
    if not api_key or not api_secret:
        raise ValueError("API anahtarı ve gizli anahtar zorunludur.")

    try:
        izin = check_permissions(temiz, api_key, api_secret)
    except Exception as e:
        logger.warning("Borsa kaydı başarısız (%s, izin denetimi): %s",
                       temiz["location"], e)
        raise
    if izin["status"] == PERM_WRITE:
        logger.warning("Borsa kaydı reddedildi (%s): yazma yetkili anahtar.",
                       temiz["location"])
        raise _yazma_yetkisi_reddi(izin, temiz)
    if izin["status"] == PERM_UNKNOWN and not acknowledge_unverified:
        raise ExchangeError(izin["detail"] + " Devam etmek için bunu onaylamanız "
                            "gerekiyor.")

    import keyvault
    keyvault.put(key_name(temiz["location"]), api_key)
    keyvault.put(secret_name(temiz["location"]), api_secret)
    kayit = save_profile({**temiz, "permission_status": izin["status"]})
    logger.info("Borsa anahtarı kasaya yazıldı: %s (izin: %s)",
                temiz["location"], izin["status"])
    return {"profile": kayit, "permission": izin}


# =====================================================================
# Toplu okuma
# =====================================================================
def read_all(only_enabled=True) -> dict:
    """(konum → okuma). Bağlantılar paralel okunur; biri düşerse diğerleri kalır."""
    profiller = {k: v for k, v in list_profiles().items()
                 if (not only_enabled) or v.get("enabled", True)}
    if not profiller:
        return {}

    def oku(oge):
        konum, profil = oge
        try:
            return read_exchange(konum, profil)
        except Exception as e:                       # beklenmeyen hata
            logger.error("Borsa okuması beklenmedik şekilde düştü (%s): %s",
                         konum, e)
            return {"id": konum, "location": konum, "source": "exchange",
                    "ok": False, "balances": [], "incomplete": True,
                    "notes": [_not(NOTE_ERROR, f"Okuma düştü: {e}")]}

    ogeler = list(profiller.items())
    if len(ogeler) == 1:
        sonuc = [oku(ogeler[0])]
    else:
        n = min(PARALEL_ISCI, len(ogeler))
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as havuz:
            sonuc = list(havuz.map(oku, ogeler))
    return {o["location"]: o for o in sonuc}


# Kaç gün kala uyarılır. Bir anahtarı yenilemek borsada birkaç dakikalık iş
# ama fark edilmesi haftalar alabilir; iki hafta rahat bir pay.
KEY_EXPIRY_WARN_DAYS = 14


def key_expiry_state(profil) -> dict:
    """
    Anahtarın ne kadar ömrü kaldığı.

    Bunu API'den öğrenmenin yolu yok — hiçbir borsa anahtarın bitiş tarihini
    bildirmiyor — bu yüzden tarih kullanıcıdan gelir ve **isteğe bağlıdır**.
    Girilmediyse `unknown` döner; "sonsuz geçerli" DEĞİL. Bilmediğimiz şeyi
    bildiğimiz gibi göstermek, bu projede birkaç kez düzelttiğimiz hatanın
    aynısı olurdu.

    Neden gerekli: MEXC dinamik IP'de anahtara **90 gün** ömür veriyor.
    Süre dolduğunda anahtar sessizce ölür ve okuma "başarısız" görünür;
    kullanıcı sebebini bağlantıda, ağda veya kodda arar.
    """
    ham = str((profil or {}).get("key_expires_at") or "").strip()
    if not ham:
        return {"state": "unknown", "days_left": None, "expires_at": ""}
    try:
        biter = datetime.strptime(ham, "%Y-%m-%d").date()
    except ValueError:
        return {"state": "unknown", "days_left": None, "expires_at": ham}

    kalan = (biter - datetime.now().date()).days
    if kalan < 0:
        durum = "expired"
    elif kalan <= KEY_EXPIRY_WARN_DAYS:
        durum = "expiring"
    else:
        durum = "ok"
    return {"state": durum, "days_left": kalan, "expires_at": ham}


def status() -> dict:
    """Arayüzün özet ihtiyacı: hangi borsa tanımlı, anahtarı var mı."""
    profiller = list_profiles()
    return {
        "profiles": profiller,
        "families": signing_families(),
        "builtin": builtin_profiles(),
        "credentials": {k: credentials_stored(k) for k in profiller},
        # Süre bilgisi yalnızca anahtarı OLAN profiller için anlamlıdır;
        # anahtarsız bir profilde "süresi doldu" demek kafa karıştırırdı.
        "key_expiry": {k: key_expiry_state(p) for k, p in profiller.items()
                       if credentials_stored(k)},
        "expiry_warn_days": KEY_EXPIRY_WARN_DAYS,
    }
