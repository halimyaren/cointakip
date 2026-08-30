"""
CoinTakip — Bağlantı Kayıt Defteri ve Zincir Üstü Okuyucular (FAZ F6)
=====================================================================

NE YAPAR
--------
Kullanıcının her konumunu (borsa hesabı, cüzdan) canlı bir veri kaynağına
bağlar ve "orada gerçekte ne var" sorusunu cevaplar. Bu faz zincir üstü
cüzdanları kapsıyor; borsa API'leri aynı kayıt defterine F6b'de eklenecek.

NEDEN KAYIT DEFTERİ, NEDEN KODA GÖMÜLÜ DEĞİL
---------------------------------------------
Kullanıcı şunu istedi: *"Sistemden beklediğim esneklik tüm bağlantılarımı bir
son kullanıcı kolaylığında yapabilmek."* Bu yüzden bağlantılar `settings.json`
içinde veri olarak durur ve arayüzden yönetilir; yeni bir cüzdan eklemek kod
değişikliği gerektirmez. Aynı kalıp projede `price_sources` ile zaten kurulmuş
durumda.

CÜZDAN DEĞİL ZİNCİR OKUNUR
--------------------------
MetaMask, Phantom, Ledger, Trust — hiçbirinin bağlanılacak bir API'si yoktur.
Bunlar anahtar tutan programlardır; varlık zincirde durur. Dolayısıyla adaptör
cüzdan başına değil **zincir başına** yazılır: tek bir EVM okuyucusu Ethereum,
BSC, Arbitrum, Polygon, Base ve Optimism'i kapsar.

Bunun güvenlik açısından güzel bir sonucu var: gereken tek şey **genel
adrestir**. Adres zaten herkese açıktır, korunacak bir sır yoktur ve okuma
yapı gereği salt okunurdur.

⚠️ Bu modül HİÇBİR KOŞULDA seed phrase veya özel anahtar istemez, kabul etmez
ve saklamaz. Arayüzde de bu açıkça yazar. Böyle bir şey isteyen her ekran
dolandırıcılıktır.
"""

import concurrent.futures
import json
import re
import time
import urllib.parse
import urllib.request

from log_config import get_logger

logger = get_logger("connections")

HTTP_TIMEOUT = 12

# ---------------------------------------------------------------------
# Desteklenen zincirler
# ---------------------------------------------------------------------
# Etherscan V2 tek anahtarla çok zincir destekliyor; `chainid` parametresi
# zinciri seçiyor. Yeni bir EVM zinciri eklemek buraya bir satır yazmaktır.
#
# `discovery` — OTOMATİK TOKEN KEŞFİ BU ZİNCİRDE MÜMKÜN MÜ
# --------------------------------------------------------
# "tek anahtar tüm zincirlerde çalışır" cümlesi yanlıştı ve kullanıcıyı boşuna
# uğraştırdı: Etherscan V2 anahtarı gerçekten çok zincirli, ama ÜCRETSİZ plan
# zincirlerin yalnızca bir kısmını kapsıyor. Kapsam dışı bir zincirde istek
# `Free API access is not supported for this chain` diye geri dönüyor.
#
#   "free" — ücretsiz anahtarla token keşfi çalışır
#   "paid" — keşif için ücretli Etherscan planı gerekir; ücretsiz anahtarla
#            yalnızca yerel coin okunur. Çözüm ödemek değil: kullanıcı takip
#            etmek istediği tokenı kontrat adresiyle elle tanımlar ve bakiye
#            doğrudan genel RPC'den okunur (anahtar gerekmez).
#
# Kaynak: docs.etherscan.io/supported-chains — plan kapsamı değişebilir, bu
# yüzden bilgi koda gömülü tek bir yerde durur.
EVM_CHAINS = {
    "ethereum": {"chain_id": 1, "name": "Ethereum", "native": "ETH",
                 "discovery": "free",
                 "rpc": "https://ethereum-rpc.publicnode.com"},
    "bsc": {"chain_id": 56, "name": "BNB Chain", "native": "BNB",
            "discovery": "paid",
            "rpc": "https://bsc-rpc.publicnode.com"},
    "polygon": {"chain_id": 137, "name": "Polygon", "native": "POL",
                "discovery": "free",
                "rpc": "https://polygon-bor-rpc.publicnode.com"},
    "arbitrum": {"chain_id": 42161, "name": "Arbitrum One", "native": "ETH",
                 "discovery": "free",
                 "rpc": "https://arbitrum-one-rpc.publicnode.com"},
    "optimism": {"chain_id": 10, "name": "Optimism", "native": "ETH",
                 "discovery": "paid",
                 "rpc": "https://optimism-rpc.publicnode.com"},
    "base": {"chain_id": 8453, "name": "Base", "native": "ETH",
             "discovery": "paid",
             "rpc": "https://base-rpc.publicnode.com"},
    "avalanche": {"chain_id": 43114, "name": "Avalanche C-Chain", "native": "AVAX",
                  "discovery": "paid",
                  "rpc": "https://avalanche-c-chain-rpc.publicnode.com"},
}

SOLANA_RPC = "https://api.mainnet-beta.solana.com"
SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"
ETHERSCAN_KEY_NAME = "etherscan_api_key"

# Toz bakiye eşiği: bunun altındaki miktarlar listeyi doldurmaktan başka bir
# işe yaramıyor. Sıfır değil, çünkü çok küçük ondalıklı tokenlar var.
DUST_EPSILON = 1e-12

CONNECTION_TYPES = ("onchain",)

# Elle tanımlanabilecek token sayısı. Her token okuma başına bir RPC çağrısıdır;
# sınırsız bırakmak tek bir bağlantıyı dakikalarca sürer hâle getirirdi.
MAX_MANUAL_TOKENS = 60

# Aynı anda kaç ağ isteği. Genel RPC uçları ücretsiz ve paylaşımlı; bu sayıyı
# büyütmek okumayı hızlandırmaz, istek reddi (rate limit) getirir.
PARALEL_ISCI = 8


# ---------------------------------------------------------------------
# Okuma notları ve seviyeleri
# ---------------------------------------------------------------------
# Her not aynı ağırlıkta değildi ama arayüz hepsini "eksik okundu" sayıyordu:
# Solana'nın spam token bilgilendirmesi de, BNB Chain'de token keşfinin hiç
# yapılamamış olması da aynı kırmızı bildirimi üretiyordu. Kullanıcı üç
# bağlantının eksik okunduğunu sandı; gerçekte eksik olan birdi. Alarmı
# şişirmek, gerçek sorunu gürültüde kaybettiriyor.
NOTE_ERROR = "error"   # okunamadı — elde veri yok
NOTE_WARN = "warn"     # okundu ama EKSİK okundu — bir kısım veri gelmedi
NOTE_INFO = "info"     # eksiksiz okundu; bilinmesinde yarar olan bir durum var


def _not(seviye, mesaj):
    return {"level": seviye, "message": str(mesaj)}


def is_incomplete(notlar) -> bool:
    """Bu okumada gerçekten eksik kalan veri var mı? Bilgi notları saymaz."""
    return any(n.get("level") in (NOTE_ERROR, NOTE_WARN) for n in (notlar or []))


# =====================================================================
# HTTP yardımcıları
# =====================================================================
def _http_json(url, payload=None, headers=None):
    baslik = {"User-Agent": "CoinTakip/1.0", "Accept": "application/json"}
    baslik.update(headers or {})
    veri = None
    if payload is not None:
        veri = json.dumps(payload).encode("utf-8")
        baslik["Content-Type"] = "application/json"
    istek = urllib.request.Request(url, data=veri, headers=baslik)
    with urllib.request.urlopen(istek, timeout=HTTP_TIMEOUT) as cevap:
        return json.loads(cevap.read().decode("utf-8"))


def _paralel(ogeler, is_fn, isci=None):
    """
    `is_fn`'i her öge için paralel çalıştırır; `(öge, sonuç, hata)` üçlüleri
    döndürür. Giriş sırası KORUNUR — rapor her çalıştırmada aynı sırayla
    çıksın diye.

    Bu işlerin tamamı ağ beklemesi olduğu için iş parçacığı doğru araç: GIL
    beklerken serbest bırakılıyor. İşçi sayısı bilerek düşük tutuldu; genel
    RPC uçları ücretsiz ve paylaşımlı, onları boğmak okumayı hızlandırmaz.
    """
    liste = list(ogeler)
    if not liste:
        return []
    if len(liste) == 1:
        try:
            return [(liste[0], is_fn(liste[0]), None)]
        except Exception as e:
            return [(liste[0], None, e)]

    def sarmala(oge):
        try:
            return (oge, is_fn(oge), None)
        except Exception as e:
            return (oge, None, e)

    n = min(isci or PARALEL_ISCI, len(liste))
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as havuz:
        return list(havuz.map(sarmala, liste))


def _rpc(url, method, params):
    cevap = _http_json(url, {"jsonrpc": "2.0", "id": 1,
                             "method": method, "params": params})
    if "error" in cevap:
        raise RuntimeError(str(cevap["error"].get("message", cevap["error"])))
    return cevap.get("result")


def _etherscan(chain_id, params, api_key):
    sorgu = dict(params)
    sorgu["chainid"] = chain_id
    sorgu["apikey"] = api_key
    cevap = _http_json(ETHERSCAN_V2 + "?" + urllib.parse.urlencode(sorgu))
    # Etherscan "0" durumunu hem gerçek hata hem "kayıt yok" için kullanıyor.
    if str(cevap.get("status")) != "1":
        mesaj = str(cevap.get("message", "")).lower()
        if "no transactions" in mesaj or "no records" in mesaj:
            return []
        raise RuntimeError(cevap.get("result") or cevap.get("message") or
                           "Etherscan isteği başarısız.")
    return cevap.get("result") or []


# =====================================================================
# Adres doğrulama
# =====================================================================
_EVM_ADRES = re.compile(r"^0x[0-9a-fA-F]{40}$")
_SOLANA_ADRES = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

# Sırların yanlışlıkla adres kutusuna yapıştırılmasını yakalamak için.
# Kullanıcıyı korumak, kabul edip sessizce saklamaktan iyidir.
_OZEL_ANAHTAR = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")


def validate_address(chain: str, address: str) -> tuple:
    """(temiz_adres, hata) döndürür."""
    ham = str(address or "").strip()
    if not ham:
        return None, "Adres boş olamaz."

    # ÖNCE bu: 12/24 kelimelik bir ifade veya 64 karakterlik hex, adres değil
    # SIRDIR. Sessizce reddetmek yetmez, kullanıcı ne yaptığını bilmeli.
    if len(ham.split()) >= 12:
        return None, ("Bu bir kurtarma ifadesine (seed phrase) benziyor. "
                      "CoinTakip asla kurtarma ifadesi veya özel anahtar "
                      "istemez ve saklamaz — yalnızca herkese açık adresinizi "
                      "girin. Bu ifadeyi hiçbir yere yazmayın.")
    if _OZEL_ANAHTAR.match(ham) and not _EVM_ADRES.match(ham):
        return None, ("Bu bir özel anahtara benziyor. CoinTakip yalnızca "
                      "herkese açık adres ister; özel anahtarınızı hiçbir "
                      "yere girmeyin.")

    if chain == "solana":
        if not _SOLANA_ADRES.match(ham):
            return None, "Geçerli bir Solana adresi değil."
        return ham, None
    if chain in EVM_CHAINS:
        if not _EVM_ADRES.match(ham):
            return None, "Geçerli bir EVM adresi değil (0x ile başlayan 42 karakter)."
        return ham.lower(), None
    return None, f"Bilinmeyen zincir: {chain}"


# Yaygın cüzdan ve donanım cüzdanı adları — yalnızca ÖNERİ listesidir.
# Kullanıcının defterine hiçbiri kendiliğinden eklenmez; `DEFAULT_LOCATIONS`
# ile karıştırılmamalı (oraya eklemek Kasa ekranında boş sekmeler üretirdi).
# Amaç, kullanıcının adı sıfırdan yazmak zorunda kalmaması.
SUGGESTED_WALLETS = [
    "METAMASK", "PHANTOM", "TRUST WALLET", "LEDGER", "TREZOR", "RABBY",
    "COINBASE WALLET", "EXODUS", "SOLFLARE", "BACKPACK", "KEPLR",
    "SAFEPAL", "TOKENPOCKET", "ZERION", "ARGENT",
]


def location_suggestions() -> list:
    """
    Konum kutusunda önerilecek adlar: kullanıcının defterinde fiilen geçenler
    ÖNCE, ardından yaygın cüzdan adları. Öneri listede olmak bir konumu var
    etmez — kullanıcı seçmedikçe hiçbir yere yazılmaz.
    """
    from data_manager import known_locations
    mevcut = list(known_locations())
    var = set(mevcut)
    return mevcut + [w for w in SUGGESTED_WALLETS if w not in var]


def duplicate_address_warnings(baglantilar=None) -> list:
    """
    Aynı adres birden çok KONUMDA kayıtlıysa uyarır.

    Gerçek durum: kullanıcı aynı tohum ifadesini hem MetaMask'e hem Phantom'a
    almış, dolayısıyla iki cüzdan aynı `0x…` adresini gösteriyor. Bunları iki
    ayrı konum olarak kaydetmek **aynı parayı iki kez saydırır** — ekranda iki
    satır çıkar, ikisi de deftere eklenirse varlık iki katına çıkar.

    Engellemek yerine uyarıyoruz: kullanıcı yeniden düzenleme yapıyor olabilir.
    Ama sessiz kalmak, tabloyu bozan bir hatayı görünmez kılardı.
    """
    baglantilar = baglantilar if baglantilar is not None else list_connections()
    adresler = {}
    for spec in baglantilar.values():
        anahtar = (str(spec.get("chain") or ""), str(spec.get("address") or "").lower())
        adresler.setdefault(anahtar, set()).add(spec.get("location"))
    uyarilar = []
    for (zincir, adres), konumlar in sorted(adresler.items()):
        if len(konumlar) > 1:
            uyarilar.append(
                f"Aynı adres birden çok konumda kayıtlı: {adres} ({zincir}) → "
                f"{', '.join(sorted(konumlar))}. Bu **aynı parayı iki kez saydırır**; "
                "muhtemelen aynı hesabı iki farklı cüzdan uygulamasına almışsınız. "
                "Bakiye tek bir yerde durduğu için yalnızca BİR konumda tutun."
            )
    return uyarilar


def supported_chains() -> list:
    """
    Arayüzün zincir listesi. Koddan türetilir, elle yazılmaz.

    `discovery` alanı arayüze taşınıyor ki kullanıcı zinciri SEÇERKEN otomatik
    token keşfinin orada çalışıp çalışmadığını görsün — tokenı gelmedikten
    sonra değil.
    """
    liste = [{"id": k, "name": v["name"], "native": v["native"], "family": "evm",
              "discovery": v["discovery"]}
             for k, v in EVM_CHAINS.items()]
    # Solana'da token keşfi için anahtar gerekmiyor: hesabın token hesapları
    # doğrudan RPC'den listeleniyor.
    liste.append({"id": "solana", "name": "Solana", "native": "SOL",
                  "family": "solana", "discovery": "builtin"})
    return liste


# =====================================================================
# Kayıt defteri
# =====================================================================
def validate_connection(spec: dict) -> tuple:
    """(temiz_tanim, hata) döndürür. Yalnızca doğrulama yapar, yazmaz."""
    if not isinstance(spec, dict):
        return None, "Bağlantı tanımı bir nesne olmalı."
    tur = str(spec.get("type") or "onchain").strip().lower()
    if tur not in CONNECTION_TYPES:
        return None, (f"Desteklenmeyen bağlantı türü: {tur}. "
                      "Bu sürümde yalnızca zincir üstü cüzdanlar destekleniyor; "
                      "borsa API'leri bir sonraki fazda geliyor.")

    zincir = str(spec.get("chain") or "").strip().lower()
    if zincir != "solana" and zincir not in EVM_CHAINS:
        return None, f"Bilinmeyen zincir: {zincir or '(boş)'}"

    adres, hata = validate_address(zincir, spec.get("address"))
    if hata:
        return None, hata

    tokenlar, gorulen = [], set()
    for t in (spec.get("tokens") or []):
        kontrat = str((t or {}).get("contract") or "").strip()
        if zincir != "solana" and not _EVM_ADRES.match(kontrat):
            return None, f"Geçersiz token kontrat adresi: {kontrat}"
        kontrat = kontrat.lower() if zincir != "solana" else kontrat
        if kontrat in gorulen:
            continue           # aynı token iki kez → iki kez sayılırdı
        gorulen.add(kontrat)
        try:
            ondalik = int((t or {}).get("decimals", 18))
        except (TypeError, ValueError):
            return None, f"Token ondalık hanesi sayı olmalı: {kontrat}"
        if not 0 <= ondalik <= 36:
            return None, f"Token ondalık hanesi 0-36 aralığında olmalı: {kontrat}"
        tokenlar.append({
            "contract": kontrat,
            "symbol": str((t or {}).get("symbol") or "").upper().strip()[:24],
            "decimals": ondalik,
        })
    if len(tokenlar) > MAX_MANUAL_TOKENS:
        return None, (f"En fazla {MAX_MANUAL_TOKENS} token elle tanımlanabilir; "
                      f"{len(tokenlar)} tanımlanmış. Her token ayrı bir zincir "
                      "isteği demek ve okuma süresi buna göre uzar.")

    return {
        "type": tur,
        "chain": zincir,
        "address": adres,
        "enabled": bool(spec.get("enabled", True)),
        "label": str(spec.get("label") or "").strip(),
        # Etherscan anahtarı yoksa token keşfi yapılamaz; kullanıcı takip etmek
        # istediği tokenları elle de tanımlayabilsin diye bu alan var.
        "tokens": tokenlar,
    }, None


"""
KİMLİK NEDEN ADRESTİR
---------------------
Bu kayıt defterinin anahtarı iki kez yanlış seçildi ve kullanıcı ikisini de
denemenin ilk dakikasında yakaladı.

1. Önce yalnızca **konum** anahtardı. `PHANTOM` + Solana kaydedildi, sonra
   `PHANTOM` + Ethereum kaydedilince ilki sessizce silindi.
2. Sonra **(konum, zincir)** çifti anahtar yapıldı. Bu da yetmedi: kullanıcının
   Phantom cüzdanında **Hesap 2 ve Hesap 3** var, ikisi de Solana ağında ve
   ikisinin de kendi tokenları var. Aynı çifte düştükleri için yine ezildiler.

Gerçek şu: bir cüzdan uygulaması bir kimlik değil, bir **kap**tır. İçinde
istediğin kadar hesap olur, her hesap birden çok zincirde yaşar. Benzersiz olan
tek şey **adrestir**. Bu yüzden her bağlantı kendi kimliğini (`c1`, `c2`, …)
taşır ve konum/zincir/adres birer alandır — anahtar değil.

Ders: kimliği kullanıcının verdiği isimden türetme; **varlığın gerçekte neyle
benzersizleştiğini** bul.
"""


def _yeni_id(mevcut) -> str:
    n = 1
    while f"c{n}" in mevcut:
        n += 1
    return f"c{n}"


def list_connections() -> dict:
    """
    Bağlantılar, kalıcı kimlikleriyle: `{"c1": {location, chain, address, …}}`.

    Eski biçimler (yalnızca konum anahtarlı, veya `KONUM@zincir` anahtarlı)
    okunurken çevrilir; kullanıcının elle düzeltmesi gerekmez.
    """
    from data_manager import load_settings, normalize_location
    ham = dict(load_settings().get("connections", {}) or {})
    cikti = {}
    for anahtar, spec in ham.items():
        if not isinstance(spec, dict):
            continue
        spec = dict(spec)
        if spec.get("location"):
            kimlik = anahtar if anahtar.startswith("c") and anahtar[1:].isdigit() \
                else _yeni_id(cikti)
        else:
            # Eski biçim: konum anahtarın içindeydi.
            konum = anahtar.split("@")[0] if "@" in anahtar else anahtar
            spec["location"] = normalize_location(konum)
            kimlik = _yeni_id(cikti)
        cikti[kimlik] = spec
    return cikti


def _kaydet(baglantilar):
    from data_manager import load_settings, save_settings
    settings = load_settings()
    settings["connections"] = baglantilar
    save_settings(settings)


def save_connection(location: str, spec: dict, conn_id=None) -> dict:
    """
    Bağlantı ekler veya günceller.

    `conn_id` verilirse o kayıt güncellenir. Verilmezse aynı (konum, zincir,
    adres) üçlüsü aranır — aynı adresi ikinci kez eklemek yeni kayıt değil
    güncellemedir. Bulunmazsa yeni kimlik üretilir; hiçbir kayıt EZİLMEZ.
    """
    from data_manager import normalize_location
    konum = normalize_location(location)
    if not konum:
        raise ValueError("Konum adı boş olamaz.")
    # Savunma: eğik çizgi taşıyan bir konum adı, yol çözümlemesinin yanlış uca
    # düştüğünün işaretidir. Bir kez oldu (`PHANTOM/TEST` diye sahte kayıt) ve
    # kullanıcı bunu ancak ekranda anlamsız bir hata olarak gördü.
    if "/" in konum or "\\" in konum:
        raise ValueError(f"Konum adı eğik çizgi içeremez: {konum}")
    temiz, hata = validate_connection(spec)
    if hata:
        raise ValueError(hata)
    temiz["location"] = konum

    baglantilar = list_connections()
    # Aynı adres BAŞKA bir konumda duruyorsa bu bir çift sayma hatasıdır.
    # Engellemiyoruz (kullanıcı taşıma yapıyor olabilir) ama sessiz de kalmıyoruz.
    cakisan = sorted({
        v.get("location") for k, v in baglantilar.items()
        if k != conn_id
        and v.get("chain") == temiz["chain"]
        and str(v.get("address", "")).lower() == temiz["address"].lower()
        and v.get("location") != konum
    })
    if conn_id and conn_id in baglantilar:
        kimlik = conn_id
    else:
        kimlik = next(
            (k for k, v in baglantilar.items()
             if v.get("location") == konum
             and v.get("chain") == temiz["chain"]
             and str(v.get("address", "")).lower() == temiz["address"].lower()),
            None) or _yeni_id(baglantilar)
    baglantilar[kimlik] = temiz
    _kaydet(baglantilar)
    logger.info("Bağlantı kaydedildi: %s (%s / %s)", kimlik, konum, temiz["chain"])
    if cakisan:
        # Dönüş şekli kirletilmiyor; uyarıyı API `duplicate_address_warnings()`
        # üzerinden veriyor. Burada yalnızca iz bırakıyoruz.
        logger.warning("Aynı adres birden çok konumda: %s → %s, %s",
                       temiz["address"], konum, ", ".join(cakisan))
    return {kimlik: temiz}


def delete_connection(conn_id: str) -> bool:
    baglantilar = list_connections()
    if baglantilar.pop(str(conn_id or "").strip(), None) is None:
        return False
    _kaydet(baglantilar)
    logger.info("Bağlantı silindi: %s", conn_id)
    return True


# =====================================================================
# EVM okuyucu
# =====================================================================
def _evm_native(chain, address):
    """Yerel coin bakiyesi. Genel RPC ile okunur — anahtar gerekmez."""
    bilgi = EVM_CHAINS[chain]
    ham = _rpc(bilgi["rpc"], "eth_getBalance", [address, "latest"])
    return int(ham, 16) / 1e18, bilgi["native"]


def _abi_string_coz(ham):
    """
    `symbol()` cevabını çözer.

    İki biçim var: modern ERC-20 dinamik `string` döndürür (offset, uzunluk,
    veri), eski tokenların bir kısmı ise `bytes32` döndürür. İkisini de
    okuyabilmek gerekiyor, çünkü kullanıcının elle ekleyeceği token eski
    olabilir.
    """
    if not ham or ham == "0x":
        return ""
    try:
        veri = bytes.fromhex(ham[2:])
    except ValueError:
        return ""
    if len(veri) >= 64:
        uzunluk = int.from_bytes(veri[32:64], "big")
        if 0 < uzunluk <= len(veri) - 64:
            return veri[64:64 + uzunluk].decode("utf-8", "ignore").strip()
    return veri.rstrip(b"\x00").decode("utf-8", "ignore").strip()


def evm_token_info(chain, contract) -> dict:
    """
    Bir token kontratından sembol ve ondalık haneyi okur.

    **API anahtarı gerekmez** — genel RPC'ye `decimals()` ve `symbol()`
    çağrısıdır. Elle token tanımlamanın işe yaramasının sebebi de budur:
    keşif ücretli olabilir ama bakiye okumak ücretsizdir. Kullanıcıdan ondalık
    hane istemek anlamsız olurdu; zincir zaten biliyor.
    """
    if chain not in EVM_CHAINS:
        raise ValueError(f"Bu zincirde elle token tanımlanamaz: {chain}")
    kontrat = str(contract or "").strip()
    if not _EVM_ADRES.match(kontrat):
        raise ValueError("Geçerli bir kontrat adresi değil (0x ile başlayan 42 "
                         "karakter). Token SEMBOLÜNÜ değil, kontrat adresini girin.")
    rpc = EVM_CHAINS[chain]["rpc"]
    ham = _rpc(rpc, "eth_call", [{"to": kontrat, "data": "0x313ce567"}, "latest"])
    if not ham or ham == "0x":
        raise ValueError(
            f"Bu adres {EVM_CHAINS[chain]['name']} üzerinde bir ERC-20 token "
            "kontratı gibi cevap vermiyor. Zinciri doğru seçtiğinizden emin "
            "olun — aynı sembolün her zincirde ayrı bir kontratı vardır.")
    ondalik = int(ham, 16)
    if ondalik > 36:
        raise ValueError("Kontrat beklenmeyen bir ondalık hane değeri döndürdü; "
                         "bu adres standart bir ERC-20 tokenı olmayabilir.")
    try:
        sembol = _abi_string_coz(
            _rpc(rpc, "eth_call", [{"to": kontrat, "data": "0x95d89b41"}, "latest"]))
    except Exception as e:
        logger.debug("Token sembolü okunamadı (%s): %s", kontrat, e)
        sembol = ""
    return {"contract": kontrat.lower(),
            "symbol": (sembol or kontrat[:8]).upper()[:24],
            "decimals": ondalik}


def _evm_token_balance(chain, address, contract, decimals):
    """`balanceOf(address)` çağrısı. Seçici: 0x70a08231."""
    veri = "0x70a08231" + "0" * 24 + address[2:]
    ham = _rpc(EVM_CHAINS[chain]["rpc"], "eth_call",
               [{"to": contract, "data": veri}, "latest"])
    if not ham or ham == "0x":
        return 0.0
    return int(ham, 16) / (10 ** int(decimals))


def _evm_discover_tokens(chain, address, api_key, limit=400):
    """
    Adresin dokunduğu ERC-20 tokenları transfer geçmişinden çıkarır.

    Bakiye uçları ücretli olduğu için ücretsiz katmanda yol budur: transfer
    kayıtları hangi tokenların hesaba girip çıktığını, sembolünü ve ondalık
    hanesini zaten taşır. Sonra her biri için tek tek bakiye okunur.
    """
    kayitlar = _etherscan(EVM_CHAINS[chain]["chain_id"], {
        "module": "account", "action": "tokentx", "address": address,
        "page": 1, "offset": limit, "sort": "desc",
    }, api_key)
    bulunan = {}
    for k in kayitlar:
        kontrat = str(k.get("contractAddress") or "").lower()
        if not kontrat or kontrat in bulunan:
            continue
        try:
            ondalik = int(k.get("tokenDecimal") or 18)
        except (TypeError, ValueError):
            ondalik = 18
        bulunan[kontrat] = {
            "contract": kontrat,
            "symbol": str(k.get("tokenSymbol") or "").upper().strip() or kontrat[:8],
            "decimals": ondalik,
        }
    return list(bulunan.values())


def read_evm(chain, address, api_key=None, tokens=None, key_stored=False):
    """
    (bakiyeler, notlar) — bakiye: [{asset, qty, contract}]

    İki ayrı yol var ve ikisi de gerekli:

    * **Otomatik keşif** — Etherscan'a transfer geçmişi sorulur, adresin
      dokunduğu tokenlar çıkarılır. Rahat ama zincire göre ücretli olabilir.
    * **Elle tanım** — kullanıcının verdiği kontrat adresleri. Anahtar
      gerektirmez, her zincirde çalışır, ücretsizdir.

    İkisi BİRLEŞTİRİLİR, biri diğerinin yerine geçmez. Önceki sürümde keşif
    başarılı olduğunda elle tanımlananlar sessizce düşüyordu; keşif penceresi
    dışında kalmış (400 kayıttan eski) bir tokenı kullanıcı elle eklemiş olsa
    bile göremezdi.
    """
    bilgi = EVM_CHAINS[chain]
    bakiyeler, notlar = [], []
    try:
        miktar, sembol = _evm_native(chain, address)
        if miktar > DUST_EPSILON:
            bakiyeler.append({"asset": sembol, "qty": miktar, "contract": None})
    except Exception as e:
        notlar.append(_not(NOTE_ERROR,
                           f"{bilgi['name']} yerel bakiyesi okunamadı: {e}"))

    elle = {t["contract"]: t for t in (tokens or []) if t.get("contract")}
    aday = dict(elle)
    kesif_yapildi = False

    if api_key and bilgi["discovery"] == "free":
        try:
            for t in _evm_discover_tokens(chain, address, api_key):
                aday.setdefault(t["contract"], t)
            kesif_yapildi = True
        except Exception as e:
            notlar.append(_not(NOTE_WARN,
                f"Token keşfi yapılamadı ({e}). Yalnızca yerel bakiye ve elle "
                "tanımladığınız tokenlar okundu."))
    else:
        # Keşif yapılamıyor. Bunun iki sebebi olabilir ve kullanıcının hangisi
        # olduğunu bilmesi gerekiyor — biri anahtar girmekle çözülür, diğeri
        # çözülmez ve elle tanım gerektirir.
        if bilgi["discovery"] == "paid":
            mesaj = (
                f"{bilgi['name']} otomatik token keşfi Etherscan'ın ÜCRETLİ "
                "planına dahil; ücretsiz anahtar bu zincirde kabul edilmiyor. "
                f"Bu yüzden yalnızca {bilgi['native']} ve elle tanımladığınız "
                "tokenlar okunur. Takip etmek istediğiniz tokenı bağlantıyı "
                "düzenleyip kontrat adresiyle ekleyin — bu yol anahtar "
                "gerektirmez ve ücretsizdir.")
        elif key_stored:
            # Anahtar VAR ama kasa kilitli. Bu ikisini aynı cümleyle anlatmak
            # kullanıcıyı olmayan bir işi yapmaya gönderiyordu: anahtarı zaten
            # girmişti, eksik olan tek şey kasayı açmaktı.
            mesaj = (
                "Etherscan anahtarınız kasada duruyor ama **kasa kilitli**, bu "
                f"yüzden token keşfi yapılamadı; yalnızca {bilgi['native']} ve "
                "elle tanımladığınız tokenlar okundu. Çözme anahtarı diskte "
                "durmadığı için uygulama her açıldığında kasayı yeniden açmanız "
                "gerekir: Anahtar Kasası → PIN → Kasayı Aç.")
        else:
            mesaj = (
                "Etherscan API anahtarı tanımlı olmadığı için token keşfi "
                f"yapılamadı; yalnızca {bilgi['native']} ve elle tanımladığınız "
                f"tokenlar okundu. {bilgi['name']} bu keşfin ücretsiz çalıştığı "
                "zincirlerden biri — anahtarı etherscan.io'dan alıp Anahtar "
                "Kasası bölümüne girmeniz yeterli.")
        # Kullanıcı tokenlarını zaten elle tanımlamışsa keşfin kapalı olması
        # bir eksiklik değil, bilinçli bir tercihtir. Alarm üretmiyoruz.
        notlar.append(_not(NOTE_INFO if elle else NOTE_WARN, mesaj))

    # Bakiyeler PARALEL okunur. Sıralı okuma, keşfin bulduğu her token için bir
    # tur ağ gecikmesi demekti: 100 tokenlı bir adres dakikalarca "Okunuyor…"
    # yazıyordu ve kullanıcı haklı olarak sürecin uzunluğundan şikâyet etti.
    # İşin tamamı ağ beklemesi olduğu için iş parçacığı burada doğru araç.
    for t, miktar, hata in _paralel(
            aday.values(),
            lambda t: _evm_token_balance(chain, address, t["contract"], t["decimals"])):
        if hata is not None:
            notlar.append(_not(NOTE_WARN,
                f"{t.get('symbol') or t['contract']} bakiyesi okunamadı: {hata}"))
            continue
        if miktar > DUST_EPSILON:
            bakiyeler.append({"asset": t["symbol"], "qty": miktar,
                              "contract": t["contract"]})

    # Elle tanımlanmış ama bakiyesi sıfır çıkan tokenı sessizce yutmak,
    # kullanıcıya "ekledim ama gelmedi" dedirtirdi. Bunu söylüyoruz.
    if elle:
        gelen = {b.get("contract") for b in bakiyeler}
        bos = [t["symbol"] or t["contract"][:10] for k, t in elle.items()
               if k not in gelen]
        if bos:
            notlar.append(_not(NOTE_INFO,
                "Elle tanımladığınız şu tokenların bu adreste bakiyesi yok: "
                + ", ".join(sorted(bos)) + "."))
        if kesif_yapildi:
            notlar.append(_not(NOTE_INFO,
                f"{len(elle)} token elle tanımlı; otomatik keşfe ek olarak okundu."))
    return bakiyeler, notlar


# =====================================================================
# Solana okuyucu
# =====================================================================
_SOLANA_TOKEN_LISTESI = {"at": 0.0, "map": {}}
# Jupiter'in doğrulanmış token listesi. Eski `tokens.jup.ag` alan adı artık
# çözülmüyor; güncel uç bu. Liste alınamazsa sistem sembol uydurmaz.
_SOLANA_LISTE_URL = "https://lite-api.jup.ag/tokens/v2/tag?query=verified"
_SOLANA_LISTE_TTL = 6 * 3600


def _solana_symbols():
    """
    Mint adresi → sembol eşlemesi (yalnızca DOĞRULANMIŞ tokenlar).

    Zincir mint adresini verir, sembolü vermez. Liste alınamazsa mint adresi
    kısaltılarak gösterilir — uydurma bir sembol yazmaktansa ham gerçeği
    göstermek doğrudur.

    Listede olmak ayrıca bir SİNYALDİR: Solana'da istenmeden gönderilen spam
    token yaygındır ve gerçek bir cüzdanda yüzlerce satır üretir. Doğrulanmış
    listede olmayan bakiyeler silinmez ama işaretlenir.
    """
    simdi = time.time()
    if _SOLANA_TOKEN_LISTESI["map"] and simdi - _SOLANA_TOKEN_LISTESI["at"] < _SOLANA_LISTE_TTL:
        return _SOLANA_TOKEN_LISTESI["map"]
    try:
        veri = _http_json(_SOLANA_LISTE_URL)
        eslem = {}
        for t in veri or []:
            # Uç `id` alanında mint adresini veriyor; eski biçim `address`'ti.
            adres = t.get("id") or t.get("address")
            sembol = str(t.get("symbol") or "").upper().strip()
            if adres and sembol:
                eslem[adres] = sembol
        if eslem:
            _SOLANA_TOKEN_LISTESI["map"] = eslem
            _SOLANA_TOKEN_LISTESI["at"] = simdi
    except Exception as e:
        logger.debug("Solana token listesi alınamadı: %s", e)
    return _SOLANA_TOKEN_LISTESI["map"]


def read_solana(address):
    """(bakiyeler, notlar). Anahtar gerekmez — genel RPC yeter."""
    bakiyeler, notlar = [], []
    try:
        lamport = _rpc(SOLANA_RPC, "getBalance", [address])
        miktar = float((lamport or {}).get("value", 0)) / 1e9
        if miktar > DUST_EPSILON:
            bakiyeler.append({"asset": "SOL", "qty": miktar, "contract": None})
    except Exception as e:
        notlar.append(_not(NOTE_ERROR, f"SOL bakiyesi okunamadı: {e}"))

    try:
        sonuc = _rpc(SOLANA_RPC, "getTokenAccountsByOwner",
                     [address, {"programId": SPL_TOKEN_PROGRAM},
                      {"encoding": "jsonParsed"}])
        eslem = _solana_symbols()
        for hesap in (sonuc or {}).get("value", []):
            try:
                bilgi = hesap["account"]["data"]["parsed"]["info"]
                mint = bilgi["mint"]
                miktar = float(bilgi["tokenAmount"].get("uiAmount") or 0.0)
            except (KeyError, TypeError, ValueError):
                continue
            if miktar <= DUST_EPSILON:
                continue
            sembol = eslem.get(mint)
            bakiyeler.append({
                "asset": sembol or (mint[:4] + "…" + mint[-4:]),
                "qty": miktar, "contract": mint,
                # Doğrulanmış listede yoksa büyük ihtimalle istenmeden
                # gönderilmiş spam. Silinmiyor — gizlemek de bir tür yalandır —
                # ama işaretleniyor ki arayüz varsayılan olarak katlayabilsin.
                "verified": bool(sembol),
            })
        dogrulanmamis = sum(1 for b in bakiyeler if b.get("verified") is False)
        if dogrulanmamis:
            # BİLGİ notu, eksiklik değil: bu tokenlar okundu ve tabloda
            # duruyorlar. Yalnızca tanınmış listede olmadıkları söyleniyor.
            # Bunu "eksik okundu" saymak kullanıcıya olmayan bir sorun
            # gösteriyordu.
            notlar.append(_not(NOTE_INFO,
                f"{dogrulanmamis} token doğrulanmış listede yok. Solana'da "
                "istenmeden gönderilen spam token yaygındır; bunlar gizlenmedi "
                "ama ayrı gösteriliyor. Tanımadığınız bir tokenın sitesine "
                "bağlanmayın."))
        if not eslem:
            notlar.append(_not(NOTE_WARN,
                "Token adı listesi alınamadı; semboller yerine kısaltılmış mint "
                "adresleri gösteriliyor."))
    except Exception as e:
        notlar.append(_not(NOTE_ERROR, f"SPL token bakiyeleri okunamadı: {e}"))
    return bakiyeler, notlar


# =====================================================================
# Tek bağlantı okuma
# =====================================================================
def read_connection(conn_id, spec=None):
    """
    Bir bağlantının canlı bakiyesini okur. **Hiçbir şey yazmaz.**

    Ağ hatası bir istisna değil, raporlanacak bir durumdur: kullanıcı hangi
    bağlantının okunamadığını görmeli, boş bir liste görüp "hiç varlığım yok"
    sanmamalı.
    """
    from data_manager import normalize_location
    if spec is None:
        spec = list_connections().get(str(conn_id or "").strip())
    konum = normalize_location((spec or {}).get("location") or "")

    if not spec:
        notlar = [_not(NOTE_ERROR, "Tanımlı bağlantı bulunamadı.")]
        return {"id": conn_id, "location": konum, "ok": False, "balances": [],
                "notes": notlar, "incomplete": True}

    zincir = spec.get("chain")
    baslangic = time.time()
    try:
        if zincir == "solana":
            bakiyeler, notlar = read_solana(spec["address"])
        else:
            anahtar, kasada_var = None, False
            try:
                import keyvault
                # `has()` kilitliyken de çalışır: "anahtar yok" ile "anahtar
                # var ama kasa kilitli" ayrı sorunlar, ayrı çözümleri var.
                kasada_var = keyvault.has(ETHERSCAN_KEY_NAME)
                if keyvault.is_unlocked():
                    anahtar = keyvault.get(ETHERSCAN_KEY_NAME)
            except Exception as e:
                logger.debug("Kasa okunamadı: %s", e)
            bakiyeler, notlar = read_evm(zincir, spec["address"], anahtar,
                                         spec.get("tokens"),
                                         key_stored=kasada_var)
        return {
            "id": conn_id, "location": konum, "ok": True, "chain": zincir,
            "label": spec.get("label", ""),
            "address": spec["address"], "balances": bakiyeler,
            "notes": notlar,
            # "Okundu" ile "eksiksiz okundu" aynı şey değil: bağlantı cevap
            # vermiş olabilir ama tokenları gelmemiş olabilir.
            "incomplete": is_incomplete(notlar),
            "token_count": len(spec.get("tokens") or []),
            "elapsed_ms": int((time.time() - baslangic) * 1000),
            "read_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    except Exception as e:
        logger.warning("Bağlantı okunamadı (%s): %s", conn_id, e)
        return {"id": conn_id, "location": konum, "ok": False, "chain": zincir,
                "label": spec.get("label", ""),
                "address": spec.get("address"), "balances": [],
                "notes": [_not(NOTE_ERROR, f"Bağlantı okunamadı: {e}")],
                "incomplete": True}


def test_connection(conn_id, spec=None):
    """Bağlantıyı dener ve özet döner. Kaydetmeden önce denemek için."""
    sonuc = read_connection(conn_id, spec)
    sonuc["asset_count"] = len(sonuc.get("balances", []))
    return sonuc


# =====================================================================
# Toplu okuma ve defterle karşılaştırma
# =====================================================================
def read_all(only_enabled=True):
    """
    (bağlantı kimliği → okuma) sözlüğü.

    Bağlantılar birbirinden bağımsız olduğu için PARALEL okunur: dört cüzdanı
    sırayla beklemek, toplam süreyi en yavaş olanın değil hepsinin toplamı
    yapıyordu.
    """
    ciftler = [(k, s) for k, s in list_connections().items()
               if not (only_enabled and not s.get("enabled", True))]
    sonuc = {}
    for (kimlik, spec), okuma, hata in _paralel(
            ciftler, lambda ks: read_connection(ks[0], ks[1])):
        # `read_connection` kendi hatalarını zaten rapora çeviriyor; buraya
        # düşen bir istisna beklenmedik demektir ve yutulmamalı.
        sonuc[kimlik] = okuma if hata is None else {
            "id": kimlik, "location": spec.get("location"), "ok": False,
            "chain": spec.get("chain"), "label": spec.get("label", ""),
            "address": spec.get("address"), "balances": [],
            "notes": [_not(NOTE_ERROR, f"Bağlantı okunamadı: {hata}")],
            "incomplete": True}
    return sonuc


def live_balance(asset, location, readings=None):
    """
    Bir (varlık, konum) için canlı bakiye — o konumun TÜM bağlantıları toplanarak.

    Bir cüzdan birden çok hesap ve birden çok zincir barındırabilir; kullanıcının
    defterindeki konum ise tektir. Bu yüzden toplama konum düzeyinde yapılır:
    Phantom'un Hesap 2'sindeki ve Hesap 3'ündeki SOL, defterde tek bir
    `PHANTOM` bakiyesidir.

    `None` ile `0.0` arasındaki fark önemlidir: birincisi "bilmiyorum",
    ikincisi "orada hiç yok". İkisini karıştırmak, okunamayan bir cüzdanı boş
    sanıp kullanıcının varlığını silmeye kalkmak demektir. Bu yüzden bir zincir
    okunamadıysa ve varlık diğerlerinde de bulunmadıysa cevap "sıfır" değil
    "bilinmiyor"dur — o varlık okunamayan zincirde duruyor olabilir.
    """
    from data_manager import normalize_location
    from reconcile import normalize_asset
    konum = normalize_location(location)
    okumalar = readings if readings is not None else read_all()
    ilgili = [o for o in okumalar.values() if o.get("location") == konum]
    if not ilgili:
        return None
    okunabilir = [o for o in ilgili if o.get("ok")]
    if not okunabilir:
        return None

    hedef = normalize_asset(asset)
    toplam, bulundu = 0.0, False
    for okuma in okunabilir:
        for b in okuma.get("balances", []):
            if normalize_asset(b.get("asset")) == hedef:
                toplam += float(b.get("qty") or 0.0)
                bulundu = True
    if bulundu:
        return toplam
    # Hiçbirinde yok. "Sıfır" diyebilmek için konumun HER zinciri okunmuş olmalı.
    return 0.0 if len(okunabilir) == len(ilgili) else None


def compare_with_ledger(data=None):
    """
    Canlı cüzdan bakiyeleriyle defteri karşılaştırır. **Yazma yok.**

    F3'ün dosya tabanlı mutabakatının zincir üstü karşılığı. Aynı dürüstlük
    kuralı geçerli: okunamayan bir bağlantı "fark" değil "bilinmiyor"dur.
    """
    from data_manager import load_portfolio, ACTIVE_STATUS, normalize_location
    from reconcile import normalize_asset, _yakin
    if data is None:
        data = load_portfolio()

    okumalar = read_all()
    # Bağlantısı olan konumlar — bir konumun birden çok hesabı ve zinciri olabilir.
    bagli_konumlar = {o.get("location") for o in okumalar.values()}
    zincirler = {}
    for o in okumalar.values():
        zincirler.setdefault(o.get("location"), []).append(o.get("chain"))

    defter = {}
    for tx in data.get("transactions", []):
        if tx.get("status") != ACTIVE_STATUS:
            continue
        ham = str(tx.get("coin") or "").upper().strip()
        varlik = normalize_asset(ham[:-4] if ham.endswith("USDT") and len(ham) > 4 else ham)
        konum = normalize_location(tx.get("exchange"))
        if konum not in bagli_konumlar:
            continue
        anahtar = (varlik, konum)
        d = defter.setdefault(anahtar, {"qty": 0.0, "coin": ham})
        d["qty"] += float(tx.get("qty") or 0.0)

    ciftler = set(defter)
    dogrulanmis = {}
    for okuma in okumalar.values():
        if not okuma.get("ok"):
            continue
        for b in okuma.get("balances", []):
            anahtar = (normalize_asset(b.get("asset")), okuma.get("location"))
            ciftler.add(anahtar)
            # Bir varlık tek bir kaynakta bile doğrulanmışsa doğrulanmış sayılır.
            dogrulanmis[anahtar] = (dogrulanmis.get(anahtar, False)
                                    or b.get("verified", True))

    satirlar = []
    for varlik, konum in sorted(ciftler):
        defter_qty = defter.get((varlik, konum), {}).get("qty", 0.0)
        canli = live_balance(varlik, konum, okumalar)

        if canli is None:
            durum, not_metni = "unreadable", (
                "Bağlantı okunamadı. Bu bir fark değil — bakiye bilinmiyor.")
        elif _yakin(canli, defter_qty) or (canli <= DUST_EPSILON and defter_qty <= DUST_EPSILON):
            durum, not_metni = "match", ""
        elif defter_qty <= DUST_EPSILON:
            durum, not_metni = "only_chain", (
                "Zincirde var, defterinizde yok. Kaydetmeyi unutmuş "
                "olabilirsiniz.")
        elif canli <= DUST_EPSILON:
            durum, not_metni = "only_ledger", (
                "Defterinizde var ama bu adreste yok. Başka bir cüzdana taşımış "
                "veya satmış olabilirsiniz.")
        else:
            durum, not_metni = "mismatch", "Zincirdeki miktar defterinizle uyuşmuyor."

        # Defterinizde olan her şey ilgilidir; doğrulanmamış olsa da gizlenmez.
        # Yalnızca defterde HİÇ olmayan, doğrulanmamış zincir bakiyeleri
        # "muhtemelen spam" sayılır ve arayüz onları katlar.
        varlik_dogrulanmis = dogrulanmis.get((varlik, konum), True)
        satirlar.append({
            "asset": varlik, "location": konum,
            "chains": sorted({z for z in zincirler.get(konum, []) if z}),
            "ledger_qty": defter_qty,
            "chain_qty": canli,
            "diff_qty": None if canli is None else canli - defter_qty,
            "status": durum, "note": not_metni,
            "verified": bool(varlik_dogrulanmis),
            "likely_spam": bool(not varlik_dogrulanmis and defter_qty <= DUST_EPSILON),
        })

    sira = {"mismatch": 0, "only_chain": 1, "only_ledger": 2,
            "unreadable": 3, "match": 4}
    satirlar.sort(key=lambda r: (r["likely_spam"], sira.get(r["status"], 5),
                                 r["location"], r["asset"]))
    # Sayımlar yalnızca ilgili satırları anlatır; 130 spam token "130 fark var"
    # diye görünseydi gerçek farklar gürültüde kaybolurdu.
    sayim = {}
    for r in satirlar:
        if r["likely_spam"]:
            continue
        sayim[r["status"]] = sayim.get(r["status"], 0) + 1
    spam_adedi = sum(1 for r in satirlar if r["likely_spam"])

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "connections": {k: {"ok": v.get("ok"), "location": v.get("location"),
                            "chain": v.get("chain"), "address": v.get("address"),
                            "label": v.get("label", ""),
                            "notes": v.get("notes", []),
                            "incomplete": bool(v.get("incomplete")),
                            "token_count": v.get("token_count", 0)}
                        for k, v in okumalar.items()},
        "rows": satirlar,
        "status_counts": sayim,
        "spam_count": spam_adedi,
        # Aynı adresin iki konumda olması tabloyu bozar; raporun başında durur.
        "warnings": duplicate_address_warnings(),
        "read_only": True,
    }
