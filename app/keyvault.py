"""
CoinTakip — Anahtar Kasası (FAZ F6)
=====================================================================

NE YAPAR
--------
Borsa API anahtarları ve sağlayıcı anahtarları gibi GERÇEKTEN gizli tutulması
gereken değerleri, kullanıcının PIN'inden türetilmiş bir anahtarla şifreleyip
`settings.json` içinde saklar. Şifre çözme anahtarı diskte HİÇBİR yerde
durmaz; yalnızca kullanıcı PIN'i girdiği oturum boyunca bellekte tutulur.

NEDEN BASE64 DEĞİL
------------------
Projede Gemini/Telegram anahtarları için kullanılan `_obfuscate_key` Base64
tabanlıdır ve **şifreleme değildir** — dosyayı okuyan herkes anahtarı geri
çevirebilir. Bu, kendi hesabınıza ait bir yapay zekâ anahtarı için kabul
edilebilir bir risktir; borsa anahtarı için değildir. Bu modül bilinçli olarak
ayrı tutuldu ve o mekanizmayı kullanmaz.

NEDEN PIN'DEN TÜRETİLİYOR
-------------------------
Gerilim şu: arka planda kullanıcı olmadan yoklama yapmak istiyorsanız, çözme
anahtarının da diskte olması gerekir — ki bu, makineye erişimi olan birine
karşı hiçbir koruma sağlamaz. Kullanıcının kararı bu yüzden "PIN ile açılan
kasa" oldu: uygulama, kullanıcı açmadan borsaya bağlanmaz. Bu bir kısıt değil,
bilinçli bir takas.

PIN DEĞİŞİRSE NE OLUR
---------------------
Kasa PIN'e bağlı olduğu için PIN değişince eski kayıtlar çözülemez hâle
gelirdi. `rewrap()` bunu engeller: PIN değiştirme akışı hem eski hem yeni PIN'i
bildiği an içerikler yeniden şifrelenir. Sessizce bozulan bir kasa, kilitli bir
kasadan daha kötüdür — kullanıcı anahtarını kaybettiğini fark etmez.
"""

import base64
import os
import secrets

from log_config import get_logger

logger = get_logger("keyvault")

# PBKDF2 tur sayısı. Yüksek tutuldu çünkü türetme yalnızca kilit açılışında
# bir kez yapılıyor; kullanıcı bir kereliğine ~0.3 sn bekler, saldırgan her
# denemesi için aynı bedeli öder.
PBKDF2_ITERATIONS = 600_000

# Kasanın doğru PIN'le açıldığını anlamak için şifrelenip saklanan sabit.
# Yanlış PIN'de çözme hata verir ve kullanıcıya "kasa bu PIN'e ait değil"
# denebilir — sessizce boş kasa göstermek yerine.
_VERIFIER_PLAINTEXT = "cointakip-vault-v1"

# Oturum anahtarı. Diske ASLA yazılmaz, sürecin ömrüyle sınırlıdır.
_session_key = None


class VaultLocked(Exception):
    """Kasa kilitli; önce PIN ile açılması gerekiyor."""


class VaultError(Exception):
    """Kasa açılamadı veya içerik çözülemedi."""


def _fernet_available():
    try:
        from cryptography.fernet import Fernet  # noqa: F401
        return True
    except ImportError:
        return False


def _derive_key(pin: str, salt_hex: str) -> bytes:
    """PIN + kuruluma özel tuzdan Fernet anahtarı türetir."""
    import hashlib
    ham = hashlib.pbkdf2_hmac(
        "sha256", str(pin).strip().encode("utf-8"),
        bytes.fromhex(salt_hex), PBKDF2_ITERATIONS, dklen=32)
    return base64.urlsafe_b64encode(ham)


def _vault_salt(settings) -> str:
    """Kasa tuzu. PIN tuzundan AYRI tutulur ki biri diğerini ele vermesin."""
    sec = settings.setdefault("security", {})
    if not sec.get("vault_salt"):
        sec["vault_salt"] = secrets.token_hex(16)
    return sec["vault_salt"]


def _encrypt_with(key: bytes, plaintext: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(key).encrypt(str(plaintext).encode("utf-8")).decode("ascii")


def _decrypt_with(key: bytes, token: str) -> str:
    from cryptography.fernet import Fernet
    from cryptography.fernet import InvalidToken
    try:
        return Fernet(key).decrypt(str(token).encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise VaultError("İçerik bu anahtarla çözülemedi.")


# ---------------------------------------------------------------------
# Kilit yönetimi
# ---------------------------------------------------------------------
def is_unlocked() -> bool:
    return _session_key is not None


def lock():
    """Oturum anahtarını bellekten düşürür."""
    global _session_key
    _session_key = None


def unlock(pin: str) -> dict:
    """
    Kasayı açar. PIN doğruysa oturum anahtarını bellekte tutar.

    İlk açılışta doğrulayıcı üretilir; sonraki açılışlarda doğrulayıcı
    çözülemezse PIN yanlıştır veya kasa başka bir PIN'le mühürlenmiştir.
    """
    global _session_key
    if not _fernet_available():
        raise VaultError(
            "Şifreleme kütüphanesi bulunamadı. Kurulum: "
            "python -m pip install -r requirements.txt")

    from data_manager import load_settings, save_settings, verify_pin

    settings = load_settings()
    sec = settings.get("security", {})
    if not sec.get("pin_enabled"):
        raise VaultError(
            "Kasa PIN korumasına dayanır. Önce Güvenlik ayarlarından bir PIN "
            "tanımlayın; anahtarlarınız o PIN'den türetilen bir anahtarla "
            "şifrelenecek.")
    if not verify_pin(pin):
        raise VaultError("Hatalı PIN.")

    tuz = _vault_salt(settings)
    key = _derive_key(pin, tuz)
    dogrulayici = sec.get("vault_verifier", "")

    if not dogrulayici:
        sec["vault_verifier"] = _encrypt_with(key, _VERIFIER_PLAINTEXT)
        settings["security"] = sec
        save_settings(settings)
        yeni = True
    else:
        try:
            if _decrypt_with(key, dogrulayici) != _VERIFIER_PLAINTEXT:
                raise VaultError("Kasa doğrulaması başarısız.")
        except VaultError:
            raise VaultError(
                "Kasa bu PIN'e ait değil. PIN'iniz kasanın dışından "
                "değiştirilmiş olabilir; kayıtlı anahtarları yeniden girmeniz "
                "gerekecek.")
        yeni = False

    _session_key = key
    logger.info("Anahtar kasası açıldı (yeni=%s).", yeni)
    return {"unlocked": True, "created": yeni}


# ---------------------------------------------------------------------
# İçerik
# ---------------------------------------------------------------------
def put(name: str, plaintext: str):
    """Kasaya bir sır yazar. Boş değer kaydı siler."""
    if _session_key is None:
        raise VaultLocked("Kasa kilitli.")
    from data_manager import load_settings, save_settings
    settings = load_settings()
    kasa = settings.setdefault("vault", {})
    ad = str(name or "").strip()
    if not ad:
        raise VaultError("Kasa kaydının adı boş olamaz.")
    if not str(plaintext or "").strip():
        kasa.pop(ad, None)
    else:
        kasa[ad] = _encrypt_with(_session_key, plaintext)
    settings["vault"] = kasa
    save_settings(settings)


def get(name: str, default=None):
    """Kasadan bir sır okur. Kilitliyse `VaultLocked` fırlatır."""
    if _session_key is None:
        raise VaultLocked("Kasa kilitli.")
    from data_manager import load_settings
    kasa = load_settings().get("vault", {}) or {}
    token = kasa.get(str(name or "").strip())
    if not token:
        return default
    return _decrypt_with(_session_key, token)


def has(name: str) -> bool:
    """
    Kayıt VAR MI? Kilitliyken de cevaplanabilir — içeriği değil varlığını
    söyler. Arayüz "anahtar tanımlı ama kasa kilitli" durumunu böyle gösterir.
    """
    from data_manager import load_settings
    kasa = load_settings().get("vault", {}) or {}
    return bool(kasa.get(str(name or "").strip()))


def names() -> list:
    from data_manager import load_settings
    return sorted((load_settings().get("vault", {}) or {}).keys())


def forget(name: str):
    """Kaydı siler. Kasanın kilitli olması gerekmez — silmek için çözmek gerekmez."""
    from data_manager import load_settings, save_settings
    settings = load_settings()
    kasa = settings.get("vault", {}) or {}
    if kasa.pop(str(name or "").strip(), None) is not None:
        settings["vault"] = kasa
        save_settings(settings)


def rewrap(old_pin: str, new_pin: str):
    """
    PIN değişince kasayı yeni PIN'e mühürler.

    Bu çağrılmazsa kullanıcı PIN'ini değiştirdiği anda bütün anahtarlarını
    sessizce kaybeder ve bunu ancak bir sonraki bağlantı denemesinde anlar.
    """
    from data_manager import load_settings, save_settings
    settings = load_settings()
    sec = settings.get("security", {})
    kasa = settings.get("vault", {}) or {}
    dogrulayici = sec.get("vault_verifier", "")
    if not dogrulayici and not kasa:
        return  # kasa hiç kullanılmamış

    tuz = _vault_salt(settings)
    eski = _derive_key(old_pin, tuz)
    try:
        if dogrulayici:
            _decrypt_with(eski, dogrulayici)
    except VaultError:
        # Eski PIN kasayı açmıyor: yeniden mühürleyemeyiz. Bozuk bir kasayı
        # taşımaktansa durumu açıkça bırakıyoruz; unlock() anlaşılır bir
        # mesaj verecek.
        logger.warning("Kasa eski PIN ile açılamadı; yeniden mühürleme atlandı.")
        return

    yeni = _derive_key(new_pin, tuz)
    sec["vault_verifier"] = _encrypt_with(yeni, _VERIFIER_PLAINTEXT)
    for ad, token in list(kasa.items()):
        try:
            kasa[ad] = _encrypt_with(yeni, _decrypt_with(eski, token))
        except VaultError:
            logger.warning("Kasa kaydı yeniden şifrelenemedi: %s", ad)
    settings["security"] = sec
    settings["vault"] = kasa
    save_settings(settings)

    global _session_key
    if _session_key is not None:
        _session_key = yeni
    logger.info("Anahtar kasası yeni PIN'e mühürlendi (%s kayıt).", len(kasa))


def status() -> dict:
    from data_manager import load_settings
    settings = load_settings()
    return {
        "available": _fernet_available(),
        "pin_enabled": bool(settings.get("security", {}).get("pin_enabled")),
        "sealed": bool(settings.get("security", {}).get("vault_verifier")),
        "unlocked": is_unlocked(),
        "entry_count": len(settings.get("vault", {}) or {}),
    }
