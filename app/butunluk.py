"""
CoinTakip — Defter Bütünlük Denetimi
=====================================================================

NEDEN VAR
---------
48 saat içinde birbirinden bağımsız ÜÇ sessiz doğruluk hatası bulundu ve
üçü de *başka bir şey yapılırken tesadüfen* ortaya çıktı:

  * Aynı numarayı taşıyan işlem kayıtları — dokuz gün görünmedi. Numaraya
    göre arama listede ilk eşleşeni bulup durduğu için, kullanıcı yeni bir
    lotu satmaya kalksa sistem kapanmış başka bir kaydı işleme alacaktı.
  * Alımda düşülmeyen nakit — toplam varlık `pozisyon + nakit` olarak
    hesaplandığı için aynı para iki kez sayılıyordu.
  * Aynı gelirin iki farklı maliyet tabanıyla deftere girmesi.

Ortak yanları: hiçbiri hata vermiyordu, hiçbiri ekranda kırmızı yanmıyordu.
Defter kendi kendini hiç denetlemiyordu. Bu modül o boşluğu kapatır.

Buradaki her denetim, bulunan gerçek bir hatanın GENELLEMESİDİR. Yeni bir
hata sınıfı bulunduğunda buraya bir madde eklenir; böylece aynı sınıftan bir
hata bir daha sessiz kalamaz.

**HİÇBİR ŞEY YAZMAZ.**
Bu modülün tek işi bakmak ve söylemek. Ne düzelttiği, ne düzelteceği vardır:
hangi kaydın değişeceği çoğu zaman ona kimin işaret ettiğine bağlıdır ve o
karar kullanıcınındır — 9 Eylül onarımında tam olarak böyle olmuştu. Otomatik
düzelten bir denetim, sessiz bir hatayı sessiz bir değişiklikle takas ederdi.
Bir test bu sözü ayrıca denetler.
"""

from datetime import datetime

from log_config import get_logger

logger = get_logger("butunluk")

HATA = "hata"
UYARI = "uyari"

# Bir bulguda kaç örnek gösterilir. Tamamını taşımak, 148 kayıtlık bir
# defterde raporu okunmaz hâle getirir; hiç göstermemek ise "nerede?"
# sorusunu cevapsız bırakır.
ORNEK_TAVANI = 20


def _bulgu(kod, seviye, baslik, aciklama, ogeler=None):
    ogeler = list(ogeler or [])
    return {
        "code": kod,
        "severity": seviye,
        "title": baslik,
        "detail": aciklama,
        "count": len(ogeler),
        "items": ogeler[:ORNEK_TAVANI],
        "truncated": len(ogeler) > ORNEK_TAVANI,
    }


def _f(deger, varsayilan=0.0):
    try:
        return float(deger)
    except (TypeError, ValueError):
        return varsayilan


def _no(tx):
    try:
        return int(tx.get("id", 0) or 0)
    except (TypeError, ValueError):
        return 0


# =====================================================================
# Denetimler — her biri (data, baglam) alır, bulgu listesi döndürür
# =====================================================================
def _tx_numaralari(data, ctx):
    """Numaralar benzersiz ve sayaç ileride olmalı.

    9 Eylül 2026: `next_tx_id` 74'te donmuşken defterde 145'e kadar numara
    vardı ve her yeni kayıt var olan bir numarayı alıyordu.
    """
    import collections

    out = []
    sayac = collections.Counter(_no(t) for t in data.get("transactions", []))
    cakisan = sorted(no for no, adet in sayac.items() if adet > 1)
    if cakisan:
        out.append(_bulgu(
            "tx_id_cakismasi", HATA,
            "Aynı numarayı taşıyan işlem kayıtları var",
            "Numaraya göre arama listede İLK eşleşeni bulup durur; satış, "
            "düzenleme ve durum değiştirme yanlış kaydı işleme alabilir.",
            [f"numara {no} — {sayac[no]} kayıt" for no in cakisan]))

    numarasiz = [t for t in data.get("transactions", []) if _no(t) <= 0]
    if numarasiz:
        out.append(_bulgu(
            "tx_id_yok", HATA, "Numarası olmayan işlem kayıtları var",
            "Numarasız bir kayıt hiçbir uçtan bulunamaz; düzenlenemez ve "
            "satılamaz.",
            [f"{t.get('date')} {t.get('coin')}" for t in numarasiz]))

    if sayac:
        gereken = max(sayac) + 1
        mevcut = int(_f(data.get("next_tx_id"), 0))
        if mevcut < gereken:
            out.append(_bulgu(
                "tx_id_sayaci_geride", HATA,
                "İşlem numarası sayacı defterin gerisinde",
                "Bir sonraki kayıt var olan bir numarayı alır ve çakışma "
                "üretir. Çakışmanın kendisi henüz oluşmamış olabilir.",
                [f"next_tx_id={mevcut}, en büyük numara={max(sayac)}, "
                 f"olması gereken={gereken}"]))
    return out


def _nakit(data, ctx):
    """`usdt_cash`, konum nakitlerinin toplamına eşit olmalı ve hiçbiri
    negatif olmamalı.

    Toplam varlık `pozisyon değeri + nakit` olarak hesaplanıyor; nakit
    yanlışsa ekrandaki toplam da yanlıştır.
    """
    out = []
    cuzdan = data.get("wallets") or {}
    kasalar = cuzdan.get("exchange_cash") or {}

    negatif = [f"{k}: {_f(v):,.8f}" for k, v in kasalar.items() if _f(v) < -1e-9]
    if negatif:
        out.append(_bulgu(
            "negatif_nakit", HATA, "Negatif nakit bakiyesi",
            "Bir konumda eksi nakit fiziksel olarak imkânsızdır.", negatif))

    toplam = sum(_f(v) for v in kasalar.values())
    beyan = _f(cuzdan.get("usdt_cash"))
    if abs(toplam - beyan) > 0.01:
        out.append(_bulgu(
            "nakit_toplami_tutmuyor", HATA,
            "Toplam nakit, konum nakitlerinin toplamıyla uyuşmuyor",
            "İkisi farklıysa hangisinin doğru olduğu bilinemez ve toplam "
            "varlık ikisinden birine göre yanlış hesaplanır.",
            [f"usdt_cash={beyan:,.8f}, konumların toplamı={toplam:,.8f}, "
             f"fark={beyan - toplam:+,.8f}"]))
    return out


def _pozisyon_alanlari(data, ctx):
    """Her kaydın anlamlı olması için gereken en az bilgi."""
    out, eksik, negatif, bilinmeyen = [], [], [], []
    durumlar = {"Aktif", "Kapandı / İzleme"}

    for t in data.get("transactions", []):
        etiket = f"#{_no(t)} {t.get('date')} {t.get('coin')}"
        for alan in ("coin", "exchange", "date"):
            if not str(t.get(alan) or "").strip():
                eksik.append(f"{etiket} — '{alan}' boş")
        durum = str(t.get("status") or "")
        if durum not in durumlar:
            bilinmeyen.append(f"{etiket} — durum: {durum!r}")
        if durum == "Aktif" and _f(t.get("qty")) < -1e-12:
            negatif.append(f"{etiket} — miktar {_f(t.get('qty')):,.8f}")

    if eksik:
        out.append(_bulgu("eksik_alan", HATA, "Zorunlu alanı boş kayıtlar",
                          "Bu kayıtlar raporlarda ve hesaplamalarda "
                          "öngörülemeyen davranışa yol açar.", eksik))
    if negatif:
        out.append(_bulgu("negatif_miktar", HATA, "Negatif miktarlı açık lot",
                          "Elde eksi coin bulunamaz; FIFO ve maliyet "
                          "hesapları bozulur.", negatif))
    if bilinmeyen:
        out.append(_bulgu("bilinmeyen_durum", UYARI, "Tanınmayan durum değeri",
                          "Bu kayıtlar ne açık ne kapalı sayılır; bazı "
                          "ekranlarda hiç görünmezler.", bilinmeyen))
    return out


def _kapali_lotlar(data, ctx):
    """Kapanmış bir lot, nasıl kapandığını söylemelidir."""
    out = []
    eksik = []
    for t in data.get("transactions", []):
        if str(t.get("status") or "") != "Kapandı / İzleme":
            continue
        if not str(t.get("exit_date") or "").strip():
            eksik.append(f"#{_no(t)} {t.get('date')} {t.get('coin')} — "
                         "çıkış tarihi yok")
    if eksik:
        out.append(_bulgu(
            "kapali_lot_eksik", UYARI, "Çıkış bilgisi eksik kapalı lotlar",
            "Vergi dökümü ve gerçekleşmiş K/Z bu alanlardan besleniyor; "
            "eksik kayıtlar dökümde tarihsiz görünür.", eksik))
    return out


def _defter_baglari(data, ctx):
    """Transfer ve mutabakat kayıtları var olan işlemlere işaret etmeli.

    9 Eylül onarımında bu bağların haritası çıkarılmasaydı, numara
    değiştirmek sessizce bir bağı koparacaktı.
    """
    out = []
    numaralar = {_no(t) for t in data.get("transactions", [])}
    kopuk = []

    for tr in (data.get("transfers") or []):
        for tuketilen in (tr.get("consumed") or []):
            no = int(_f(tuketilen.get("tx_id"), 0))
            if no and no not in numaralar:
                kopuk.append(f"transfer #{tr.get('id')} → olmayan işlem #{no}")

    for rb in (data.get("rebuilds") or []):
        for alan in ("closed_tx_ids", "created_tx_ids"):
            for no in (rb.get(alan) or []):
                if int(_f(no, 0)) not in numaralar:
                    kopuk.append(f"mutabakat #{rb.get('id')} {alan} → "
                                 f"olmayan işlem #{no}")
        kz = (rb.get("realized") or {}).get("tx_id")
        if kz and int(_f(kz, 0)) not in numaralar:
            kopuk.append(f"mutabakat #{rb.get('id')} K/Z kaydı → "
                         f"olmayan işlem #{kz}")

    if kopuk:
        out.append(_bulgu(
            "kopuk_bag", HATA, "Var olmayan işleme işaret eden bağlar",
            "Geri alma bu bağları kullanır; kopuk bir bağ, geri almanın "
            "sessizce eksik çalışması demektir.", kopuk))
    return out


def _arsiv_baglari(data, ctx):
    """Uygulanmış her borsa olayı gerçek bir işleme bakmalı.

    9 Eylül'de ARB alımının numarası değişirken bu bağ da güncellenmişti;
    güncellenmeseydi olay kapanmış bir transfer kaydını gösterecekti.
    """
    out = []
    numaralar = {_no(t) for t in data.get("transactions", [])}
    try:
        import archive
        satirlar = archive.applied_events_with_tx()
    except Exception as e:
        logger.debug("Arşiv bağları okunamadı: %s", e)
        return [_bulgu("arsiv_okunamadi", UYARI, "Arşiv denetlenemedi",
                       f"Arşiv okunamadığı için borsa olaylarının defter "
                       f"bağları kontrol edilemedi: {e}")]

    kopuk = [f"{r['kind']} {r['symbol']} ({r['event_uid']}) → olmayan işlem "
             f"#{r['applied_tx_id']}"
             for r in satirlar
             if int(_f(r.get("applied_tx_id"), 0)) not in numaralar]
    if kopuk:
        out.append(_bulgu(
            "arsiv_bagi_kopuk", HATA,
            "İşlenmiş borsa olayı var olmayan bir kayda bakıyor",
            "Olay 'işlendi' görünür ama defterde karşılığı yoktur; aynı "
            "işlem bir daha yakalanmaz ve eksik kalır.", kopuk))
    return out


DENETIMLER = (
    _tx_numaralari,
    _nakit,
    _pozisyon_alanlari,
    _kapali_lotlar,
    _defter_baglari,
    _arsiv_baglari,
)


def denetle(data=None):
    """Defterin bütün değişmezlerini denetler. **Hiçbir şey yazmaz.**"""
    if data is None:
        from data_manager import load_portfolio
        data = load_portfolio()

    ctx = {}
    bulgular = []
    for denetim in DENETIMLER:
        try:
            bulgular.extend(denetim(data, ctx) or [])
        except Exception as e:
            # Bir denetimin düşmesi diğerlerini iptal etmemeli; sessizce
            # atlanması ise "denetlendi ve temiz" izlenimi verirdi.
            logger.warning("Bütünlük denetimi düştü (%s): %s",
                           getattr(denetim, "__name__", "?"), e)
            bulgular.append(_bulgu(
                "denetim_dustu", UYARI, "Bir denetim çalıştırılamadı",
                f"{getattr(denetim, '__name__', '?')}: {e}"))

    hatalar = [b for b in bulgular if b["severity"] == HATA]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ok": not hatalar,
        "error_count": len(hatalar),
        "warning_count": len(bulgular) - len(hatalar),
        "checks_run": len(DENETIMLER),
        "transaction_count": len(data.get("transactions", [])),
        "findings": bulgular,
        # Bu modülün sözü: bakar ve söyler, düzeltmez.
        "read_only": True,
    }
