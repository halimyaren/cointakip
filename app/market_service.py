"""
CoinTakip — PİYASA VERİSİ SERVİSİ (FAZ M1)

═══════════════════════════════════════════════════════════════════════════
NEDEN VAR
═══════════════════════════════════════════════════════════════════════════
Yapay zekâ analiz motoru portföyü tam olarak biliyordu ama PİYASAYI hiç
bilmiyordu. Kullanıcı bunu şöyle fark etti: her analizde aynı öneriyi
alıyordu ("BTC'nin %25'ini sat"). Sebebin bir yarısı hafızasızlıktı ve
FAZ 6.005'te çözüldü. Diğer yarısı buydu — modelin piyasa hakkında
söyleyecek yeni bir şeyi yoktu, çünkü kendisine hiç piyasa verisi
gitmiyordu.

Bu modül o boşluğu kapatır. Beş çekirdek metrik toplar:
BTC trendi, ETH/BTC, piyasa genişliği, Fear & Greed, BTC dominansı + mcap.

═══════════════════════════════════════════════════════════════════════════
TASARIM KURALLARI — hepsi ölçümle gerekçelendirildi (5 Eylül 2026)
═══════════════════════════════════════════════════════════════════════════

1) HÜKÜM VERMEYİZ, SAYI VERİRİZ.
   Ölçüm günü BTC şu hâldeydi: SMA50 ($69.131) < SMA200 ($69.719), yani
   kitaba göre "ölüm kesişimi" — düşüş sinyali. Ama fiyat ($79.754) her iki
   ortalamanın da %14 üstündeydi ve 30 günde %24 yükselmişti. Etiket
   gerçeğin tersini söylüyordu. Bu yüzden bu modül "boğa/ayı", "altseason"
   gibi hüküm üretmez; ölçülebilir sayıları verir, yorumu modele bırakır.
   (Tek istisna: Fear & Greed'in KENDİ sınıflandırması. O bizim etiketimiz
   değil, kullanıcının da ekranda gördüğü sağlayıcı etiketidir; kaynağı
   belirtilerek aynen geçirilir.)

2) DOMİNANS BİR OLGU DEĞİL, BİR KONVANSİYONDUR.
   Aynı anda ölçüldü:
       CoinGecko    58.84   (19.612 coin kapsıyor)
       Coinpaprika  56.52   (13.657 coin)
       Coinlore     59.33   (14.993 coin)
   Yayılım 2.81 PUAN. Bu bir hata değil: her kaynağın bildirdiği dominans
   kendi bildirdiği toplam piyasa değeriyle tutarlı. Fark "toplam piyasa"
   tanımından geliyor. Bu yüzden TEK kaynak kullanılır ve kaynak adı her
   kayda yazılır. Kaynak sonradan değişirse arşivde "dominans bir gecede
   3 puan atladı" diye SAHTE bir sinyal doğar ve model bunun üzerine
   tavsiye kurar.

3) YAVAŞ KAYNAK EŞZAMANLI ÇAĞRILMAZ.
   Ölçülen gecikmeler (kullanıcının ağı, tekrarlı):
       Binance         375 / 836 / 374 ms
       alternative.me  462 / 460 / 442 ms
       CoinGecko    22445 / 15403 / 7446 ms   <-- hız sınırı cezası DEĞİL
       Coinpaprika    254 / 1289 / 24347 ms
   CoinGecko'nun yavaşlığı 7 dakikalık soğuma sonrası da sürdü. Bu yüzden
   tüm çekimler ARKA PLANDA yapılır; analiz anında yalnızca hafızadan
   okunur. Piyasa verisi yoksa analiz eksik veriyle ama ZAMANINDA çalışır.

4) BAYAT VERİ SESSİZCE VERİLMEZ.
   Her metrik yaşını taşır. Taze → aynen gider. Bayat → yaşıyla birlikte
   gider. Çok eski → hiç gitmez. Sessiz başarısızlık bu projede en pahalı
   hata türü sayılır (bkz. Gate.io, aylarca 403 alıp "açık" göründü).

5) GENİŞLİK BEDAVA — UYDURULMAZ.
   `price_service` zaten her turda Binance'in tüm 24s ticker'ını indiriyor
   (1.89 MB, 3695 çift). Piyasa genişliği o veriden SIFIR ek çağrıyla
   türetilir. Kullanıcı Binance kademesini kapatmışsa genişlik hesaplanamaz;
   o zaman "yok" denir, tahmin edilmez.

═══════════════════════════════════════════════════════════════════════════
ANAHTAR POLİTİKASI
═══════════════════════════════════════════════════════════════════════════
CoinGecko anahtarsız da çalışır ama IP başına dakikada 5-15 çağrıyla
sınırlıdır (ölçüldü: 5. çağrıda HTTP 429, `retry-after: 60`). Ücretsiz demo
anahtarı bunu dakikada 100'e çıkarır ve TABAN ADRESİ DEĞİŞTİRMEZ — yalnızca
`x-cg-demo-api-key` başlığı eklenir.

Kullanıcının kararı: anahtar "isteğe bağlı bir ekstra" değil, TERCİH EDİLEN
yoldur. Anahtarsız yol çalışmaya devam eder ama arayüzde görünür biçimde
YEDEK olarak konumlandırılır — kullanıcı hangi kalitede veri aldığını
bilmelidir.
"""

import statistics
import threading
import time

from log_config import get_logger

logger = get_logger("market_service")

# =====================================================================
# KAYNAK KAYIT DEFTERİ
# =====================================================================
# `price_sources` ile aynı desen: kaynak eklemek/kapatmak kod değil ayardır.
MARKET_SOURCE_IDS = ("btc_trend", "ethbtc", "breadth", "fear_greed", "global")

MARKET_SOURCE_LABELS = {
    "btc_trend":   "BTC trendi (Binance)",
    "ethbtc":      "ETH/BTC (Binance)",
    "breadth":     "Piyasa genişliği (mevcut Binance verisi)",
    "fear_greed":  "Korku & Açgözlülük (alternative.me)",
    "global":      "Dominans & piyasa değeri (CoinGecko)",
}

DEFAULT_MARKET_URLS = {
    "btc_klines":  "https://api.binance.com/api/v3/klines",
    "fear_greed":  "https://api.alternative.me/fng/",
    "coingecko_global": "https://api.coingecko.com/api/v3/global",
}

# Kaynak başına yenileme aralığı (saniye). Metriklerin gerçek değişim
# hızına göre seçildi; hepsini aynı tempoya bağlamak ücretsiz uçları
# gereksiz yorar.
KAYNAK_TTL = {
    "btc_trend":  900.0,    # 15 dk — günlük mum, ama son mum canlı
    "ethbtc":     900.0,
    "fear_greed": 1800.0,   # 30 dk — endeks zaten günde bir güncelleniyor
    "global":     900.0,    # 15 dk — yavaş uç, sık çağırmanın anlamı yok
}

# Tazelik eşikleri (saniye): (bayat_sayilir, artik_verilmez).
#
# Metrik başına AYRI, çünkü doğal tempoları farklı: Fear & Greed günde bir
# kez güncellenir, yani 30 saatlik bir F&G değeri hâlâ GÜNCEL değerdir —
# ona fiyat verisiyle aynı eşiği uygulamak, sağlam veriyi boşuna atmak olur.
TAZELIK_ESIKLERI = {
    "btc_trend":  (7200.0, 43200.0),      # 2 saat / 12 saat
    "ethbtc":     (7200.0, 43200.0),
    "breadth":    (900.0, 7200.0),        # 15 dk / 2 saat — en hızlı bayatlayan
    "fear_greed": (129600.0, 259200.0),   # 36 saat / 72 saat
    "global":     (21600.0, 86400.0),     # 6 saat / 24 saat
}

TAZE = "fresh"
BAYAT = "stale"

# Genişlik hesabında bir çiftin "likit" sayılması için gereken 24s hacim.
# Düşük hacimli çöp çiftler yüzde değişimde uçuk değerler üretir ve
# medyanı bozar.
GENISLIK_MIN_HACIM_USDT = 1_000_000.0

# Arka plan döngüsünün uyanma sıklığı. Asıl tempoyu KAYNAK_TTL belirler;
# bu yalnızca "zamanı geldi mi" kontrolünün sıklığıdır.
DONGU_ARALIGI = 60.0

# İlk çekim bu kadar gecikmeyle yapılır. Uygulama açılışını ve ilk fiyat
# turunu bloke etmemek için: piyasa verisi hiçbir zaman acil değildir.
ILK_CEKIM_GECIKMESI = 8.0

# Klines penceresi. 250 gün, SMA200 + makul bir tampon demek.
KLINE_LIMIT = 250

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _yuzde(yeni, eski):
    """Yüzde değişim. Payda sıfır/negatifse None — sıfıra bölmek yerine yokluk."""
    try:
        eski = float(eski)
        if eski <= 0:
            return None
        return round(100.0 * (float(yeni) - eski) / eski, 2)
    except (TypeError, ValueError):
        return None


def _tazelik(kaynak_id, yas_sn):
    """Yaşı tazelik etiketine çevirir. Üçüncü durum (çok eski) None döner."""
    bayat_esik, atma_esik = TAZELIK_ESIKLERI.get(kaynak_id, (3600.0, 86400.0))
    if yas_sn is None or yas_sn < 0:
        return None
    if yas_sn > atma_esik:
        return None
    return TAZE if yas_sn <= bayat_esik else BAYAT


class MarketDataService:
    """Piyasa verisini arka planda toplar, önbellekte tutar, yaşıyla sunar."""

    def __init__(self, price_engine=None):
        # price_engine: genişlik türetimi ve ayar okuma için. Testler sahte
        # bir motor verebilsin diye enjekte ediliyor, modül içinde import
        # edilmiyor.
        self.price_engine = price_engine
        self.lock = threading.Lock()
        self.is_running = False

        # { kaynak_id: {"data": {...}, "fetched_at": float} }
        self._cache = {}
        # { kaynak_id: {"ok":bool,"last_error":str,"last_ok_ts":float,
        #               "last_try_ts":float,"fail_count":int} }
        self._health = {}
        self._son_dongu_ts = 0.0

    # -----------------------------------------------------------------
    # Yaşam döngüsü
    # -----------------------------------------------------------------
    def start_background_updater(self):
        if self.is_running:
            return
        self.is_running = True
        t = threading.Thread(target=self._background_loop, daemon=True)
        t.start()
        logger.info("Piyasa verisi servisi aktif (ilk çekim %.0f sn sonra).",
                    ILK_CEKIM_GECIKMESI)

    def stop(self):
        self.is_running = False

    def _background_loop(self):
        # Açılışta beklemek bilinçli: fiyat motoru ilk turunu rahatça atsın.
        time.sleep(ILK_CEKIM_GECIKMESI)
        while self.is_running:
            try:
                self.refresh_due()
            except Exception as e:
                logger.warning("Piyasa verisi döngüsünde hata: %s", e)
            time.sleep(DONGU_ARALIGI)

    # -----------------------------------------------------------------
    # Yapılandırma
    # -----------------------------------------------------------------
    def _ayarlar(self):
        try:
            from data_manager import load_settings
            return load_settings() or {}
        except Exception as e:
            logger.debug("Piyasa ayarları okunamadı: %s", e)
            return {}

    def _url(self, anahtar):
        s = self._ayarlar()
        urls = s.get("api_urls") or {}
        return urls.get(anahtar) or DEFAULT_MARKET_URLS[anahtar]

    def _coingecko_anahtari(self):
        """Ücretsiz demo anahtarı. Yoksa boş dize döner (anahtarsız yedek yol)."""
        s = self._ayarlar()
        ham = ((s.get("api_keys") or {}).get("coingecko_api_key") or "").strip()
        return ham

    def aktif_kaynaklar(self):
        """Kullanıcının açtığı piyasa kaynakları."""
        s = self._ayarlar()
        kayitli = s.get("market_sources") or {}
        aktif = []
        for sid in MARKET_SOURCE_IDS:
            row = kayitli.get(sid)
            if isinstance(row, dict):
                if row.get("enabled", True):
                    aktif.append(sid)
            else:
                aktif.append(sid)     # tanımsız = açık (varsayılan)
        return aktif

    # -----------------------------------------------------------------
    # HTTP — price_service'in katmanını kullanır, yenisini yazmaz
    # -----------------------------------------------------------------
    def _getir(self, url, timeout, headers=None):
        import json as _json
        import urllib.request

        h = {"Accept": "application/json", "User-Agent": BROWSER_UA}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _json.loads(resp.read().decode("utf-8"))

    def _sagligi_isaretle(self, kaynak_id, ok, hata=None):
        h = self._health.setdefault(kaynak_id, {
            "ok": None, "last_error": None, "last_ok_ts": 0.0,
            "last_try_ts": 0.0, "fail_count": 0,
        })
        h["last_try_ts"] = time.time()
        if ok:
            h["ok"] = True
            h["fail_count"] = 0
            h["last_error"] = None
            h["last_ok_ts"] = time.time()
        else:
            h["ok"] = False
            h["fail_count"] = int(h.get("fail_count", 0)) + 1
            h["last_error"] = str(hata)[:200] if hata else "bilinmeyen hata"

    # -----------------------------------------------------------------
    # ADAPTÖRLER
    # -----------------------------------------------------------------
    def fetch_btc_trend(self):
        """Tek Binance çağrısından BTC'nin tüm trend tablosunu türetir.

        Buradaki her sayı ÖLÇÜLEBİLİR bir büyüklüktür; hiçbiri hüküm değildir.
        `sma50 < sma200` bilgisini veriyoruz ama ona "ölüm kesişimi" demiyoruz —
        modülün başındaki 1 numaralı kural bunu neden yasakladığını anlatıyor.
        """
        url = f"{self._url('btc_klines')}?symbol=BTCUSDT&interval=1d&limit={KLINE_LIMIT}"
        ham = self._getir(url, timeout=10)
        return self._klines_to_trend(ham, "BTCUSDT")

    @staticmethod
    def _klines_to_trend(ham, sembol):
        """Klines dizisini trend sözlüğüne çevirir. Ağa çıkmaz — test edilebilir."""
        if not isinstance(ham, list) or len(ham) < 2:
            raise ValueError("klines yanıtı beklenen biçimde değil")
        kapanis = []
        for mum in ham:
            try:
                kapanis.append(float(mum[4]))
            except (TypeError, ValueError, IndexError):
                continue
        if len(kapanis) < 2:
            raise ValueError("klines yanıtından kapanış fiyatı çıkarılamadı")

        son = kapanis[-1]

        def degisim(gun):
            if len(kapanis) <= gun:
                return None
            return _yuzde(son, kapanis[-1 - gun])

        # Ortalamalar yalnızca yeterli veri varsa hesaplanır. Eksik veriyle
        # kısa pencereden SMA200 uydurmak, yanlış bir sayıyı doğru gibi
        # sunmak olur.
        sma50 = round(statistics.fmean(kapanis[-50:]), 2) if len(kapanis) >= 50 else None
        sma200 = round(statistics.fmean(kapanis[-200:]), 2) if len(kapanis) >= 200 else None

        zirve = max(kapanis)
        dip = min(kapanis)

        getiriler = []
        for i in range(max(1, len(kapanis) - 30), len(kapanis)):
            o = _yuzde(kapanis[i], kapanis[i - 1])
            if o is not None:
                getiriler.append(o)
        oynaklik = round(statistics.pstdev(getiriler), 2) if len(getiriler) >= 2 else None

        # Son mumun kapanış zamanı = kaynağın kendi tazelik alanı.
        try:
            son_mum_ts = float(ham[-1][6]) / 1000.0
        except (TypeError, ValueError, IndexError):
            son_mum_ts = None

        return {
            "symbol": sembol,
            "price": round(son, 2),
            "change_7d_pct": degisim(7),
            "change_30d_pct": degisim(30),
            "change_90d_pct": degisim(90),
            "sma50": sma50,
            "sma200": sma200,
            "pct_vs_sma50": _yuzde(son, sma50) if sma50 else None,
            "pct_vs_sma200": _yuzde(son, sma200) if sma200 else None,
            "sma50_above_sma200": (None if (sma50 is None or sma200 is None)
                                   else bool(sma50 > sma200)),
            "range_low": round(dip, 2),
            "range_high": round(zirve, 2),
            "range_days": len(kapanis),
            "pct_from_high": _yuzde(son, zirve),
            "daily_volatility_pct_30d": oynaklik,
            "candle_close_ts": son_mum_ts,
            "source": "BINANCE",
        }

    def fetch_ethbtc(self):
        url = f"{self._url('btc_klines')}?symbol=ETHBTC&interval=1d&limit=95"
        ham = self._getir(url, timeout=10)
        if not isinstance(ham, list) or len(ham) < 2:
            raise ValueError("ETHBTC klines yanıtı beklenen biçimde değil")
        kapanis = [float(m[4]) for m in ham]
        son = kapanis[-1]

        def degisim(gun):
            if len(kapanis) <= gun:
                return None
            return _yuzde(son, kapanis[-1 - gun])

        try:
            son_mum_ts = float(ham[-1][6]) / 1000.0
        except (TypeError, ValueError, IndexError):
            son_mum_ts = None

        return {
            "pair": "ETH/BTC",
            "value": round(son, 6),
            "change_7d_pct": degisim(7),
            "change_30d_pct": degisim(30),
            "change_90d_pct": degisim(90),
            "candle_close_ts": son_mum_ts,
            "source": "BINANCE",
            "note": ("ETH/BTC yukselirse ETH BTC'den guclu demektir. "
                     "Bu bir yon bilgisidir, al/sat sinyali degildir."),
        }

    def fetch_fear_greed(self):
        url = f"{self._url('fear_greed')}?limit=8&format=json"
        ham = self._getir(url, timeout=10)
        return self._fng_to_dict(ham)

    @staticmethod
    def _fng_to_dict(ham):
        """alternative.me yanıtını sözlüğe çevirir. Ağa çıkmaz."""
        if not isinstance(ham, dict):
            raise ValueError("F&G yanıtı beklenen biçimde değil")
        meta = ham.get("metadata") or {}
        if meta.get("error"):
            raise ValueError(f"F&G kaynağı hata bildirdi: {meta['error']}")
        satirlar = ham.get("data") or []
        if not satirlar:
            raise ValueError("F&G yanıtı boş")

        def sayi(x):
            try:
                return int(x)
            except (TypeError, ValueError):
                return None

        bugun = satirlar[0]
        deger = sayi(bugun.get("value"))
        if deger is None:
            raise ValueError("F&G değeri sayıya çevrilemedi")

        gecmis = []
        for s in satirlar[:8]:
            d = sayi(s.get("value"))
            ts = sayi(s.get("timestamp"))
            if d is None or ts is None:
                continue
            gecmis.append({
                "date": time.strftime("%Y-%m-%d", time.gmtime(ts)),
                "value": d,
                "label": s.get("value_classification"),
            })

        onceki = gecmis[1]["value"] if len(gecmis) > 1 else None
        hafta_once = gecmis[7]["value"] if len(gecmis) > 7 else None

        return {
            "value": deger,
            # Bu etiket BİZİM hükmümüz değil, sağlayıcının kendi standardı.
            "classification": bugun.get("value_classification"),
            "change_1d": (deger - onceki) if onceki is not None else None,
            "change_7d": (deger - hafta_once) if hafta_once is not None else None,
            "history": gecmis,
            "value_ts": sayi(bugun.get("timestamp")),
            "seconds_until_update": sayi(bugun.get("time_until_update")),
            "source": "alternative.me",
            "note": ("Bu endeksin kendi metodolojisinde BTC dominansi %10 "
                     "agirlikla zaten var. F&G ile dominansi BAGIMSIZ iki "
                     "teyit gibi okuma."),
        }

    def fetch_global(self):
        """BTC dominansı + toplam piyasa değeri (CoinGecko).

        Anahtar varsa başlıkla gönderilir; taban adres değişmez. Anahtarsız
        yol çalışır ama tercih edilen yol anahtarlı olandır.
        """
        anahtar = self._coingecko_anahtari()
        headers = {"x-cg-demo-api-key": anahtar} if anahtar else None
        ham = self._getir(self._url("coingecko_global"), timeout=25, headers=headers)
        out = self._global_to_dict(ham)
        out["auth_mode"] = "demo_key" if anahtar else "keyless"
        return out

    @staticmethod
    def _global_to_dict(ham):
        """CoinGecko /global yanıtını sözlüğe çevirir. Ağa çıkmaz."""
        if not isinstance(ham, dict) or "data" not in ham:
            raise ValueError("CoinGecko /global yanıtı beklenen biçimde değil")
        d = ham["data"] or {}
        yuzdeler = d.get("market_cap_percentage") or {}
        mcap = (d.get("total_market_cap") or {}).get("usd")
        hacim = (d.get("total_volume") or {}).get("usd")
        btc_d = yuzdeler.get("btc")
        if mcap is None or btc_d is None:
            raise ValueError("CoinGecko yanıtında dominans veya mcap yok")

        btc_d = round(float(btc_d), 2)
        mcap = float(mcap)
        # BTC DIŞI piyasa değeri: ham toplam mcap büyük ölçüde BTC+ETH'in
        # yeniden ifadesidir ve kaynaklar arası en çok burada uyuşmazlık var
        # (%5.6 ölçüldü). Bu türetme, aynı çağrıdan gerçekten AYRI bir bilgi
        # çıkarır: altcoinlerin toplam büyüklüğü.
        btc_disi = mcap * (1.0 - btc_d / 100.0)

        return {
            "btc_dominance_pct": btc_d,
            "eth_dominance_pct": (round(float(yuzdeler["eth"]), 2)
                                  if yuzdeler.get("eth") is not None else None),
            "total_market_cap_usd": round(mcap, 0),
            "market_cap_excl_btc_usd": round(btc_disi, 0),
            "total_volume_24h_usd": round(float(hacim), 0) if hacim else None,
            "market_cap_change_24h_pct": (
                round(float(d["market_cap_change_percentage_24h_usd"]), 2)
                if d.get("market_cap_change_percentage_24h_usd") is not None else None),
            "coins_covered": d.get("active_cryptocurrencies"),
            "value_ts": d.get("updated_at"),
            # Kaynak adı BİLEREK her kayda yazılıyor. Dominans kaynağa göre
            # 2.81 puan değişiyor; kaynağı unutmuş bir geçmiş, sahte sinyal
            # üretir.
            "source": "CoinGecko",
            "convention_note": ("Dominans, kaynagin 'toplam piyasa' tanimina "
                                "baglidir. Ayni anda olculdu: CoinGecko 58.84, "
                                "Coinpaprika 56.52, Coinlore 59.33. Bu deger "
                                "YALNIZCA CoinGecko konvansiyonudur; baska bir "
                                "yerde gordugun sayiyla birebir tutmayabilir."),
        }

    # -----------------------------------------------------------------
    # GENİŞLİK — sıfır ek çağrı
    # -----------------------------------------------------------------
    def fetch_breadth(self):
        """Piyasa genişliğini mevcut fiyat motorundan türetir.

        Ağa ÇIKMAZ. `price_service` Binance'in tüm 24s ticker'ını zaten
        indiriyor; biz o veriyi okuyoruz. Binance kademesi kapalıysa veri
        yoktur ve burada hata yükselir — uydurmak yerine yokluk bildirmek
        doğru davranıştır.
        """
        if self.price_engine is None:
            raise ValueError("fiyat motoru yok")
        ham = self.price_engine.get_breadth_input()
        return self._breadth_to_dict(ham)

    @staticmethod
    def _breadth_to_dict(ham):
        """[{symbol, change_pct, quote_volume}] → genişlik özeti. Ağa çıkmaz."""
        if not ham:
            raise ValueError("genişlik için Binance verisi yok")

        likit = [r for r in ham
                 if (r.get("quote_volume") or 0) >= GENISLIK_MIN_HACIM_USDT]
        if len(likit) < 20:
            # 20'nin altında örnekle "piyasanın %X'i artıda" demek yanıltıcı.
            raise ValueError(f"likit çift sayısı yetersiz ({len(likit)})")

        degisimler = [float(r["change_pct"]) for r in likit]
        btc = next((float(r["change_pct"]) for r in ham
                    if r.get("symbol") == "BTCUSDT"), None)

        artida = sum(1 for c in degisimler if c > 0)
        toplam = len(degisimler)
        btc_ustu = (sum(1 for c in degisimler if btc is not None and c > btc)
                    if btc is not None else None)

        return {
            "liquid_pairs": toplam,
            "min_quote_volume_usd": GENISLIK_MIN_HACIM_USDT,
            "advancing": artida,
            "declining": toplam - artida,
            "advancing_pct": round(100.0 * artida / toplam, 1),
            "median_change_24h_pct": round(statistics.median(degisimler), 2),
            "mean_change_24h_pct": round(statistics.fmean(degisimler), 2),
            "btc_change_24h_pct": round(btc, 2) if btc is not None else None,
            "outperforming_btc_pct": (round(100.0 * btc_ustu / toplam, 1)
                                      if btc_ustu is not None else None),
            "source": "BINANCE (mevcut ticker verisi, ek cagri yok)",
            "note": ("Likit = 24s hacmi 1M USDT ustu USDT cifti. Bu, paranin "
                     "BTC'de mi altcoinlerde mi oldugunu dominanstan daha "
                     "taze gosterir."),
        }

    # -----------------------------------------------------------------
    # TOPLAMA
    # -----------------------------------------------------------------
    def _cekiciler(self):
        return {
            "btc_trend": self.fetch_btc_trend,
            "ethbtc": self.fetch_ethbtc,
            "breadth": self.fetch_breadth,
            "fear_greed": self.fetch_fear_greed,
            "global": self.fetch_global,
        }

    def refresh_due(self, force=False):
        """Zamanı gelen kaynakları yeniler. Bir kaynağın patlaması diğerlerini
        etkilemez — piyasa verisi kısmi de olsa değerlidir."""
        simdi = time.time()
        aktif = set(self.aktif_kaynaklar())
        yenilenen = []

        for kaynak_id, cekici in self._cekiciler().items():
            if kaynak_id not in aktif:
                continue
            # Genişliğin kendi TTL'i yok: kaynağı zaten bellekte, her turda
            # yeniden türetmek bedava ve en tazesi iyisi.
            ttl = KAYNAK_TTL.get(kaynak_id, 0.0)
            onceki = self._cache.get(kaynak_id)
            if not force and onceki and (simdi - onceki["fetched_at"]) < ttl:
                continue
            try:
                veri = cekici()
                with self.lock:
                    self._cache[kaynak_id] = {"data": veri, "fetched_at": time.time()}
                self._sagligi_isaretle(kaynak_id, True)
                yenilenen.append(kaynak_id)
            except Exception as e:
                self._sagligi_isaretle(kaynak_id, False, e)
                # Eski değer SİLİNMEZ; bayat veri, veri yokluğundan iyidir —
                # yaşı bildirildiği sürece.
                logger.debug("Piyasa kaynağı '%s' yenilenemedi: %s", kaynak_id, e)

        self._son_dongu_ts = simdi
        if yenilenen:
            self._arsivle()
        return yenilenen

    def _arsivle(self):
        """Günlük piyasa fotoğrafını arşive yazar.

        Arşiv modülü bilerek GEÇ import ediliyor: piyasa servisi arşiv
        olmadan da çalışabilmeli ve testler bu bağı kolayca kesebilmeli.
        Yazma başarısız olursa hiçbir şey durmaz — kaybedilen tek şey bir
        günlük geçmiştir.

        Aynı gün tekrar yazmak sorun değil: `write_market_snapshot` upsert
        yapıyor ve o günün satırı günün SON gözlemine yakınsıyor.
        """
        try:
            import archive
            archive.write_market_snapshot(self.get_snapshot())
        except Exception as e:
            logger.debug("Piyasa fotoğrafı arşivlenemedi: %s", e)

    def get_snapshot(self):
        """Modele ve arayüze gidecek tek sözlük. AĞA ÇIKMAZ, önbellekten okur.

        Her blok kendi yaşını taşır. Çok eskiyen blok hiç dönmez — bayat
        sayıyı sessizce vermektense yokluğu bildirmek doğrudur.
        """
        simdi = time.time()
        with self.lock:
            kopya = {k: dict(v) for k, v in self._cache.items()}

        cikti = {}
        atilan = []
        for kaynak_id, kayit in kopya.items():
            yas = simdi - kayit["fetched_at"]
            tazelik = _tazelik(kaynak_id, yas)
            if tazelik is None:
                atilan.append(kaynak_id)
                continue
            blok = dict(kayit["data"])
            blok["fetched_at"] = round(kayit["fetched_at"], 0)
            blok["age_seconds"] = int(yas)
            blok["age_human"] = _yas_metni(yas)
            blok["freshness"] = tazelik
            cikti[kaynak_id] = blok

        return {
            "available": bool(cikti),
            "blocks": cikti,
            "dropped_as_too_old": atilan,
            "generated_at": round(simdi, 0),
        }

    def describe_sources(self):
        """Ayarlar/durum ekranı için kaynak listesi — sağlıkla birlikte."""
        aktif = set(self.aktif_kaynaklar())
        anahtar_var = bool(self._coingecko_anahtari())
        out = []
        for sid in MARKET_SOURCE_IDS:
            h = self._health.get(sid) or {}
            denendi = bool(h.get("last_try_ts"))
            kayit = self._cache.get(sid)
            satir = {
                "id": sid,
                "label": MARKET_SOURCE_LABELS.get(sid, sid),
                "enabled": sid in aktif,
                "healthy": h.get("ok") if denendi else None,
                "fail_count": int(h.get("fail_count", 0)),
                "last_error": h.get("last_error"),
                "last_ok_ts": h.get("last_ok_ts") or 0.0,
                "has_data": bool(kayit),
                "age_seconds": (int(time.time() - kayit["fetched_at"])
                                if kayit else None),
                "needs_network": sid != "breadth",
            }
            if sid == "global":
                # Anahtarsız çalışmak bir hata değil ama GÖRÜNÜR olmalı:
                # kullanıcı hangi kalitede veri aldığını bilmelidir.
                satir["auth_mode"] = "demo_key" if anahtar_var else "keyless"
                satir["auth_is_preferred"] = anahtar_var
                satir["auth_hint"] = (
                    "Ucretsiz CoinGecko demo anahtari tanimli; dakikada 100 cagri."
                    if anahtar_var else
                    "Anahtarsiz yedek modda: IP basina dakikada 5-15 cagri. "
                    "Ucretsiz demo anahtari onerilir."
                )
            out.append(satir)
        return out


def _yas_metni(saniye):
    """Yaşı insan diline çevirir — arayüzde ve modelin metninde kullanılır."""
    s = int(max(0, saniye))
    if s < 90:
        return f"{s} saniye"
    if s < 5400:
        return f"{s // 60} dakika"
    if s < 172800:
        return f"{s // 3600} saat"
    return f"{s // 86400} gun"


# Uygulama genelinde tek örnek — price_service'teki desenin aynısı.
market_service = MarketDataService()
