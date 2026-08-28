"""
CoinTakip — Borsa Mutabakatı (FAZ F3)
=====================================================================

NE YAPAR, NE YAPMAZ
-------------------
Bu modül borsadan indirilen dışa aktarım dosyalarını okur ve kullanıcının
defteriyle KARŞILAŞTIRIR. **Deftere hiçbir şey yazmaz.**

Bu bilinçli bir mimari karardır. "Borsa geçmişini içe aktar, defteri yeniden
kur" yaklaşımı denendiğinde şu sorunlarla boğuşmak gerekiyordu: mükerrer
tespiti, kısmi dolumlar, BNB ile ödenen komisyonlar, dönüşümler, toz bakiyeler.
Bir hata maliyet tabanını bozar — yani sistemin tek gerçek değerini.

Bunun yerine: **maliyet tabanı kullanıcının elle girdiği hâliyle kalır, borsa
onu asla ezmez.** Sistem sadece "borsa ne diyor, defterin ne diyor, fark nerede"
sorusunu cevaplar. Ne aktarılacağına kullanıcı karar verir.

NEDEN API DEĞİL DOSYA
---------------------
Borsaların API'si geçmişi vermiyor: Binance ~2 yıl, MEXC 1 ay. Kullanıcının
web arayüzünden indirdiği dosyalar 2023-02'ye kadar iniyor — yani API'nin
ULAŞAMADIĞI derinlik. Ayrıca dosya okumak API anahtarı gerektirmediği için
anahtar güvenliği riski hiç doğmuyor.

DÜRÜSTLÜK KURALI
----------------
Rapor, "uyuşmuyor" ile "dosya o kadar geriye gitmiyor"u BİRBİRİNDEN AYIRMAK
ZORUNDADIR. Kapsam penceresinin dışında kalan bir pozisyonu "fark var" diye
göstermek, kullanıcıyı olmayan bir hatayı kovalamaya iter. Her borsa için
kapsam aralığı hesaplanır ve rapora yazılır.
"""

import csv
import glob
import os
import re
from datetime import datetime

from log_config import get_logger

logger = get_logger("reconcile")

# Dolara ~1:1 sabitli kotasyon varlıkları. Kullanıcının 430 Binance
# dolumunun tamamı USDT veya BUSD; yani USD dönüşümü sorunu bu veri setinde
# doğmuyor. Yine de liste açık tutuldu.
STABLE_QUOTES = {"USDT", "BUSD", "USDC", "FDUSD", "TUSD", "DAI"}

# Borsalar aynı varlığı farklı adlandırabiliyor. MEXC, Tether Gold'u
# `GOLD(XAUT)` diye yazıyor; defterde `XAUT` olarak duruyor. Takma ad tablosu
# olmadan mutabakat bunu "iki ayrı coin" sanır ve sahte fark üretir.
ASSET_ALIASES = {
    "GOLD(XAUT)": "XAUT",
    "XAUT0": "XAUT",
}

# Miktar karşılaştırmasında görece tolerans. Borsa ondalık yuvarlaması ve
# kullanıcının elle girdiği yuvarlanmış miktarlar birebir tutmaz.
QTY_TOLERANCE_PCT = 0.5
QTY_TOLERANCE_ABS = 1e-8


def export_root():
    """Dışa aktarım klasörü — proje kökündeki `borsa_exports/`."""
    from data_manager import BASE_DIR
    return os.path.join(BASE_DIR, "borsa_exports")


def normalize_asset(name):
    t = str(name or "").upper().strip()
    return ASSET_ALIASES.get(t, t)


_MIKTAR_RE = re.compile(r"^\s*(-?[\d.,]+)\s*([A-Z0-9()._-]*)\s*$", re.IGNORECASE)


def parse_amount_with_asset(text):
    """
    Binance/MEXC dışa aktarımları miktarı ve varlığı BİTİŞİK yazar:
    `"0.00089BTC"` → `(0.00089, "BTC")`, `"0USDT"` → `(0.0, "USDT")`.
    Varlık yoksa (düz sayı) ikinci değer boş döner.
    """
    if text is None:
        return 0.0, ""
    m = _MIKTAR_RE.match(str(text))
    if not m:
        return 0.0, ""
    ham = m.group(1).replace(",", "")
    try:
        deger = float(ham)
    except ValueError:
        return 0.0, ""
    return deger, normalize_asset(m.group(2))


def split_pair(pair, quote_hint=""):
    """`BTCUSDT` / `GOLD(XAUT)_USDT` → ("BTC","USDT") / ("XAUT","USDT")."""
    p = str(pair or "").upper().strip()
    if "_" in p:
        taban, _, kot = p.partition("_")
        return normalize_asset(taban), normalize_asset(kot)
    if quote_hint and p.endswith(quote_hint) and len(p) > len(quote_hint):
        return normalize_asset(p[:-len(quote_hint)]), normalize_asset(quote_hint)
    for q in sorted(STABLE_QUOTES | {"BTC", "ETH", "BNB", "TRY"}, key=len, reverse=True):
        if p.endswith(q) and len(p) > len(q):
            return normalize_asset(p[:-len(q)]), normalize_asset(q)
    return normalize_asset(p), ""


def _olay(exchange, zaman, kind, asset, qty, **ek):
    olay = {
        "exchange": exchange,
        "time": str(zaman or "")[:19],
        "kind": kind,                    # TRADE | DEPOSIT | WITHDRAW
        "asset": normalize_asset(asset),
        "qty": float(qty or 0.0),        # işaretli: + giriş, − çıkış
        "quote_asset": "",
        "quote_qty": 0.0,
        "price": 0.0,
        "fee_asset": "",
        "fee_qty": 0.0,
        "usd_value": 0.0,
        "usd_known": False,
        "source": "",
    }
    olay.update(ek)
    return olay


# ---------------------------------------------------------------------
# Binance okuyucuları
# ---------------------------------------------------------------------
def load_binance_trades(path):
    olaylar, uyarilar = [], []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for satir in csv.DictReader(f):
            try:
                miktar, taban = parse_amount_with_asset(satir.get("Executed"))
                tutar, kot = parse_amount_with_asset(satir.get("Amount"))
                komisyon, kom_varlik = parse_amount_with_asset(satir.get("Fee"))
                if not taban:
                    taban, kot2 = split_pair(satir.get("Pair"), kot)
                    kot = kot or kot2
                yon = str(satir.get("Side", "")).upper()
                isaret = 1.0 if yon.startswith("B") else -1.0

                # Komisyon coin'in KENDİSİNDEN alındıysa eline geçen miktar
                # o kadar azalır. Binance'in "Executed" sütunu komisyon
                # düşülmeden önceki dolum miktarıdır.
                net = miktar
                if isaret > 0 and kom_varlik and normalize_asset(kom_varlik) == normalize_asset(taban):
                    net = miktar - komisyon

                olaylar.append(_olay(
                    "BINANCE", satir.get("Time"), "TRADE", taban, isaret * net,
                    quote_asset=kot, quote_qty=-isaret * tutar,
                    price=float(satir.get("Price") or 0.0),
                    fee_asset=kom_varlik, fee_qty=komisyon,
                    usd_value=tutar if kot in STABLE_QUOTES else 0.0,
                    usd_known=kot in STABLE_QUOTES,
                    source=os.path.basename(path),
                ))
            except Exception as e:
                uyarilar.append(f"Binance işlem satırı okunamadı: {e}")
    return olaylar, uyarilar


def _binance_transfer(path, kind, isaret):
    olaylar, uyarilar = [], []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for satir in csv.DictReader(f):
            try:
                if str(satir.get("Status", "")).lower() not in ("completed", "success", ""):
                    continue
                miktar = float(str(satir.get("Amount") or 0).replace(",", ""))
                olaylar.append(_olay(
                    "BINANCE", satir.get("Time"), kind, satir.get("Coin"),
                    isaret * miktar,
                    fee_qty=float(str(satir.get("Fee") or 0).replace(",", "") or 0),
                    fee_asset=normalize_asset(satir.get("Coin")),
                    source=os.path.basename(path),
                ))
            except Exception as e:
                uyarilar.append(f"Binance {kind} satırı okunamadı: {e}")
    return olaylar, uyarilar


def load_binance_deposits(path):
    return _binance_transfer(path, "DEPOSIT", 1.0)


def load_binance_withdrawals(path):
    return _binance_transfer(path, "WITHDRAW", -1.0)


# ---------------------------------------------------------------------
# MEXC okuyucuları
# ---------------------------------------------------------------------
def _xlsx_rows(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        satirlar = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not satirlar:
        return []
    basliklar = [str(c) if c is not None else "" for c in satirlar[0]]
    return [dict(zip(basliklar, r)) for r in satirlar[1:]
            if r and any(c is not None for c in r)]


def load_mexc_trades(path):
    olaylar, uyarilar = [], []
    for satir in _xlsx_rows(path):
        try:
            taban, kot = split_pair(satir.get("Pairs"))
            miktar = float(str(satir.get("Executed Amount") or 0).replace(",", ""))
            tutar = float(str(satir.get("Total") or 0).replace(",", ""))
            komisyon, kom_varlik = parse_amount_with_asset(satir.get("Fee"))
            yon = str(satir.get("Side", "")).upper()
            isaret = 1.0 if yon.startswith("B") else -1.0

            net = miktar
            if isaret > 0 and kom_varlik and normalize_asset(kom_varlik) == taban:
                net = miktar - komisyon

            olaylar.append(_olay(
                "MEXC", satir.get("Time"), "TRADE", taban, isaret * net,
                quote_asset=kot, quote_qty=-isaret * tutar,
                price=float(str(satir.get("Filled Price") or 0).replace(",", "")),
                fee_asset=kom_varlik, fee_qty=komisyon,
                usd_value=tutar if kot in STABLE_QUOTES else 0.0,
                usd_known=kot in STABLE_QUOTES,
                source=os.path.basename(path),
            ))
        except Exception as e:
            uyarilar.append(f"MEXC işlem satırı okunamadı: {e}")
    return olaylar, uyarilar


def load_mexc_statement(path):
    """
    MEXC ekstresinden YALNIZCA para yatırma/çekme alınır.

    'Spot Trading' satırları işlem dosyasında zaten var; ikisini birden almak
    her alımı iki kez saydırırdı. Vadeli hesap transferleri de spot bakiyeyi
    ilgilendirmediği için atlanır.
    """
    olaylar, uyarilar = [], []
    for satir in _xlsx_rows(path):
        try:
            tip = str(satir.get("Transaction Type") or "").strip().lower()
            if tip not in ("deposit", "withdraw"):
                continue
            miktar = float(str(satir.get("Quantity") or 0).replace(",", ""))
            kind = "DEPOSIT" if tip == "deposit" else "WITHDRAW"
            # Ekstre çıkışları zaten negatif yazıyor; işareti tipe göre sabitliyoruz.
            miktar = abs(miktar) * (1.0 if kind == "DEPOSIT" else -1.0)
            olaylar.append(_olay(
                "MEXC", satir.get("Creation Time(UTC+03:00)") or satir.get("Creation Time"),
                kind, satir.get("Crypto"), miktar,
                source=os.path.basename(path),
            ))
        except Exception as e:
            uyarilar.append(f"MEXC ekstre satırı okunamadı: {e}")
    return olaylar, uyarilar


# ---------------------------------------------------------------------
# Dosya keşfi ve yükleme
# ---------------------------------------------------------------------
# (dosya adı kalıbı, borsa, tür, okuyucu)
FILE_PATTERNS = [
    ("*Spot-Trade-History*.csv", "BINANCE", "trades", load_binance_trades),
    ("*Deposit-History*.csv", "BINANCE", "deposits", load_binance_deposits),
    ("*Withdraw-History*.csv", "BINANCE", "withdrawals", load_binance_withdrawals),
    ("*Trade History*.xlsx", "MEXC", "trades", load_mexc_trades),
    ("*Statement*.xlsx", "MEXC", "statement", load_mexc_statement),
]


def discover_export_files(root=None):
    """Klasör yapısından bağımsız olarak tanınan dosyaları bulur."""
    root = root or export_root()
    bulunan = []
    if not os.path.isdir(root):
        return bulunan
    for kalip, borsa, tur, okuyucu in FILE_PATTERNS:
        for yol in glob.glob(os.path.join(root, "**", kalip), recursive=True):
            # 'Order History' dolum değil emirdir; 'Trade History' ile karışmasın.
            if "order history" in os.path.basename(yol).lower():
                continue
            bulunan.append({"path": yol, "name": os.path.basename(yol),
                            "exchange": borsa, "kind": tur, "_loader": okuyucu})
    bulunan.sort(key=lambda d: (d["exchange"], d["kind"], d["name"]))
    return bulunan


def load_all_events(root=None):
    """(olaylar, kaynak_bilgisi, uyarilar)"""
    olaylar, kaynaklar, uyarilar = [], [], []
    for dosya in discover_export_files(root):
        try:
            yeni, uy = dosya["_loader"](dosya["path"])
        except Exception as e:
            uyarilar.append(f"{dosya['name']} okunamadı: {e}")
            logger.warning("Mutabakat dosyası okunamadı (%s): %s", dosya["name"], e)
            continue
        olaylar.extend(yeni)
        uyarilar.extend(uy)
        tarihler = sorted(o["time"] for o in yeni if o["time"])
        kaynaklar.append({
            "name": dosya["name"], "exchange": dosya["exchange"],
            "kind": dosya["kind"], "rows": len(yeni),
            "first": tarihler[0][:10] if tarihler else None,
            "last": tarihler[-1][:10] if tarihler else None,
        })
    return olaylar, kaynaklar, uyarilar


def coverage_windows(olaylar):
    """
    Borsa başına kapsam aralığı.

    Rapor "uyuşmuyor" ile "dosya o kadar geriye gitmiyor"u ayırt edebilsin
    diye şart. MEXC dışa aktarımı 2024-10'da başlıyor; ondan önce alınmış bir
    coin dosyada YOK, ama bu bir tutarsızlık değil.
    """
    pencere = {}
    for o in olaylar:
        if not o["time"]:
            continue
        p = pencere.setdefault(o["exchange"], {"first": o["time"][:10], "last": o["time"][:10]})
        p["first"] = min(p["first"], o["time"][:10])
        p["last"] = max(p["last"], o["time"][:10])
    return pencere


# ---------------------------------------------------------------------
# Özetleme ve mutabakat
# ---------------------------------------------------------------------
def build_asset_summary(olaylar):
    """Varlık bazında borsa tarafının özeti."""
    ozet = {}
    for o in olaylar:
        a = o["asset"]
        if not a:
            continue
        s = ozet.setdefault(a, {
            "asset": a, "bought_qty": 0.0, "sold_qty": 0.0,
            "deposited_qty": 0.0, "withdrawn_qty": 0.0,
            "buy_cost_usd": 0.0, "buy_qty_usd_known": 0.0,
            "sell_proceeds_usd": 0.0, "trade_count": 0,
            "exchanges": set(), "first": None, "last": None,
            "usd_unknown_trades": 0,
        })
        s["exchanges"].add(o["exchange"])
        t = o["time"][:10] if o["time"] else None
        if t:
            s["first"] = t if s["first"] is None else min(s["first"], t)
            s["last"] = t if s["last"] is None else max(s["last"], t)

        if o["kind"] == "TRADE":
            s["trade_count"] += 1
            if o["qty"] >= 0:
                s["bought_qty"] += o["qty"]
                if o["usd_known"]:
                    s["buy_cost_usd"] += o["usd_value"]
                    s["buy_qty_usd_known"] += o["qty"]
                else:
                    s["usd_unknown_trades"] += 1
            else:
                s["sold_qty"] += -o["qty"]
                if o["usd_known"]:
                    s["sell_proceeds_usd"] += o["usd_value"]
                else:
                    s["usd_unknown_trades"] += 1
        elif o["kind"] == "DEPOSIT":
            s["deposited_qty"] += o["qty"]
        elif o["kind"] == "WITHDRAW":
            s["withdrawn_qty"] += -o["qty"]

    for s in ozet.values():
        s["exchanges"] = sorted(s["exchanges"])
        s["on_exchange_qty"] = (s["bought_qty"] - s["sold_qty"]
                                + s["deposited_qty"] - s["withdrawn_qty"])
        s["acquired_qty"] = s["bought_qty"] + s["deposited_qty"]
        s["exchange_avg_cost"] = (s["buy_cost_usd"] / s["buy_qty_usd_known"]
                                  if s["buy_qty_usd_known"] > 0 else 0.0)
    return ozet


def ledger_summary(data):
    """Defterdeki aktif pozisyonların varlık bazında özeti."""
    from data_manager import ACTIVE_STATUS
    ozet = {}
    for tx in data.get("transactions", []):
        if tx.get("status") != ACTIVE_STATUS:
            continue
        ham = str(tx.get("coin") or "").upper().strip()
        varlik = normalize_asset(ham[:-4] if ham.endswith("USDT") and len(ham) > 4 else ham)
        if not varlik:
            continue
        qty = float(tx.get("qty") or 0.0)
        cost = float(tx.get("cost") or 0.0)
        s = ozet.setdefault(varlik, {"asset": varlik, "qty": 0.0, "invested": 0.0,
                                     "locations": set(), "lots": 0, "first_date": None})
        s["qty"] += qty
        s["invested"] += qty * cost
        s["locations"].add(str(tx.get("exchange") or "BINANCE").upper())
        s["lots"] += 1
        tarih = str(tx.get("date") or "")[:10]
        if tarih:
            s["first_date"] = tarih if s["first_date"] is None else min(s["first_date"], tarih)
    for s in ozet.values():
        s["locations"] = sorted(s["locations"])
        s["avg_cost"] = (s["invested"] / s["qty"]) if s["qty"] > 0 else 0.0
    return ozet


def _yakin(a, b):
    fark = abs(a - b)
    if fark <= QTY_TOLERANCE_ABS:
        return True
    olcek = max(abs(a), abs(b))
    return olcek > 0 and (fark / olcek * 100.0) <= QTY_TOLERANCE_PCT


def reconcile(data, root=None):
    """
    Borsa dosyalarıyla defteri karşılaştırır. **Deftere hiçbir şey yazmaz.**
    """
    olaylar, kaynaklar, uyarilar = load_all_events(root)
    pencere = coverage_windows(olaylar)
    borsa = build_asset_summary(olaylar)
    defter = ledger_summary(data)

    satirlar = []
    for varlik in sorted(set(borsa) | set(defter)):
        b = borsa.get(varlik)
        d = defter.get(varlik)
        d_qty = d["qty"] if d else 0.0
        b_kalan = b["on_exchange_qty"] if b else 0.0

        # --- Kapsam kanıtı ---
        # Dosyaların geçmişi kapsamadığını İSPATLAYAN iki sinyal var; ikisi de
        # varken "fark var" demek kullanıcıyı olmayan bir hatayı kovalamaya iter.
        konumlar = set(d["locations"]) if d else set()
        kapsanan_konum = bool(konumlar & set(pencere.keys()))

        # 1) Negatif borsa bakiyesi FİZİKSEL OLARAK İMKÂNSIZDIR. Çıkan miktar
        #    girenden fazlaysa, alım penceresinden önce olmuş demektir.
        negatif_kanit = b is not None and b_kalan < -QTY_TOLERANCE_ABS

        # 2) Defterdeki en eski lot, dosyaların başlangıcından öncesindeyse
        #    o alım dosyada zaten olamaz.
        pencere_basi = None
        if b and b["exchanges"]:
            adaylar = [pencere[x]["first"] for x in b["exchanges"] if x in pencere]
            pencere_basi = min(adaylar) if adaylar else None
        elif pencere:
            pencere_basi = min(p["first"] for p in pencere.values())
        tarih_kaniti = bool(d and d.get("first_date") and pencere_basi
                            and d["first_date"] < pencere_basi)

        # Stabilcoinler pozisyon değil NAKİTtir; cüzdan bakiyesinde takip
        # ediliyorlar. Pozisyon mutabakatında "USDT -3.789 eksik" demek gürültüdür.
        if varlik in STABLE_QUOTES:
            durum = "stablecoin"
            not_metni = ("Nakit birimi — pozisyon olarak takip edilmiyor. "
                         "Serbest nakit bakiyesi Cüzdan ekranından yönetilir.")
        elif b is None:
            if d and konumlar and not kapsanan_konum:
                durum = "uncovered_location"
                not_metni = (f"Bu varlık {', '.join(sorted(konumlar))} üzerinde tutuluyor "
                             "ve o konum için dışa aktarım dosyası yok. "
                             "Mutabakat yapılamaz — eksiklik değil, kapsam dışı.")
            else:
                durum = "only_ledger"
                not_metni = ("Bu varlık dışa aktarım dosyalarında hiç yok. "
                             "Dosyaların kapsamadığı bir tarihte alınmış veya "
                             "başka bir borsadan gelmiş olabilir.")
        elif negatif_kanit:
            durum = "coverage_gap"
            not_metni = (f"Borsa kayıtlarına göre bakiye eksiye düşüyor "
                         f"({b_kalan:,.4f}) — bu imkânsızdır. Alım işlemleri dosyanın "
                         f"başlangıcından ({pencere_basi}) önce yapılmış. "
                         "Karşılaştırma anlamsız, fark değil.")
        elif d is None or d_qty <= QTY_TOLERANCE_ABS:
            if b_kalan <= QTY_TOLERANCE_ABS:
                durum = "closed"
                not_metni = "Borsada girilip çıkılmış, defterde açık pozisyon yok."
            else:
                durum = "only_exchange"
                not_metni = "Borsa kayıtlarına göre bakiye var ama defterde yok."
        elif _yakin(b_kalan, d_qty):
            durum = "match"
            not_metni = ""
        elif tarih_kaniti:
            durum = "coverage_gap"
            not_metni = (f"Defterdeki en eski alım {d['first_date']}, dosya ise "
                         f"{pencere_basi} tarihinde başlıyor. Önceki işlemler dosyada "
                         "yok; fark bundan kaynaklanıyor olabilir.")
        elif b["withdrawn_qty"] > QTY_TOLERANCE_ABS:
            durum = "off_exchange"
            not_metni = (f"{b['withdrawn_qty']:,.8f} adet borsadan çekilmiş. "
                         "Defterdeki miktar cüzdan/başka borsa bakiyesini "
                         "yansıtıyor olabilir — bu bir tutarsızlık olmayabilir.")
        else:
            durum = "mismatch"
            not_metni = "Borsa kayıtları ile defter miktarı uyuşmuyor."

        satirlar.append({
            "asset": varlik,
            "exchanges": b["exchanges"] if b else [],
            "locations": d["locations"] if d else [],
            "bought_qty": b["bought_qty"] if b else 0.0,
            "sold_qty": b["sold_qty"] if b else 0.0,
            "deposited_qty": b["deposited_qty"] if b else 0.0,
            "withdrawn_qty": b["withdrawn_qty"] if b else 0.0,
            "on_exchange_qty": b_kalan,
            "acquired_qty": b["acquired_qty"] if b else 0.0,
            "ledger_qty": d_qty,
            "diff_qty": b_kalan - d_qty,
            "exchange_avg_cost": b["exchange_avg_cost"] if b else 0.0,
            "ledger_avg_cost": d["avg_cost"] if d else 0.0,
            "ledger_invested": d["invested"] if d else 0.0,
            "ledger_first_date": d.get("first_date") if d else None,
            "coverage_start": pencere_basi,
            "trade_count": b["trade_count"] if b else 0,
            "first_seen": b["first"] if b else None,
            "last_seen": b["last"] if b else None,
            "usd_unknown_trades": b["usd_unknown_trades"] if b else 0,
            "status": durum,
            "note": not_metni,
        })

    sira = {"mismatch": 0, "only_exchange": 1, "coverage_gap": 2, "off_exchange": 3,
            "only_ledger": 4, "uncovered_location": 5, "match": 6,
            "closed": 7, "stablecoin": 8}
    satirlar.sort(key=lambda r: (sira.get(r["status"], 9), r["asset"]))

    sayim = {}
    for r in satirlar:
        sayim[r["status"]] = sayim.get(r["status"], 0) + 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "export_root": root or export_root(),
        "files_found": len(kaynaklar),
        "sources": kaynaklar,
        "coverage": pencere,
        "event_count": len(olaylar),
        "rows": satirlar,
        "status_counts": sayim,
        "warnings": uyarilar[:50],
        # Bu rapor salt okunurdur; arayüz bunu kullanıcıya açıkça söyler.
        "read_only": True,
    }
