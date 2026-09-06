"""
CoinTakip — BORSA İŞLEMİ YAKALAMA (FAZ F7)

═══════════════════════════════════════════════════════════════════════════
NEDEN VAR
═══════════════════════════════════════════════════════════════════════════
Kullanıcı Binance'te bir satış yaptığında uygulama bunu GÖRMÜYORDU.
`exchanges.py` yalnızca bakiyeyi okuyordu; işlem geçmişine hiç bakılmıyordu.
Tek yol ya "Sat" düğmesine elle basmak ya da ay sonunda CSV dışa aktarıp
mutabakata vermekti.

Bu modül o boşluğu kapatır: borsanın kendi işlem kaydını okur, yeni olanları
bulur ve kullanıcının önüne ONAY BEKLEYEN bir liste olarak koyar.

═══════════════════════════════════════════════════════════════════════════
TASARIM KURALLARI
═══════════════════════════════════════════════════════════════════════════

1) DEFTERE ASLA KENDİLİĞİNDEN YAZILMAZ.
   Bulunan her işlem `pending` durumunda bekler; deftere ancak kullanıcı
   "İşle" dediğinde girer. Üç sebep:
     - Kısmi satışta maliyet yöntemi (Konsolide Ortalama / FIFO) sonucu
       DEĞİŞTİREN bir karardır ve karar kullanıcınındır.
     - Aynı satış elle de işlenmiş olabilir; sessiz bir otomatik yazma çift
       kayıt üretir.
     - Projenin mevcut çizgisi budur: airdrop/spam tokenlar da portföye
       kendiliğinden girmez.

2) TOZ DÖNÜŞÜMÜ AYRI BİR OLAYDIR VE `myTrades`E DÜŞMEZ.
   Binance'in "Küçük Bakiyeleri Dönüştür" özelliği spot işlem değildir;
   yalnızca `/sapi/v1/asset/dribblet` ucunda görünür. Bunu okumayan bir
   sistem, kullanıcı dönüştürme yaptığında varlıkların bakiyeden silindiğini
   görür ama sebebini asla söyleyemez.

   Etkisi tutarın küçüklüğüyle ölçülmez. Kullanıcının gerçek verisinde
   ölçüldü (6 Eylül 2026): 17.76 USDT'lik bir dönüşüm, defterde 434.54 USD
   maliyet tabanını silecekti — yani ~418 USD'lik gerçekleşmiş bir zarar,
   hiçbir yere yazılmadan. "Küçük bakiye" piyasa değeri için küçüktür,
   maliyet tabanı için değil.

3) AÇIKLAYAMADIĞIMIZ DEĞİŞİMİ SAKLAMAYIZ.
   Her taramada bakiye fotoğrafı alınır. Bir varlığın miktarı değişmiş ama
   bunu açıklayan bir işlem bulunamamışsa kullanıcıya SUSULMAZ; "şu varlık
   şu kadar değişti, sebebini göremiyorum" denir. Para yatırma/çekme, Earn
   ve vadeli transferleri bu sürümün kapsamı dışında — kapsam dışı olmak,
   görünmez olmak demek değildir.

4) İLK TARAMA YALNIZCA BAŞLANGIÇ NOKTASI KURAR.
   Bir sembol ilk kez tarandığında hiçbir işlem "bekliyor" listesine
   düşmez; sadece imleç kurulur. Aksi hâlde aylarca öncesine ait, çoğu
   zaten deftere elle işlenmiş yüzlerce işlem gelen kutusuna dolardı.
   Sınır açıktır ve arayüzde yazar: **bu sürüm "bundan sonrasını yakalar".**

5) SALT OKUMA. Bu modülün ağa çıkan tek yolu `exchanges.signed_get`'tir ve
   o yalnızca GET yapar. Emir verme veya para çekme çağrısı yoktur.

═══════════════════════════════════════════════════════════════════════════
MALİYET
═══════════════════════════════════════════════════════════════════════════
Binance `myTrades` ağırlığı 20, `dribblet` 1; IP bütçesi dakikada 6000.
Kullanıcının defterinde 21 açık Binance sembolü var → tam tarama 420 ağırlık,
bütçenin %7'si. Yine de her turda hepsini yoklamıyoruz: bakiyesi değişmemiş
bir sembolde yeni işlem olamaz, o yüzden normal turda yalnızca DEĞİŞEN
varlıklar yoklanır. Tam tarama kullanıcı "Şimdi tara" dediğinde yapılır.
"""

import threading
import time
from datetime import datetime

from log_config import get_logger

logger = get_logger("trade_sync")

# Arka plan turu. Fiyat motorundan çok daha seyrek: işlem yakalamak acil
# değildir ve borsanın imza doğrulaması ucuz bir çağrı değildir.
DONGU_ARALIGI = 300.0          # 5 dakika
ILK_TARAMA_GECIKMESI = 25.0    # açılışı ve ilk fiyat turunu bloke etme

# Bir taramada bir sembol için en fazla kaç sayfa çekilir. 1000'lik sayfa
# ile 5 sayfa = 5000 işlem; bunun ötesi tek turda halledilmesi gereken bir
# durum değildir ve sonraki tur kaldığı yerden devam eder.
SAYFA_TAVANI = 5

# Aynı anda kaç borsa taranır.
PARALEL_ISCI = 2

# Toz dönüşümü akışının imleç adı (sembol değil, hesap düzeyinde bir akış).
TOZ_KAPSAMI = "__dust__"

# Bakiye farkı eşleştirme toleransı. Borsa miktarları ondalık basamak
# yuvarlamasıyla geliyor; birebir eşitlik aramak her turda sahte "açıklanamayan
# değişim" üretirdi.
FARK_TOLERANS_ORAN = 0.01      # %1
FARK_TOLERANS_MUTLAK = 1e-8

# Bu varlıklar bir "coin pozisyonu" değil nakittir; onlar için sembol
# yoklanmaz (USDTUSDT diye bir çift yok).
NAKIT_VARLIKLAR = {"USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI", "USD"}

# Borsanın "böyle bir sembol yok" cevabı. Bu hata tekrar tekrar denenmemeli:
# defterdeki eski bir coin artık listelenmiyor olabilir ve her turda 20
# ağırlık harcamanın anlamı yok.
GECERSIZ_SEMBOL_IZLERI = ("-1121", "invalid symbol", "invalid_symbol")

TRADE = "TRADE"
DUST = "DUST"
UNEXPLAINED = "UNEXPLAINED"


# =====================================================================
# SAF DÖNÜŞTÜRÜCÜLER — hiçbiri ağa çıkmaz, hepsi tek başına test edilebilir
# =====================================================================
def _f(deger, varsayilan=0.0):
    try:
        return float(deger)
    except (TypeError, ValueError):
        return varsayilan


def _iso(ms):
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def gecersiz_sembol_hatasi_mi(mesaj) -> bool:
    m = str(mesaj or "").lower()
    return any(iz in m for iz in GECERSIZ_SEMBOL_IZLERI)


def normalize_trade(exchange, ham):
    """Binance ailesinin `myTrades` satırını olay sözlüğüne çevirir.

    Komisyon işlemin KENDİ varlığından alındıysa eline geçen miktar o kadar
    azalır — `reconcile.load_binance_trades` CSV tarafında aynı düzeltmeyi
    yapıyor ve iki yolun aynı sonucu vermesi şart, aksi hâlde aynı işlem
    dosyadan mı API'den mi geldiğine göre farklı bakiye üretirdi.
    """
    import reconcile

    borsa = str(exchange or "").upper().strip()
    sembol = str(ham.get("symbol") or "").upper().strip()
    islem_no = ham.get("id")
    if islem_no is None or not sembol:
        raise ValueError("işlem satırında sembol veya numara yok")

    taban, kot = reconcile.split_pair(sembol)
    alis = bool(ham.get("isBuyer"))
    miktar = _f(ham.get("qty"))
    fiyat = _f(ham.get("price"))
    tutar = _f(ham.get("quoteQty")) or (miktar * fiyat)
    komisyon = _f(ham.get("commission"))
    kom_varlik = str(ham.get("commissionAsset") or "").upper().strip()
    zaman_ms = ham.get("time") or ham.get("transactTime") or 0

    net = miktar
    if alis and kom_varlik and kom_varlik == taban:
        net = max(0.0, miktar - komisyon)

    return {
        "event_uid": f"{borsa}:trade:{sembol}:{islem_no}",
        "exchange": borsa,
        "kind": TRADE,
        "symbol": sembol,
        "base_asset": taban,
        "quote_asset": kot,
        "side": "BUY" if alis else "SELL",
        "qty": net,
        "price": fiyat,
        "quote_qty": tutar,
        "fee_asset": kom_varlik,
        "fee_qty": komisyon,
        "trade_at": _iso(zaman_ms),
        "trade_ts": _f(zaman_ms) / 1000.0,
        "raw_json": _json_dump({**ham, "gross_qty": miktar}),
        "_trade_id": int(islem_no),
    }


def normalize_dust(exchange, satir):
    """Toz dönüşümü satırını olay sözlüğüne çevirir.

    Bu bir SATIŞTIR: `from_asset` gidiyor, `target_asset` geliyor. Fiyatı
    hedef varlık cinsindendir — hedef USDT ise doğrudan dolar, BNB ise
    BNB'dir ve dolara çevrilmesi ayrı bir adımdır (bkz. `_dolar_fiyati`).
    """
    borsa = str(exchange or "").upper().strip()
    kaynak = str(satir.get("from_asset") or "").upper().strip()
    hedef = str(satir.get("target_asset") or "").upper().strip() or "BNB"
    miktar = _f(satir.get("amount"))
    gelen = _f(satir.get("transfered_amount"))
    komisyon = _f(satir.get("service_charge_amount"))
    zaman_ms = satir.get("operate_time") or 0
    islem_no = satir.get("trans_id") or f"{satir.get('batch_id')}-{kaynak}"
    if not kaynak or miktar <= 0:
        raise ValueError("toz satırında kaynak varlık veya miktar yok")

    return {
        "event_uid": f"{borsa}:dust:{islem_no}",
        "exchange": borsa,
        "kind": DUST,
        "symbol": f"{kaynak}{hedef}",
        "base_asset": kaynak,
        "quote_asset": hedef,
        "side": "SELL",
        "qty": miktar,
        # Efektif birim fiyat: eline geçen / verdiğin. Komisyon `gelen`den
        # ayrı bildirildiği için fiyat komisyon ÖNCESİDİR ve komisyon ayrı
        # alanda taşınır — satışın matematiği ikisini ayrı ister.
        "price": (gelen / miktar) if miktar > 0 else 0.0,
        "quote_qty": gelen,
        "fee_asset": hedef,
        "fee_qty": komisyon,
        "trade_at": _iso(zaman_ms),
        "trade_ts": _f(zaman_ms) / 1000.0,
        "raw_json": _json_dump(satir),
        "_operate_time": int(_f(zaman_ms)),
    }


def _json_dump(nesne):
    import json
    try:
        return json.dumps(nesne, ensure_ascii=False, default=str)
    except Exception:
        return "{}"


def olay_bakiye_etkisi(olay):
    """Bir olayın hangi varlığı ne kadar değiştirdiği. Bakiye farkını
    açıklayabilmek için gerekli tek bilgi budur."""
    etki = {}
    taban = str(olay.get("base_asset") or "")
    kot = str(olay.get("quote_asset") or "")
    miktar = _f(olay.get("qty"))
    tutar = _f(olay.get("quote_qty"))
    komisyon = _f(olay.get("fee_qty"))
    kom_varlik = str(olay.get("fee_asset") or "")

    isaret = 1.0 if olay.get("side") == "BUY" else -1.0
    if taban:
        etki[taban] = etki.get(taban, 0.0) + isaret * miktar
    if kot:
        etki[kot] = etki.get(kot, 0.0) - isaret * tutar

    # Komisyon HER ZAMAN kendi varlığından düşülür — tek istisna, alımda
    # komisyonun işlem varlığından kesilmesi: `normalize_trade` orada eline
    # geçen miktarı zaten net yazdı, ikinci kez düşmek çift sayım olurdu.
    zaten_dusuldu = (olay.get("side") == "BUY"
                     and olay.get("kind") == TRADE
                     and kom_varlik == taban)
    if komisyon > 0 and kom_varlik and not zaten_dusuldu:
        etki[kom_varlik] = etki.get(kom_varlik, 0.0) - komisyon
    return etki


def bakiye_farki(onceki, simdiki):
    """{varlık: değişim}. Sıfıra yakın farklar elenir."""
    varliklar = set(onceki or {}) | set(simdiki or {})
    out = {}
    for v in varliklar:
        eski = _f((onceki or {}).get(v))
        yeni = _f((simdiki or {}).get(v))
        fark = yeni - eski
        if abs(fark) > FARK_TOLERANS_MUTLAK:
            out[v] = fark
    return out


def aciklanamayan_degisimler(farklar, olaylar):
    """Olaylarla açıklanamayan bakiye değişimleri.

    "Açıklanamayan" burada suçlama değil dürüstlüktür: para yatırma/çekme,
    Earn abonelikleri ve vadeli transferleri bu sürümün kapsamı dışında.
    Kapsam dışı olan şeyin görünmez olması, sessiz başarısızlıktır.
    """
    aciklanan = {}
    for o in olaylar or []:
        for varlik, delta in olay_bakiye_etkisi(o).items():
            aciklanan[varlik] = aciklanan.get(varlik, 0.0) + delta

    out = []
    for varlik, fark in sorted((farklar or {}).items()):
        beklenen = aciklanan.get(varlik, 0.0)
        kalan = fark - beklenen
        tolerans = max(FARK_TOLERANS_MUTLAK,
                       abs(fark) * FARK_TOLERANS_ORAN,
                       abs(beklenen) * FARK_TOLERANS_ORAN)
        if abs(kalan) > tolerans:
            out.append({
                "asset": varlik,
                "delta": round(fark, 10),
                "explained": round(beklenen, 10),
                "unexplained": round(kalan, 10),
            })
    return out


def aday_semboller(location, defter, bakiyeler, degisen_varliklar=None):
    """Hangi sembollerin yoklanacağı.

    Birleşim bilinçli:
      * **Defterdeki açık pozisyonlar** — bir satış pozisyonu kapatsa bile
        defterde durur, yani satışı yakalamanın tek yolu buradan geçer.
      * **Borsadaki bakiye** — defterde hiç olmayan YENİ bir alım ancak
        burada görünür.

    İkisi birlikte pratikte tam kapsar. Kapsamayan tek durum dürüstçe
    söylenmeli: iki tarama arasında alınıp tamamen satılan bir coin hiçbir
    kaynakta iz bırakmaz.

    `degisen_varliklar` verilirse liste ona daraltılır — bakiyesi hiç
    değişmemiş bir sembolde yeni işlem olamaz.
    """
    from data_manager import normalize_location, symbol_for_location

    konum = normalize_location(str(location or ""))
    semboller = set()

    for tx in (defter or {}).get("transactions", []):
        if str(tx.get("status") or "") != "Aktif":
            continue
        if normalize_location(str(tx.get("exchange") or "")) != konum:
            continue
        sembol = symbol_for_location(str(tx.get("coin") or ""), konum)
        if sembol:
            semboller.add(sembol.upper())

    for b in (bakiyeler or []):
        varlik = str(b.get("asset") or "").upper().strip()
        if not varlik or varlik in NAKIT_VARLIKLAR:
            continue
        semboller.add(symbol_for_location(varlik, konum).upper())

    semboller = {s for s in semboller if s and s not in NAKIT_VARLIKLAR}

    if degisen_varliklar is not None:
        hedef = {str(v).upper() for v in degisen_varliklar}
        semboller = {s for s in semboller
                     if any(s.startswith(v) or s == v for v in hedef)}
    return sorted(semboller)


# =====================================================================
# SERVİS
# =====================================================================
class TradeSyncService:
    """Borsa işlemlerini arka planda yakalar; deftere yazmaz, önerir."""

    def __init__(self):
        self.lock = threading.Lock()
        self.is_running = False
        self._son_rapor = {}
        self._tarama_kilidi = threading.Lock()

    # -----------------------------------------------------------------
    # Yaşam döngüsü
    # -----------------------------------------------------------------
    def start_background_updater(self):
        if self.is_running:
            return
        self.is_running = True
        t = threading.Thread(target=self._background_loop, daemon=True)
        t.start()
        logger.info("Borsa işlem yakalama aktif (ilk tarama %.0f sn sonra).",
                    ILK_TARAMA_GECIKMESI)

    def stop(self):
        self.is_running = False

    def _background_loop(self):
        time.sleep(ILK_TARAMA_GECIKMESI)
        while self.is_running:
            try:
                self.scan()
            except Exception as e:
                logger.warning("Borsa işlem taramasında hata: %s", e)
            time.sleep(DONGU_ARALIGI)

    # -----------------------------------------------------------------
    # Tarama
    # -----------------------------------------------------------------
    def scan(self, location=None, full=False):
        """Tanımlı borsaları tarar ve yeni işlemleri kaydeder.

        `full=True` bakiyesi değişmemiş sembolleri de yoklar; kullanıcı
        "Şimdi tara" dediğinde bu kullanılır.

        Kasa kilitliyken SESSİZCE atlanır ve bu bir hata değildir: anahtarlar
        şifreli kasada duruyor ve kasa her açılışta elle açılıyor. Her turda
        hata üretmek, gerçek hataları görünmez yapan gürültü olurdu.
        """
        import archive
        import exchanges
        import keyvault

        # İki tarama üst üste binmesin: arka plan turu ile kullanıcının
        # "Şimdi tara" düğmesi aynı anda çalışırsa aynı işlemler iki kez
        # çekilir ve imleçler yarışır.
        if not self._tarama_kilidi.acquire(blocking=False):
            return {"ok": False, "skipped": "already_running",
                    "message": "Bir tarama zaten sürüyor."}
        try:
            profiller = {k: v for k, v in exchanges.list_profiles().items()
                         if v.get("enabled", True)}
            if location:
                from data_manager import normalize_location
                hedef = normalize_location(str(location))
                profiller = {k: v for k, v in profiller.items() if k == hedef}

            if not profiller:
                return self._rapor_kaydet({
                    "ok": False, "skipped": "no_profile",
                    "message": "Tanımlı ve açık bir borsa profili yok."})

            if not keyvault.is_unlocked():
                return self._rapor_kaydet({
                    "ok": False, "skipped": "vault_locked",
                    "message": ("Anahtar kasası kilitli. Borsa işlemleri "
                                "okunamaz; Anahtar Kasası → PIN → Kasayı Aç.")})

            borsalar = []
            for konum, profil in profiller.items():
                if not exchanges.credentials_stored(konum):
                    continue
                try:
                    borsalar.append(self._borsayi_tara(konum, profil, full=full))
                except Exception as e:
                    logger.warning("Borsa taranamadı (%s): %s", konum, e)
                    borsalar.append({"exchange": konum, "ok": False,
                                     "error": str(e)[:300], "new_events": 0})

            if not borsalar:
                return self._rapor_kaydet({
                    "ok": False, "skipped": "no_credentials",
                    "message": ("Tanımlı borsa profillerinin hiçbirinde API "
                                "anahtarı yok.")})

            return self._rapor_kaydet({
                "ok": any(b.get("ok") for b in borsalar),
                "exchanges": borsalar,
                "new_events": sum(int(b.get("new_events") or 0) for b in borsalar),
                "pending_total": archive.exchange_event_counts().get(
                    archive.EVENT_PENDING, 0),
                "scanned_at": datetime.now().isoformat(timespec="seconds"),
            })
        finally:
            self._tarama_kilidi.release()

    def _rapor_kaydet(self, rapor):
        rapor.setdefault("scanned_at", datetime.now().isoformat(timespec="seconds"))
        with self.lock:
            self._son_rapor = dict(rapor)
        return rapor

    def last_report(self):
        with self.lock:
            return dict(self._son_rapor)

    def _borsayi_tara(self, konum, profil, full=False):
        import archive
        import exchanges

        okuma = exchanges.read_exchange(konum, profil)
        if not okuma.get("ok"):
            notlar = okuma.get("notes") or []
            mesaj = notlar[0].get("message") if notlar else "Bakiye okunamadı."
            archive.set_sync_cursor(konum, "__account__", error=mesaj)
            return {"exchange": konum, "ok": False, "error": mesaj,
                    "new_events": 0}

        bakiyeler = okuma.get("balances") or []
        simdiki = {str(b["asset"]).upper(): _f(b.get("qty")) for b in bakiyeler}
        onceki = archive.get_balance_state(konum)
        ilk_bakiye_taramasi = not onceki
        farklar = bakiye_farki(onceki, simdiki)

        defter = self._defter()
        degisen = None if (full or ilk_bakiye_taramasi) else set(farklar)
        semboller = aday_semboller(konum, defter, bakiyeler, degisen)
        semboller = [s for s in semboller if not self._sembol_atlanir_mi(konum, s)]

        olaylar, hatalar, temel_kurulan = [], [], []
        for sembol in semboller:
            try:
                yeni, temel = self._sembolu_cek(konum, profil, sembol)
                olaylar.extend(yeni)
                if temel:
                    temel_kurulan.append(sembol)
            except Exception as e:
                hatalar.append({"scope": sembol, "error": str(e)[:200]})
                archive.set_sync_cursor(konum, sembol, error=e)
                logger.debug("Sembol taranamadı (%s/%s): %s", konum, sembol, e)

        toz_sonuc = self._tozu_cek(konum, profil)
        olaylar.extend(toz_sonuc["events"])
        if toz_sonuc.get("error"):
            hatalar.append({"scope": TOZ_KAPSAMI, "error": toz_sonuc["error"]})
        if toz_sonuc.get("baseline"):
            temel_kurulan.append(TOZ_KAPSAMI)

        # Açıklanamayan değişimler yalnızca ELDE ÖNCEKİ FOTOĞRAF VARSA
        # anlamlıdır. İlk taramada her varlık "değişmiş" görünür ve hepsini
        # anomali diye listelemek, uyarıyı ilk günden değersizleştirirdi.
        #
        # Bir çekim HATA verdiyse de anomali üretilmez: o durumda
        # "açıklanamayan değişim" ile "bakamadım" birbirinden ayrılamaz ve
        # ikincisini birincisi gibi sunmak yanlış bir iddia olurdu.
        anomaliler = []
        anomali_atlandi = bool(hatalar) and not ilk_bakiye_taramasi
        if not ilk_bakiye_taramasi and not hatalar:
            anomaliler = aciklanamayan_degisimler(farklar, olaylar)

        yeni_sayisi = archive.record_exchange_events(olaylar)
        if anomaliler:
            archive.record_exchange_events(
                [self._anomali_olayi(konum, a) for a in anomaliler])

        # Bakiye fotoğrafı BİR SİNYALDİR: bir varlığın miktarı değiştiği için
        # o sembolü yokluyoruz. Fotoğrafı tazelemek o sinyali tüketir — yani
        # başarısız bir çekimden sonra tazelersek, bakamadığımız değişim bir
        # daha hiç fark edilmez. Bu yüzden hata varsa ya da olaylar arşive
        # yazılamadıysa ilgili varlıklar ESKİ hâlinde bırakılır.
        archive.set_balance_state(
            konum, self._yazilacak_bakiye(onceki, simdiki, hatalar,
                                          yeni_sayisi is None))

        return {
            "exchange": konum,
            "ok": True,
            "symbols_polled": len(semboller),
            "symbols": semboller,
            "found_events": len(olaylar),
            "new_events": 0 if yeni_sayisi is None else yeni_sayisi,
            "archive_write_failed": yeni_sayisi is None,
            "baseline_established": temel_kurulan,
            "unexplained": anomaliler,
            "unexplained_skipped": anomali_atlandi,
            "errors": hatalar,
            "dust_supported": exchanges.supports(profil, "dust_log_path"),
            "first_balance_scan": ilk_bakiye_taramasi,
        }

    @staticmethod
    def _yazilacak_bakiye(onceki, simdiki, hatalar, arsiv_yazamadi):
        """Fotoğrafın hangi kısmının tazeleneceği.

        Arşive hiç yazamadıysak fotoğrafı hiç tazelemeyiz: yoksa hem olaylar
        kaybolur hem de onları bir daha aramamıza yol açacak sinyal silinir.

        Tek tek sembol hatalarında yalnızca O varlık eski değerinde bırakılır;
        çalışan sembollerin sinyali boşuna tekrarlanmaz.
        """
        if arsiv_yazamadi:
            return dict(onceki)

        yazilacak = dict(simdiki)
        for h in (hatalar or []):
            kapsam = str(h.get("scope") or "")
            if kapsam == TOZ_KAPSAMI:
                # Toz akışı hangi varlığı etkilediğini bilmiyoruz; fotoğrafın
                # tamamı eski hâlinde bırakılır.
                return dict(onceki)
            for varlik in (onceki.keys() | simdiki.keys()):
                # Kesin eşleşme: "ARBUSDT" yalnızca ARB'yi dondurur. Ön ek
                # kontrolü ilgisiz bir varlığı da dondurabilirdi.
                if kapsam != varlik and kapsam not in (f"{varlik}{k}" for k in
                                                       NAKIT_VARLIKLAR):
                    continue
                if varlik in onceki:
                    yazilacak[varlik] = onceki[varlik]
                else:
                    yazilacak.pop(varlik, None)
        return yazilacak

    def _defter(self):
        from data_manager import load_portfolio
        try:
            return load_portfolio()
        except Exception as e:
            logger.debug("Defter okunamadı: %s", e)
            return {"transactions": []}

    def _sembol_atlanir_mi(self, konum, sembol):
        """Borsanın "böyle bir sembol yok" dediği çiftler tekrar yoklanmaz."""
        import archive
        durum = archive.get_sync_cursor(konum, sembol) or {}
        if durum.get("cursor"):
            return False          # bir kez çalışmış, hata geçiciydi
        return gecersiz_sembol_hatasi_mi(durum.get("last_error"))

    def _sembolu_cek(self, konum, profil, sembol):
        """(olaylar, temel_kuruldu_mu). İmleci ilerletir."""
        import archive
        import exchanges

        durum = archive.get_sync_cursor(konum, sembol) or {}
        ham_imlec = durum.get("cursor")
        temel_kurulmadi = ham_imlec is None

        olaylar = []
        en_buyuk = int(_f(ham_imlec, 0.0)) if ham_imlec is not None else 0
        from_id = None if temel_kurulmadi else en_buyuk + 1

        for _ in range(SAYFA_TAVANI):
            satirlar = exchanges.fetch_my_trades(profil, sembol, from_id=from_id)
            if not satirlar:
                break
            for ham in satirlar:
                try:
                    olay = normalize_trade(konum, ham)
                except Exception as e:
                    logger.debug("İşlem satırı okunamadı (%s): %s", sembol, e)
                    continue
                en_buyuk = max(en_buyuk, olay["_trade_id"])
                if not temel_kurulmadi:
                    olaylar.append(olay)
            if len(satirlar) < exchanges.MY_TRADES_LIMIT:
                break
            from_id = en_buyuk + 1

        archive.set_sync_cursor(konum, sembol, cursor=en_buyuk)
        return olaylar, temel_kurulmadi

    def _tozu_cek(self, konum, profil):
        """Toz dönüşümü akışı. Desteklenmiyorsa sessizce boş döner."""
        import archive
        import exchanges

        if not exchanges.supports(profil, "dust_log_path"):
            return {"events": [], "supported": False}

        durum = archive.get_sync_cursor(konum, TOZ_KAPSAMI) or {}
        ham_imlec = durum.get("cursor")
        temel_kurulmadi = ham_imlec is None
        son_zaman = int(_f(ham_imlec, 0.0)) if ham_imlec is not None else 0

        try:
            satirlar = exchanges.fetch_dust_log(
                profil, start_time_ms=(son_zaman + 1) if son_zaman else None)
        except Exception as e:
            archive.set_sync_cursor(konum, TOZ_KAPSAMI, error=e)
            logger.debug("Toz dönüşümü okunamadı (%s): %s", konum, e)
            return {"events": [], "supported": True, "error": str(e)[:200]}

        olaylar = []
        for satir in satirlar:
            try:
                olay = normalize_dust(konum, satir)
            except Exception as e:
                logger.debug("Toz satırı okunamadı: %s", e)
                continue
            son_zaman = max(son_zaman, olay["_operate_time"])
            if not temel_kurulmadi:
                olaylar.append(olay)

        archive.set_sync_cursor(konum, TOZ_KAPSAMI, cursor=son_zaman)
        return {"events": olaylar, "supported": True,
                "baseline": temel_kurulmadi}

    def _anomali_olayi(self, konum, anomali):
        """Açıklanamayan bakiye değişimini gelen kutusuna yazar.

        Kimliğe zaman damgası giriyor çünkü bu bir borsa kaydı değil BİZİM
        gözlemimiz: aynı varlık başka bir turda tekrar açıklanamaz şekilde
        değişebilir ve o ayrı bir gözlemdir.
        """
        simdi = time.time()
        varlik = anomali["asset"]
        return {
            "event_uid": f"{konum}:unexplained:{varlik}:{int(simdi)}",
            "exchange": konum,
            "kind": UNEXPLAINED,
            "symbol": varlik,
            "base_asset": varlik,
            "quote_asset": "",
            "side": "BUY" if anomali["unexplained"] > 0 else "SELL",
            "qty": abs(anomali["unexplained"]),
            "price": 0.0,
            "quote_qty": 0.0,
            "fee_asset": "",
            "fee_qty": 0.0,
            "trade_at": datetime.now().isoformat(timespec="seconds"),
            "trade_ts": simdi,
            "raw_json": _json_dump(anomali),
        }

    # -----------------------------------------------------------------
    # Gelen kutusu
    # -----------------------------------------------------------------
    def inbox(self, status="pending", limit=200):
        import archive
        satirlar = archive.list_exchange_events(status=status, limit=limit)
        defter = self._defter()
        for s in satirlar:
            s["hint"] = self._ipucu(s, defter)
        return {
            "events": satirlar,
            "counts": archive.exchange_event_counts(),
            "last_report": self.last_report(),
            "sync_state": archive.sync_state(),
        }

    def _ipucu(self, olay, defter):
        """Satırın deftere işlenip işlenemeyeceği ve olası çift kayıt uyarısı.

        Çift kayıt uyarısı **kesin bir iddia değil**: elle girilmiş eski
        kayıtlar borsa işlem numarası taşımıyor, bu yüzden eşleştirme ancak
        "aynı gün, benzer miktar" düzeyinde olabilir. Kesin bilinmeyen bir
        şeyi kesinmiş gibi söylemek bu projede yasak; uyarı olasılık dilinde
        yazılır.
        """
        if olay.get("kind") == UNEXPLAINED:
            return {"applicable": False,
                    "reason": ("Bu bir borsa işlemi değil, açıklanamayan bir "
                               "bakiye değişimi. Para yatırma/çekme, Earn veya "
                               "vadeli transferi olabilir; bu sürüm onları "
                               "okumuyor. Deftere işlenemez.")}

        # Çift kayıt ipucu HER durumda hesaplanır ve en çok "işlenemez"
        # durumunda gerekir: satış zaten elle işlenmişse açık lot kalmaz ve
        # kullanıcı sadece "açık pozisyon yok" görürse sebebini anlamaz.
        benzer = self._benzer_defter_kaydi(defter, olay)

        if olay.get("side") == "BUY":
            ipucu = {"applicable": True, "action": "create",
                     "reason": "Deftere yeni bir alım kaydı olarak eklenir."}
            if benzer:
                ipucu["possible_duplicate"] = benzer
            return ipucu

        eslesen = self._acik_lotlar(defter, olay)
        if not eslesen:
            ipucu = {"applicable": False,
                     "reason": (f"{olay.get('base_asset')} için defterde açık "
                                "pozisyon yok; satılacak lot bulunamadı.")}
            if benzer:
                ipucu["possible_duplicate"] = benzer
                ipucu["reason"] += (" Muhtemel sebep aşağıda: bu satış zaten "
                                    "deftere işlenmiş olabilir.")
            else:
                ipucu["reason"] += " Önce alım kaydını ekleyin."
            return ipucu

        toplam = sum(_f(t.get("qty")) for t in eslesen)
        maliyet = sum(_f(t.get("qty")) * _f(t.get("cost")) for t in eslesen)
        ort = (maliyet / toplam) if toplam > 0 else 0.0
        ipucu = {
            "applicable": True, "action": "sell",
            "open_qty": round(toplam, 8),
            "avg_cost": round(ort, 8),
            "lot_count": len(eslesen),
            "reason": (f"{len(eslesen)} açık lot, toplam {toplam:g} adet, "
                       f"ortalama maliyet ${ort:,.6f}."),
        }
        if _f(olay.get("qty")) > toplam * (1 + FARK_TOLERANS_ORAN):
            ipucu["warning"] = (
                f"Borsadaki satış miktarı ({_f(olay.get('qty')):g}) defterdeki "
                f"açık miktardan ({toplam:g}) fazla. Deftere yalnızca açık "
                "miktar kadarı işlenebilir.")
        if benzer:
            ipucu["possible_duplicate"] = benzer
        return ipucu

    def _acik_lotlar(self, defter, olay):
        from data_manager import normalize_location, symbol_for_location
        konum = normalize_location(str(olay.get("exchange") or ""))
        sembol = symbol_for_location(str(olay.get("base_asset") or ""), konum)
        out = []
        for tx in (defter or {}).get("transactions", []):
            if str(tx.get("status") or "") != "Aktif":
                continue
            if normalize_location(str(tx.get("exchange") or "")) != konum:
                continue
            if symbol_for_location(str(tx.get("coin") or ""), konum) != sembol:
                continue
            out.append(tx)
        return out

    def _benzer_defter_kaydi(self, defter, olay):
        """Aynı satışın elle işlenmiş olabileceğine dair ipucu."""
        gun = str(olay.get("trade_at") or "")[:10]
        if not gun:
            return None
        from data_manager import normalize_location, symbol_for_location
        konum = normalize_location(str(olay.get("exchange") or ""))
        sembol = symbol_for_location(str(olay.get("base_asset") or ""), konum)
        miktar = _f(olay.get("qty"))
        for tx in (defter or {}).get("transactions", []):
            if str(tx.get("status") or "") == "Aktif":
                continue
            if str(tx.get("exit_date") or tx.get("date") or "")[:10] != gun:
                continue
            if symbol_for_location(str(tx.get("coin") or ""), konum) != sembol:
                continue
            kayitli = _f(tx.get("qty"))
            if miktar > 0 and abs(kayitli - miktar) <= max(
                    FARK_TOLERANS_MUTLAK, miktar * 0.05):
                return {
                    "tx_id": tx.get("id"),
                    "date": tx.get("exit_date") or tx.get("date"),
                    "qty": kayitli,
                    "note": ("Aynı gün, benzer miktarda kapanmış bir defter "
                             "kaydı var. Bu satış zaten elle işlenmiş olabilir; "
                             "işlemeden önce kontrol edin."),
                }
        return None

    # -----------------------------------------------------------------
    # Deftere işleme
    # -----------------------------------------------------------------
    def apply_event(self, event_uid, cost_method="Konsolide Ortalama",
                    live_prices=None):
        """Bir borsa işlemini deftere işler. **Yalnızca kullanıcı isteğiyle.**"""
        import archive
        from data_manager import (load_portfolio, save_portfolio,
                                  normalize_location, symbol_for_location,
                                  execute_target_sale, DEFAULT_CATEGORIES)

        olay = archive.get_exchange_event(event_uid)
        if not olay:
            raise ValueError("Bu işlem kaydı bulunamadı.")
        if olay.get("status") != archive.EVENT_PENDING:
            raise ValueError(
                f"Bu işlem zaten '{olay.get('status')}' durumunda; "
                "tekrar işlenemez.")
        if olay.get("kind") == UNEXPLAINED:
            raise ValueError(
                "Açıklanamayan bakiye değişimi deftere işlenemez. Bu bir borsa "
                "işlem kaydı değil, bizim gözlemimizdir.")

        konum = normalize_location(str(olay.get("exchange") or ""))
        taban = str(olay.get("base_asset") or "").upper()
        sembol = symbol_for_location(taban, konum)
        miktar = _f(olay.get("qty"))
        if miktar <= 0:
            raise ValueError("İşlem miktarı sıfır; deftere işlenecek bir şey yok.")

        tarih = str(olay.get("trade_at") or "")[:10] or None
        birim = self._dolar_fiyati(olay, live_prices)
        if birim is None:
            raise ValueError(
                f"Bu işlemin dolar fiyatı hesaplanamadı: karşı varlık "
                f"'{olay.get('quote_asset')}' için fiyat bilinmiyor. "
                "Deftere elle işleyin.")

        if olay.get("side") == "BUY":
            sonuc = self._alimi_isle(olay, konum, sembol, miktar, birim, tarih,
                                     load_portfolio, save_portfolio,
                                     DEFAULT_CATEGORIES)
            tx_id = sonuc.get("transaction", {}).get("id")
        else:
            defter = load_portfolio()
            lotlar = self._acik_lotlar(defter, olay)
            if not lotlar:
                raise ValueError(
                    f"{taban} için defterde açık pozisyon yok; satış işlenemez.")
            acik = sum(_f(t.get("qty")) for t in lotlar)
            satilacak = min(miktar, acik)
            komisyon_usd = self._komisyon_dolari(olay, birim, live_prices)
            sonuc = execute_target_sale(
                pos_key=f"{sembol}@{konum}",
                sell_price=birim,
                sell_qty=satilacak,
                fee_amount=_f(olay.get("fee_qty")),
                fee_asset=str(olay.get("fee_asset") or "USDT").upper(),
                fee_usd=komisyon_usd,
                cost_method=cost_method,
                sale_date=tarih,
                source_ref=event_uid,
            )
            tx_id = None

        if not archive.set_event_status(event_uid, archive.EVENT_APPLIED, tx_id):
            # Defter zaten değişti; durumu yazamadıysak kullanıcı bunu
            # BİLMELİ, yoksa aynı işlemi ikinci kez işleyebilir.
            logger.error("Defter güncellendi ama işlem durumu yazılamadı: %s",
                         event_uid)
            return {"success": True, "result": sonuc,
                    "warning": ("İşlem deftere yazıldı ama gelen kutusundaki "
                                "durumu güncellenemedi. Aynı satırı ikinci kez "
                                "işlemeyin.")}
        logger.info("Borsa işlemi deftere işlendi: %s (%s %s)",
                    event_uid, olay.get("side"), sembol)
        return {"success": True, "result": sonuc}

    def _alimi_isle(self, olay, konum, sembol, miktar, birim, tarih,
                    load_portfolio, save_portfolio, DEFAULT_CATEGORIES):
        defter = load_portfolio()
        tx_list = defter.setdefault("transactions", [])
        next_id = defter.get("next_tx_id") or (
            max((int(t.get("id") or 0) for t in tx_list), default=0) + 1)

        kayit = {
            "id": next_id,
            "date": tarih or datetime.now().strftime("%Y-%m-%d"),
            "coin": sembol,
            "exchange": konum,
            "qty": miktar,
            "cost": birim,
            "status": "Aktif",
            "notes": (f"Borsadan yakalandı ({olay.get('trade_at')}) | "
                      f"{olay.get('symbol')} @ {_f(olay.get('price')):g}"),
            "category": DEFAULT_CATEGORIES.get(sembol,
                                               DEFAULT_CATEGORIES.get(
                                                   str(olay.get("base_asset")),
                                                   "Altcoin")),
            "fee_amount": _f(olay.get("fee_qty")),
            "fee_asset": str(olay.get("fee_asset") or "USDT").upper(),
            "fee_usd": 0.0,
            "source_ref": olay.get("event_uid"),
        }
        tx_list.append(kayit)
        defter["next_tx_id"] = next_id + 1
        save_portfolio(defter)
        return {"transaction": kayit}

    def _dolar_fiyati(self, olay, live_prices=None):
        """Birim fiyatı dolara çevirir.

        Karşı varlık stabilse fiyat zaten dolardır. Değilse (toz dönüşümünde
        hedef BNB olabilir, ETH/BTC gibi çiftlerde kot BTC'dir) canlı fiyat
        gerekir. Fiyat yoksa None döner ve işlem REDDEDİLİR — uydurma bir
        kurla gerçekleşmiş K/Z hesaplamak, yanlış bir sayıyı doğru gibi
        deftere yazmak olurdu.
        """
        fiyat = _f(olay.get("price"))
        if fiyat <= 0:
            return None
        kot = str(olay.get("quote_asset") or "").upper()
        if not kot or kot in NAKIT_VARLIKLAR:
            return fiyat
        kur = self._varlik_dolari(kot, live_prices)
        return None if kur is None else fiyat * kur

    def _komisyon_dolari(self, olay, birim_usd, live_prices=None):
        komisyon = _f(olay.get("fee_qty"))
        if komisyon <= 0:
            return 0.0
        varlik = str(olay.get("fee_asset") or "").upper()
        if not varlik or varlik in NAKIT_VARLIKLAR:
            return komisyon
        if varlik == str(olay.get("base_asset") or "").upper():
            return komisyon * birim_usd
        kur = self._varlik_dolari(varlik, live_prices)
        # Komisyonun doları bilinmiyorsa sıfır sayılır ve bu ABARTMA DEĞİL
        # eksiltmedir: gerçekleşmiş kâr olduğundan biraz yüksek görünür.
        # Alternatif (işlemi tümden reddetmek) BNB ile ödenen her komisyonda
        # özelliği kullanılamaz yapardı.
        return 0.0 if kur is None else komisyon * kur

    def _varlik_dolari(self, varlik, live_prices=None):
        if live_prices is None:
            try:
                from price_service import price_service
                live_prices = price_service.get_prices()
            except Exception:
                return None
        for anahtar in (f"{varlik}USDT", varlik):
            kayit = (live_prices or {}).get(anahtar)
            if isinstance(kayit, dict) and _f(kayit.get("price")) > 0:
                return _f(kayit["price"])
        return None

    def dismiss_event(self, event_uid):
        import archive
        olay = archive.get_exchange_event(event_uid)
        if not olay:
            raise ValueError("Bu işlem kaydı bulunamadı.")
        if olay.get("status") != archive.EVENT_PENDING:
            raise ValueError(
                f"Bu işlem zaten '{olay.get('status')}' durumunda.")
        if not archive.set_event_status(event_uid, archive.EVENT_DISMISSED):
            raise ValueError("İşlem durumu güncellenemedi.")
        return {"success": True}


# Uygulama genelinde tek örnek — price_service ve market_service ile aynı desen.
trade_sync = TradeSyncService()
