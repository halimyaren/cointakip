"""
CoinTakip — Borsa Geçmişinin API'den Doldurulması (FAZ F7c)
=====================================================================

NE İŞE YARAR
------------
Mutabakat (`reconcile`) bugüne kadar yalnızca kullanıcının borsanın web
arayüzünden indirdiği dosyaları okuyabiliyordu. Dosyalar 2023-02'ye kadar
iniyor — yani API'nin ULAŞAMADIĞI derinlik — ama her ay yeniden indirilmek
zorundalar. İndirilmedikleri her gün mutabakat biraz daha körleşir; iki
indirme arasındaki fark "defter yanlış" gibi görünür, oysa yalnızca dosya
eskidir.

Bu modül aynı olayları BORSA API'SİNDEN üretir. İş bölümü şudur:

  * **Derin geçmiş** → dosyalar. Bir kez indirilir, değişmez arşivdir.
  * **Son dönem**    → API. Her doldurmada güncellenir.

DOSYA ESASTIR, API BOŞLUĞU DOLDURUR
-----------------------------------
Aynı işlem hem dosyada hem API'de bulunur. İkisini birden almak her işlemi
iki kez saydırır — mutabakatın bütün değeri doğru sayabilmesinde olduğu için
bu ölümcül bir hatadır. Kural tek cümledir: **bir borsanın dosyaları nereye
kadar geliyorsa, API yalnızca ORADAN SONRASINI doldurur.**

Sınır dosyalardan yana çizildi çünkü dosyalar daha zengindir. Çevrimler
(Convert), airdrop dağıtımları, cüzdanlar arası taşımalar hesap defteri
dosyasında görünür; API'de bunların bir kısmının karşılığı hiç yoktur.
Çakışan bir dönemde daha eksik kaynağı tercih etmek için sebep yok.

DEFTERE YAZMAZ
--------------
`reconcile` modülünün yasası burada da geçerlidir: maliyet tabanı
kullanıcının elle girdiği hâliyle kalır, borsa onu asla ezmez. Bu modül
yalnızca "borsa ne diyor" tarafını üretir; ne aktarılacağına kullanıcı
karar verir.

NEDEN ARŞİVE YAZILIYOR
----------------------
Doldurma pahalıdır: sembol başına ayrı çağrı, Earn ucunda çağrı başına 150
ağırlık, para hareketlerinde borsaya göre değişen pencereler. Bunu her mutabakat
raporunda yeniden yapmak hem yavaş hem de sınırları zorlayan bir israftır.
Bu yüzden doldurma AÇIKÇA tetiklenen bir iştir ve sonucu arşivde durur;
mutabakat ağa hiç çıkmadan onu okur.
"""

import time
from datetime import datetime

from log_config import get_logger

logger = get_logger("api_history")

# Bir sembol için en fazla kaç sayfa çekilir. Sayfa 1000 satır; 40 sayfa
# 40.000 işlem eder ve bireysel bir hesapta bu tavana çarpılmaz. Tavan yine
# de var: ucun beklenmedik bir yanıt vermesi hâlinde döngünün sonsuza kadar
# dönmesi bir hata değil felakettir.
SAYFA_TAVANI = 40

# NE KADAR GERİYE GİDİLİR
# ----------------------
# Sabit bir derinlik yazmıyoruz. Doldurmanın işi dosyaların BIRAKTIĞI
# BOŞLUĞU kapatmak; dosya 27 Ağustos'ta bitiyorsa iki yıl geriye gitmenin
# tek sonucu, sonradan zaten atılacak satırlar için yüzlerce istek atmaktır.
# Derinlik bu yüzden sınırdan hesaplanır ve dosya yoksa varsayılana düşer.
VARSAYILAN_GERIYE_GUN = 730       # dosya hiç yoksa ~2 yıl
GUVENLIK_PAYI_GUN = 7             # sınırla bilinçli üst üste binme

# Tek bir akışta atılacak en fazla istek. Derinlik sınırdan hesaplandığı için
# pratikte bu tavana çarpılmaz; tavan, beklenmedik bir sınır değerinin
# (bozuk tarih, gelecekteki bir zaman damgası) binlerce isteğe dönüşmesini
# engellemek için var.
PENCERE_TAVANI = 60

# HIZ SINIRINA SAYGI
# ------------------
# Uçların ağırlıkları çok farklı: `myTrades` 20, Earn ödülleri 150. Sabit bir
# bekleme ikisine de yanlış gelir — biri gereksiz yavaşlar, diğeri sınırı
# zorlar. Bekleme bu yüzden ağırlıktan hesaplanıyor. Bütçe Binance'in dakika
# başına 6000'lik tavanının bir bölümü; kalanı düzenli taramaya ve fiyat
# motoruna bırakılıyor, çünkü doldurma sürerken onlar da çalışıyor.
AGIRLIK_BUTCESI_DK = 2400


def _nefes(agirlik):
    """Ağırlığa göre bekleme. Doldurma arka planda çalışan taramayı aç
    bırakmamalı; bütçenin tamamını kendine ayırmıyor."""
    time.sleep(max(0.0, float(agirlik)) / (AGIRLIK_BUTCESI_DK / 60.0))


# =====================================================================
# Sınır: dosyalar nereye kadar geliyor
# =====================================================================
def dosya_sinirlari(dosya_olaylari):
    """Borsa → dosyaların ulaştığı EN SON zaman (ISO, 19 karakter).

    API olaylarından bu sınırın gerisinde kalanlar atılır. Sınırın kendisi
    de dâhil edilir (`<=`): dosyanın son satırıyla aynı saniyedeki bir işlem
    büyük olasılıkla o satırın ta kendisidir ve iki kez saymaktansa bir kez
    saymak doğrudur — eksik saymak raporda görünür, çift saymak görünmez.
    """
    sinir = {}
    for o in dosya_olaylari or []:
        zaman = str(o.get("time") or "")[:19]
        if not zaman:
            continue
        borsa = str(o.get("exchange") or "").upper().strip()
        if zaman > sinir.get(borsa, ""):
            sinir[borsa] = zaman
    return sinir


def sinirin_otesi(api_olaylari, sinirlar):
    """API olaylarından yalnızca dosyaların bitiminden SONRA olanlar."""
    out = []
    for o in api_olaylari or []:
        borsa = str(o.get("exchange") or "").upper().strip()
        sinir = (sinirlar or {}).get(borsa)
        zaman = str(o.get("time") or "")[:19]
        if sinir and zaman and zaman <= sinir:
            continue
        out.append(o)
    return out


# =====================================================================
# Borsa olayı → mutabakat olayı
# =====================================================================
def _kaynak_adi(konum):
    return f"{str(konum or '').title()} API"


def defter_olaylari(olay, kaynak=""):
    """Bir `trade_sync` olayını mutabakatın anladığı olay(lar)a çevirir.

    Miktarların doğruluğu `trade_sync.olay_bakiye_etkisi` ile aynı kuralları
    izler; ikisi ayrışırsa aynı işlem dosyadan mı API'den mi geldiğine göre
    farklı bakiye üretirdi ve bu, mutabakatın güvenilirliğini bitirirdi.
    """
    import reconcile
    import trade_sync

    borsa = str(olay.get("exchange") or "").upper().strip()
    zaman = str(olay.get("trade_at") or "")[:19]
    tur = str(olay.get("kind") or "")
    taban = str(olay.get("base_asset") or "").upper().strip()
    kot = str(olay.get("quote_asset") or "").upper().strip()
    miktar = float(olay.get("qty") or 0.0)
    tutar = float(olay.get("quote_qty") or 0.0)
    kom_varlik = str(olay.get("fee_asset") or "").upper().strip()
    komisyon = float(olay.get("fee_qty") or 0.0)
    kaynak = kaynak or _kaynak_adi(borsa)

    if tur in (trade_sync.TRADE, trade_sync.DUST):
        return _alim_satim_olaylari(
            borsa, zaman, tur, str(olay.get("side") or "").upper(),
            taban, kot, miktar, tutar, float(olay.get("price") or 0.0),
            kom_varlik, komisyon, kaynak)

    if tur == trade_sync.EARN:
        # Bedelsiz giriş. Dosya tarafında `TH_REWARD_OPS` aynı şekilde
        # işaretleniyor; iki yolun aynı sonucu vermesi şart.
        return [reconcile._olay(
            borsa, zaman, "REWARD", taban, miktar,
            zero_cost=True, operation="Simple Earn Rewards", source=kaynak)]

    if tur == trade_sync.DEPOSIT:
        return [reconcile._olay(borsa, zaman, "DEPOSIT", taban, miktar,
                                operation="Deposit", source=kaynak)]

    if tur == trade_sync.WITHDRAW:
        # Ağ komisyonu çekilen varlığın kendisinden gider ve o da bakiyeden
        # çıkar. Yalnızca `amount` yazılırsa komisyon kadarı her seferinde
        # açıklanamayan bir fark olarak kalırdı.
        return [reconcile._olay(borsa, zaman, "WITHDRAW", taban,
                                -(miktar + komisyon),
                                operation="Withdraw", source=kaynak)]

    return []


def _alim_satim_olaylari(borsa, zaman, tur, yon, taban, kot, miktar, tutar,
                         fiyat, kom_varlik, komisyon, kaynak):
    """Spot işlem ve toz dönüşümünün mutabakat satırları.

    `reconcile.load_binance_trades` ile aynı biçimi üretir. Oradaki iki
    incelik burada da geçerli: komisyon işlem varlığının kendisinden
    alındıysa miktar zaten NET'tir (`normalize_trade` düşmüştür), başka bir
    coinden ödendiyse o coinin bakiyesi ayrı bir satırla azalır.
    """
    import reconcile
    import trade_sync

    isaret = 1.0 if yon == "BUY" else -1.0
    stabil = kot in reconcile.STABLE_QUOTES
    satirlar = [reconcile._olay(
        borsa, zaman, "TRADE", taban, isaret * miktar,
        quote_asset=kot, quote_qty=-isaret * tutar, price=fiyat,
        fee_asset=kom_varlik, fee_qty=komisyon,
        usd_value=tutar if stabil else 0.0, usd_known=stabil,
        operation="Dust Convert" if tur == trade_sync.DUST else "Trade",
        source=kaynak)]

    if tur == trade_sync.DUST:
        # Toz dönüşümünün GELEN bacağı. Kaynak varlık çıkarken hedef varlık
        # (genellikle BNB) girer; yalnızca çıkan bacağı yazmak BNB bakiyesini
        # olduğundan düşük yeniden kurardı. Hedef stabil değilse bu girişin
        # dolar maliyeti BİLİNMİYOR — uydurmak yerine söylemek doğrudur.
        net = tutar - komisyon
        if kot and net > 0:
            satirlar.append(reconcile._olay(
                borsa, zaman, "TRADE", kot, net,
                usd_value=net if stabil else 0.0, usd_known=stabil,
                operation="Dust Convert", source=kaynak))
        return satirlar

    # Komisyon BAŞKA bir coinden ödendiyse (Binance'te çoğunlukla BNB) o
    # coinin bakiyesi azalır. Komisyon işlem varlığının kendisindense
    # `normalize_trade` onu zaten miktardan düşmüştür; ikinci kez yazmak
    # çift sayım olurdu.
    if komisyon > 0 and kom_varlik and kom_varlik != taban:
        satirlar.append(reconcile._olay(
            borsa, zaman, "FEE", kom_varlik, -komisyon,
            operation="Trade Fee", source=kaynak))
    return satirlar


# =====================================================================
# Toplama
# =====================================================================
def _pencereler(pencere_ms, adet):
    """En yeniden en eskiye doğru (başlangıç, bitiş) çiftleri.

    Uçların hepsi bir pencere tavanı dayatıyor ve tavan borsaya göre değişir
    (Binance para hareketlerinde 90 gün, MEXC'te 7). Geçmişe inmenin tek yolu
    pencereyi kaydıra kaydıra yürümek.
    """
    bitis = int(time.time() * 1000)
    for _ in range(max(1, int(adet))):
        baslangic = bitis - pencere_ms
        yield baslangic, bitis
        bitis = baslangic - 1


def _geriye_gun(sinir):
    """Doldurmanın kaç gün geriye gideceği.

    `sinir` o borsanın dosyalarının ulaştığı en son zaman. Boşsa dosya yok
    demektir ve varsayılan derinliğe düşülür. Emniyet payı bilinçli: sınırın
    hemen ötesindeki bir işlemi kaçırmaktansa üst üste binmek yeğdir, çünkü
    çakışan satırlar zaten `sinirin_otesi` tarafından atılıyor.
    """
    if not sinir:
        return VARSAYILAN_GERIYE_GUN
    try:
        an = datetime.strptime(str(sinir)[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            an = datetime.strptime(str(sinir)[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return VARSAYILAN_GERIYE_GUN
    gun = (datetime.now() - an).days + GUVENLIK_PAYI_GUN
    return max(GUVENLIK_PAYI_GUN, min(gun, VARSAYILAN_GERIYE_GUN))


def _pencere_adedi(geriye_gun, pencere_gun):
    """Verilen derinliği kapatmak için kaç pencere gerekir."""
    pencere_gun = max(1, int(pencere_gun))
    adet = -(-int(geriye_gun) // pencere_gun)        # yukarı yuvarlama
    return max(1, min(adet, PENCERE_TAVANI))


def _sembol_atlanir_mi(konum, sembol):
    """Borsanın "böyle bir sembol yok" dediği çiftler doldurmada da atlanır.

    Düzenli tarama bu elemeyi yapıyordu, doldurma yapmıyordu; sonuç, borsanın
    artık tanımadığı bir sembolün (MEXC'te `XAUTUSDT`, doğrusu
    `GOLD(XAUT)USDT`) her doldurmada uyarı üretmesiydi. Aynı bilgi iki yerde
    farklı davranmamalı.
    """
    import archive
    import trade_sync

    durum = archive.get_sync_cursor(konum, sembol) or {}
    if durum.get("cursor"):
        return False              # bir kez çalışmış, hata geçiciydi
    return trade_sync.gecersiz_sembol_hatasi_mi(durum.get("last_error"))


def _sembol_islemleri(profil, konum, sembol):
    """Bir sembolün TÜM işlem geçmişi. `fromId=0`'dan başlar."""
    import exchanges
    import trade_sync

    olaylar = []
    from_id, en_buyuk = 0, 0
    for _ in range(SAYFA_TAVANI):
        satirlar = exchanges.fetch_my_trades(profil, sembol, from_id=from_id)
        if not satirlar:
            break
        for ham in satirlar:
            try:
                olay = trade_sync.normalize_trade(konum, ham)
            except Exception as e:
                logger.debug("İşlem satırı okunamadı (%s): %s", sembol, e)
                continue
            en_buyuk = max(en_buyuk, olay["_trade_id"])
            olaylar.append(olay)
        if len(satirlar) < exchanges.MY_TRADES_LIMIT:
            break
        from_id = en_buyuk + 1
        _nefes(exchanges.MY_TRADES_WEIGHT)
    return olaylar


def _pencereli_akis(profil, konum, cek, cozumle, pencere_ms, adet, etiket,
                    agirlik):
    """Pencere pencere geriye giden bir akış. Hata pencereyi atlatır, akışı
    değil: bir pencerenin düşmesi diğerlerini iptal etmemeli."""
    olaylar, uyarilar = [], []
    for baslangic, bitis in _pencereler(pencere_ms, adet):
        try:
            satirlar = cek(profil, baslangic, bitis)
        except Exception as e:
            uyarilar.append(f"{konum} {etiket} penceresi okunamadı: {e}")
            logger.debug("%s okunamadı (%s): %s", etiket, konum, e)
            continue
        for satir in satirlar:
            try:
                olaylar.append(cozumle(konum, satir))
            except Exception as e:
                # Kapsam dışı satırlar (iade edilmiş çekme, bekleyen yatırma)
                # da buraya düşer ve atlanmaları DOĞRUDUR.
                logger.debug("%s satırı atlandı: %s", etiket, e)
        _nefes(agirlik)
    return olaylar, uyarilar


def _borsa_akislari(profil, konum, sinir=None):
    """Hesap düzeyindeki akışların tamamı. (olaylar, uyarilar)

    Pencere GENİŞLİĞİ borsadan, pencere SAYISI dosya sınırından gelir.
    İkisini de sabit yazmak iki ayrı hataya yol açmıştı: MEXC'in 7 günlük
    tavanına 90 günlük aralık göndermek her çağrıyı düşürüyordu, ve sabit
    derinlik dosyaların zaten kapsadığı dönem için yüzlerce gereksiz istek
    attırıyordu.
    """
    import exchanges
    import trade_sync

    olaylar, uyarilar = [], []
    geriye = _geriye_gun(sinir)

    if exchanges.supports(profil, "dust_log_path"):
        # Toz ucu aralık almıyor: son 100 kayıt neyse odur.
        #
        # `fetch_dust_log` iç içe cevabı ZATEN açıyor (`return dust_rows(ham)`).
        # Burada bir kez daha `dust_rows` uygulamak, listeye sözlük muamelesi
        # yapıp "yanıt beklenen biçimde değil" hatası veriyordu ve doldurmada
        # hiç toz kaydı olmuyordu. Düzenli tarama bu hatayı yapmıyordu çünkü
        # o, `fetch_dust_log`un çıktısını doğrudan `normalize_dust`a veriyor.
        try:
            for satir in exchanges.fetch_dust_log(profil):
                try:
                    olaylar.append(trade_sync.normalize_dust(konum, satir))
                except Exception as e:
                    logger.debug("Toz satırı atlandı: %s", e)
        except Exception as e:
            uyarilar.append(f"{konum} toz dönüşümü geçmişi okunamadı: {e}")

    akislar = [
        ("earn_flexible_path", "Earn (esnek) ödülleri",
         lambda p, b, s: exchanges.fetch_earn_rewards(
             p, locked=False, start_time_ms=b, end_time_ms=s),
         trade_sync.normalize_earn, "earn_window_days",
         exchanges.EARN_PENCERE_GUN, exchanges.EARN_WEIGHT),
        ("earn_locked_path", "Earn (vadeli) ödülleri",
         lambda p, b, s: exchanges.fetch_earn_rewards(
             p, locked=True, start_time_ms=b, end_time_ms=s),
         trade_sync.normalize_earn, "earn_window_days",
         exchanges.EARN_PENCERE_GUN, exchanges.EARN_WEIGHT),
        ("deposit_path", "para yatırma",
         lambda p, b, s: exchanges.fetch_deposits(
             p, start_time_ms=b, end_time_ms=s),
         trade_sync.normalize_deposit, "capital_window_days",
         exchanges.CAPITAL_PENCERE_GUN, exchanges.CAPITAL_WEIGHT),
        ("withdraw_path", "para çekme",
         lambda p, b, s: exchanges.fetch_withdrawals(
             p, start_time_ms=b, end_time_ms=s),
         trade_sync.normalize_withdraw, "capital_window_days",
         exchanges.CAPITAL_PENCERE_GUN, exchanges.CAPITAL_WEIGHT),
    ]
    for alan, etiket, cek, cozumle, pencere_alani, varsayilan, agirlik in akislar:
        if not exchanges.supports(profil, alan):
            continue
        pencere_gun = exchanges.pencere_gunu(profil, pencere_alani, varsayilan)
        yeni, uy = _pencereli_akis(
            profil, konum, cek, cozumle, pencere_gun * exchanges.GUN_MS,
            _pencere_adedi(geriye, pencere_gun), etiket, agirlik)
        olaylar.extend(yeni)
        uyarilar.extend(uy)
    return olaylar, uyarilar


def topla(defter, profiller=None, sinirlar=None):
    """Borsa API'sinden geçmişi toplar. (olaylar, kaynaklar, uyarilar)

    **Ağa çıkar ve yavaştır.** Çağıran taraf bunu açık bir kullanıcı
    eylemine bağlamalı; beş dakikada bir çalışan tarama bu yoldan geçmez.

    `sinirlar` borsa başına dosyaların ulaştığı en son zamandır
    (`dosya_sinirlari`). Verilirse doldurma yalnızca o noktadan bugüne kadar
    iner — dosyaların zaten kapsadığı dönem için istek atmak, sonradan
    atılacak satırlar uğruna borsanın hız sınırını harcamak olurdu.
    """
    import exchanges
    import keyvault
    import trade_sync

    olaylar, kaynaklar, uyarilar = [], [], []

    if not keyvault.is_unlocked():
        return [], [], ["Anahtar kasası kilitli; API'den geçmiş okunamaz."]

    profiller = profiller if profiller is not None else {
        k: v for k, v in exchanges.list_profiles().items()
        if v.get("enabled", True)}

    for konum, profil in sorted(profiller.items()):
        ham_olaylar = []
        try:
            okuma = exchanges.read_exchange(konum, profil)
        except Exception as e:
            uyarilar.append(f"{konum} bakiyesi okunamadı: {e}")
            continue

        bakiyeler = okuma.get("balances") or []
        semboller = [s for s in trade_sync.aday_semboller(konum, defter, bakiyeler)
                     if not _sembol_atlanir_mi(konum, s)]
        for sembol in semboller:
            try:
                ham_olaylar.extend(_sembol_islemleri(profil, konum, sembol))
            except Exception as e:
                uyarilar.append(f"{konum} {sembol} işlem geçmişi okunamadı: {e}")
                logger.debug("Sembol doldurulamadı (%s/%s): %s", konum, sembol, e)

        sinir = (sinirlar or {}).get(konum)
        akis_olaylari, akis_uyarilari = _borsa_akislari(profil, konum, sinir)
        ham_olaylar.extend(akis_olaylari)
        uyarilar.extend(akis_uyarilari)

        kaynak = _kaynak_adi(konum)
        borsa_olaylari = []
        for olay in ham_olaylar:
            borsa_olaylari.extend(defter_olaylari(olay, kaynak))

        tarihler = sorted(o["time"] for o in borsa_olaylari if o["time"])
        kaynaklar.append({
            "name": kaynak, "exchange": konum, "kind": "api",
            "rows": len(borsa_olaylari),
            "first": tarihler[0][:10] if tarihler else None,
            "last": tarihler[-1][:10] if tarihler else None,
            "symbols": len(semboller),
        })
        olaylar.extend(borsa_olaylari)

    return olaylar, kaynaklar, uyarilar
