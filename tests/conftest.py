r"""
CoinTakip — Test Altyapısı ve Ortak Fixture'lar (FAZ C2)

╔══════════════════════════════════════════════════════════════════════════╗
║  GÜVENLİK GARANTİSİ                                                      ║
║                                                                          ║
║  Buradaki `izole_veri` fixture'ı autouse=True'dur — yani HER test         ║
║  otomatik olarak geçici bir dizine yönlendirilir. Hiçbir test             ║
║  D:\Claude_Projects\CoinTakip\data\portfolio.json dosyasına dokunamaz.    ║
║  Bir test fixture istemeyi unutsa bile gerçek veri korunur.               ║
║  (Çalışma Kuralı #2: 73 işlem kaydını koru.)                             ║
╚══════════════════════════════════════════════════════════════════════════╝

Ayrıca tüm harici ağ çağrıları kapatılır (Çalışma Kuralı #1: sıfır kota israfı):
  - Fiyat motorunun arka plan thread'i başlatılmaz
  - Fiyatlar sabit test verisinden gelir
  - Sparkline üretimi Binance'e istek atmaz
  - Gemini API'ye çağrı yapan test YOKTUR
"""

import os
import sys
import json
import logging

import pytest

# app/ dizinini import yoluna ekle — proje düz import kullanıyor
# (uvicorn cwd=app ile çalıştığı için `from data_manager import ...` şeklinde)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(PROJECT_ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import data_manager                      # noqa: E402
import price_service as price_module     # noqa: E402
import market_service as market_module   # noqa: E402
import trade_sync as trade_sync_module   # noqa: E402


# Sabit test fiyatları — ağ erişimi olmadan deterministik sonuç verir
SAHTE_FIYATLAR = {
    "BTCUSDT":  {"price": 100000.0, "open_price": 98000.0, "change_pct": 2.04, "source": "TEST"},
    "ETHUSDT":  {"price": 2000.0,   "open_price": 2100.0,  "change_pct": -4.76, "source": "TEST"},
    "SOLUSDT":  {"price": 150.0,    "open_price": 150.0,   "change_pct": 0.0,   "source": "TEST"},
    "XAUTUSDT": {"price": 4000.0,   "open_price": 4000.0,  "change_pct": 0.0,   "source": "TEST"},
    # Nano fiyatlı DEX tokeni — CPL edge case'ini temsil eder
    "CPLUSDT":  {"price": 2.0e-09,  "open_price": 2.0e-09, "change_pct": 0.0,
                 "source": "DEX (BSC Pancakeswap)", "is_dex": True},
}

SAHTE_SPARKLINE = {
    "points": [90.0, 92.0, 95.0, 93.0, 97.0, 99.0, 100.0],
    "change_7d_pct": 11.11,
    "min_price": 90.0,
    "max_price": 100.0,
    "updated_at": 0,
}


# ===========================================================================
# SERT BEKÇİ: TEST OTURUMU GERÇEK data/ KLASÖRÜNE YAZAMAZ
#
# `izole_veri` yolları geçici dizine çeviriyor ve bugüne kadar yeterli
# sayıldı. Yetmedi: 5 Eylül 2026'da gerçek `data/settings.json` bir test
# oturumu sırasında VARSAYILAN AYARLARLA ÜZERİNE YAZILDI. Kullanıcının
# Gemini anahtarı, cüzdan bağlantıları, şifreli borsa anahtarları ve PIN'i
# kayboldu; hiçbiri yedeklenmiyordu çünkü uygulama yalnızca `portfolio.json`
# yedekliyor.
#
# Ders şu: yol yönlendirmesi bir SÖZLEŞMEDİR ve sözleşmeler tutulmayabilir.
# Bir arka plan thread'i, geç import edilen bir modül, ya da monkeypatch
# geri alındıktan sonra çalışan herhangi bir kod o sözleşmenin dışına
# çıkabilir. Bu yüzden artık yönlendirmeye ek olarak İŞLETİM SİSTEMİ
# SEVİYESİNDE bir duvar var: test oturumu boyunca gerçek `data/` altına
# açılan her yazma girişimi ENGELLENİR ve testi kırar.
#
# Yönlendirme "yanlışlıkla yazma" ihtimalini azaltır; bu duvar onu imkânsız
# kılar. Kullanıcının gerçek parayla ilgili verisi söz konusu olduğunda
# aradaki fark önemlidir.
# ===========================================================================
GERCEK_DATA_DIZINI = os.path.join(PROJECT_ROOT, "data")

# Log dosyası hariç: `log_config` gerçek log dosyasını uygulama açılışında
# ele geçiriyor ve bir günlük kaydı veri değildir.
_YAZMAYA_IZINLI = (os.path.join(GERCEK_DATA_DIZINI, "logs"),)


def _gercek_veri_yolu_mu(yol):
    try:
        tam = os.path.abspath(os.fspath(yol))
    except Exception:
        return False
    if not tam.startswith(os.path.abspath(GERCEK_DATA_DIZINI)):
        return False
    return not any(tam.startswith(os.path.abspath(i)) for i in _YAZMAYA_IZINLI)


@pytest.fixture(autouse=True, scope="session")
def gercek_veriye_yazma_duvari():
    """Oturum boyunca gerçek `data/` altına yazmayı fiziksel olarak engeller."""
    import builtins

    ilk_open, ilk_replace, ilk_remove = builtins.open, os.replace, os.remove

    def _patla(islem, yol):
        raise AssertionError(
            f"\n\nTEST GERÇEK KULLANICI VERİSİNE YAZMAYA ÇALIŞTI!\n"
            f"  işlem : {islem}\n"
            f"  hedef : {yol}\n\n"
            "Bu kesinlikle yasaktır. Muhtemel sebep: bir arka plan thread'i "
            "ya da\n`izole_veri` yönlendirmesinin dışında kalan bir kod yolu.\n"
            "Bir kez gerçekten oldu ve kullanıcının API anahtarlarıyla PIN'i "
            "silindi.\n")

    def korumali_open(dosya, kip="r", *a, **k):
        if any(c in kip for c in "wxa+") and _gercek_veri_yolu_mu(dosya):
            _patla(f"open(mode={kip!r})", dosya)
        return ilk_open(dosya, kip, *a, **k)

    def korumali_replace(src, dst, *a, **k):
        if _gercek_veri_yolu_mu(dst):
            _patla("os.replace", dst)
        return ilk_replace(src, dst, *a, **k)

    def korumali_remove(yol, *a, **k):
        if _gercek_veri_yolu_mu(yol):
            _patla("os.remove", yol)
        return ilk_remove(yol, *a, **k)

    builtins.open = korumali_open
    os.replace = korumali_replace
    os.remove = korumali_remove
    try:
        yield
    finally:
        builtins.open, os.replace, os.remove = ilk_open, ilk_replace, ilk_remove


@pytest.fixture(autouse=True)
def izole_veri(tmp_path, monkeypatch):
    """
    HER teste otomatik uygulanır. Veri yollarını geçici dizine çevirir ve
    tüm ağ çağrılarını devre dışı bırakır.
    """
    veri_dizini = tmp_path / "data"
    yedek_dizini = veri_dizini / "backups"
    yedek_dizini.mkdir(parents=True, exist_ok=True)

    # --- Log dosyasını koru ---
    # log_config gerçek data/logs/cointakip.log dosyasına yazar. Test koşuları
    # kullanıcının gerçek log dosyasını gürültüyle doldurmamalı; kayıtlar
    # pytest'in kendi yakalayıcısında kalır (hata ayıklarken -o log_cli=true ile görülür).
    kok_logger = logging.getLogger("cointakip")
    dosya_handlerlari = [h for h in kok_logger.handlers
                         if isinstance(h, logging.FileHandler)]
    for h in dosya_handlerlari:
        kok_logger.removeHandler(h)

    # --- Veri yollarını izole et ---
    # Fonksiyonlar bu sabitleri çağrı anında global olarak okuduğu için
    # modül seviyesinde monkeypatch etmek yeterlidir.
    monkeypatch.setattr(data_manager, "DATA_DIR", str(veri_dizini))
    monkeypatch.setattr(data_manager, "DATA_FILE", str(veri_dizini / "portfolio.json"))
    monkeypatch.setattr(data_manager, "BACKUP_DIR", str(yedek_dizini))
    monkeypatch.setattr(data_manager, "SETTINGS_FILE", str(veri_dizini / "settings.json"))

    # --- Ağ erişimini kes ---
    motor = price_module.price_service
    monkeypatch.setattr(motor, "prices", dict(SAHTE_FIYATLAR))
    monkeypatch.setattr(motor, "last_update_ts", 1_700_000_000.0)
    monkeypatch.setattr(motor, "start_background_updater", lambda: None)
    monkeypatch.setattr(motor, "update_all_prices", lambda: None)
    # calculate_portfolio_metrics her pozisyon için sparkline ister —
    # stub'lanmazsa her test Binance'e HTTP isteği atardı.
    monkeypatch.setattr(motor, "get_sparkline_7d",
                        lambda symbol, live_price=0.0, change_24h=0.0: dict(SAHTE_SPARKLINE))
    # Zincir üstü arama varsayılan olarak kapalı. Kendi sahte verisini isteyen
    # test bunu tekrar monkeypatch ederek ezer; ezmeyen bir test yanlışlıkla
    # DexScreener'a çıkamaz.
    monkeypatch.setattr(motor, "fetch_dex_screener", lambda query: None)
    # Kaynak yapılandırması testler arasında sızmasın (10 sn'lik önbellek var).
    motor._config_cache = None
    motor._config_ts = 0.0
    motor._watchlist_cache = []
    motor._watchlist_ts = 0.0
    motor._dex_last_fetch = {}

    # --- FAZ M1: piyasa verisi servisi de susturulur ---
    #
    # `main.py` gövdesi import anında `market_service.start_background_updater()`
    # çağırıyor. Bu döngü 8 saniye bekleyip Binance, alternative.me ve
    # CoinGecko'ya GERÇEKTEN çıkıyor. Fiyat motoru için kurulan bekçi bunu
    # yakalamıyordu çünkü ayrı bir nesne — yani aynı hata ikinci bir kapıdan
    # geri geliyordu.
    piyasa = market_module.market_service
    monkeypatch.setattr(piyasa, "start_background_updater", lambda: None)
    monkeypatch.setattr(piyasa, "refresh_due", lambda force=False: [])
    monkeypatch.setattr(piyasa, "_arsivle", lambda: None)
    # Önbellek testler arasında sızmasın.
    piyasa._cache = {}
    piyasa._health = {}

    # --- FAZ F7: borsa işlem yakalama da susturulur ---
    #
    # Bu servis diğer ikisinden daha tehlikeli: İMZALI çağrı yapıyor, yani
    # susturulmazsa test oturumu kullanıcının gerçek API anahtarıyla gerçek
    # Binance hesabına bağlanırdı. Yol yönlendirmesi burada yetmez çünkü
    # anahtar diskteki dosyadan değil kasadan geliyor.
    esitleyici = trade_sync_module.trade_sync
    monkeypatch.setattr(esitleyici, "start_background_updater", lambda: None)
    monkeypatch.setattr(
        esitleyici, "scan",
        lambda location=None, full=False: {"ok": False, "skipped": "test"})
    esitleyici._son_rapor = {}

    yield veri_dizini

    # Log handler'larını geri tak (aynı oturumda uygulama çalıştırılırsa diye)
    for h in dosya_handlerlari:
        kok_logger.addHandler(h)


# ===========================================================================
# BEKÇİ: FİYAT MOTORUNUN ARKA PLAN THREAD'İ TESTLERDE ÇALIŞMAMALI
#
# `main.py`'nin gövdesi import anında `price_service.start_background_updater()`
# çağırır. Bu fixture'ların dışında (örneğin bir test modülü `main`'i modül
# seviyesinde import ederse, yani TOPLAMA anında) gerçekleşirse thread gerçekten
# başlar ve tüm oturum boyunca 4 saniyede bir AĞA çıkar.
#
# Bu bir kez oldu ve üç ayrı zarar verdi:
#   1. Veri düzeltmeleri gerçek `data/portfolio.json` üzerinde koşabilirdi.
#   2. README'nin "testler ağa dokunmaz" sözü sessizce bozuldu.
#   3. Thread `price_service.prices`'ı arka planda değiştirdiği için testler
#      seyrek ve TEKRAR ÜRETİLEMEZ şekilde kırıldı. Teşhisi zor olan buydu:
#      tam takım koşumlarının yaklaşık beşte birinde tek bir test düşüyordu.
#
# Sebebi düzeltmek yetmez; aynı hata sessizce geri gelebilir. Bu yüzden oturum
# sonunda açıkça denetlenir ve takım KIRILIR.
# ===========================================================================
def pytest_sessionfinish(session, exitstatus):
    import threading

    # FAZ M1 — Bekçi artık İKİ motoru birden denetliyor.
    #
    # Piyasa verisi servisi eklendiğinde bu tam olarak yaşandı: fiyat motoru
    # için kurulmuş bekçi, `main` import edildiğinde başlayan PİYASA thread'ini
    # görmüyordu çünkü o ayrı bir nesne. Aynı hata ikinci bir kapıdan sessizce
    # geri döndü. Bir daha dönmesin diye denetim listeye çevrildi: yeni bir
    # arka plan servisi eklenirse buraya da eklenmelidir.
    motorlar = [
        ("Fiyat motoru", price_module.price_service),
        ("Piyasa verisi servisi", market_module.market_service),
        ("Borsa işlem yakalama", trade_sync_module.trade_sync),
    ]
    calisanlar = [(ad, m) for ad, m in motorlar if getattr(m, "is_running", False)]
    if not calisanlar:
        return

    for _, m in calisanlar:
        m.is_running = False          # döngüyü durdur, sonraki koşumu kurtar
    canli = [t.name for t in threading.enumerate()
             if t is not threading.main_thread() and t.is_alive()]
    session.exitstatus = 1
    print(
        "\n\nHATA: Şu arka plan thread'leri test oturumu boyunca ÇALIŞTI: "
        + ", ".join(ad for ad, _ in calisanlar) + "\n"
        "Bu, testlerin ağa çıktığı anlamına gelir; ayrıca fiyatlar/piyasa "
        "verisi arka planda\ndeğiştiği için kararsız (flaky) test üretir.\n"
        f"Canlı thread'ler: {canli or 'yok'}\n"
        "Muhtemel sebep: bir test modülü `main`'i MODÜL SEVİYESİNDE import "
        "ediyor.\n"
        "`main` yalnızca fixture içinden import edilmelidir "
        "(bkz. tests/test_packaging.py).\n",
        file=sys.stderr,
    )


@pytest.fixture
def ornek_portfoy():
    """
    Gerçek veri şemasını yansıtan küçük bir portföy.

    Bilinçli olarak şunları içerir:
      - Aynı coin/borsa çiftinde İKİ lot (konsolidasyon ve FIFO testi için)
      - qty=0.0 olan Aktif işlem (gerçek verideki id 35/41 edge case'i)
      - Nano fiyatlı DEX tokeni (CPL edge case'i)
    """
    return {
        "wallets": {
            "usdt_cash": 1000.0,
            "exchange_cash": {"BINANCE": 800.0, "MEXC": 200.0, "GATE.IO": 0.0, "DEX": 0.0},
            "futures_balance": 0.0,
            "margin_balance": 0.0,
        },
        "settings": {"currency": "USD", "default_exchange": "BINANCE"},
        "transactions": [
            # BTC — iki ayrı lot, FIFO için farklı maliyetler (eski lot önce)
            {"id": 1, "date": "2026-01-10", "coin": "BTCUSDT", "exchange": "BINANCE",
             "qty": 0.01, "cost": 80000.0, "status": "Aktif", "notes": "", "category": "Majör / L1"},
            {"id": 2, "date": "2026-02-15", "coin": "BTCUSDT", "exchange": "BINANCE",
             "qty": 0.01, "cost": 90000.0, "status": "Aktif", "notes": "", "category": "Majör / L1"},
            # ETH — zararda tek lot
            {"id": 3, "date": "2026-03-01", "coin": "ETHUSDT", "exchange": "BINANCE",
             "qty": 1.0, "cost": 2500.0, "status": "Aktif", "notes": "", "category": "Majör / L1"},
            # Edge case: qty 0.0 ama Aktif — sıfıra bölme riski
            {"id": 4, "date": "2026-03-05", "coin": "SOLUSDT", "exchange": "BINANCE",
             "qty": 0.0, "cost": 200.0, "status": "Aktif", "notes": "", "category": "Majör / L1"},
            # Edge case: nano fiyat
            {"id": 5, "date": "2026-03-10", "coin": "CPLUSDT", "exchange": "DEX",
             "qty": 2_700_000_000.0, "cost": 1.0e-08, "status": "Aktif", "notes": "", "category": "Meme / DEX"},
            # Kapanmış işlem — gerçekleşmiş K/Z testi için
            {"id": 6, "date": "2026-01-05", "coin": "XAUTUSDT", "exchange": "MEXC",
             "qty": 0.1, "cost": 3000.0, "status": "Kapandı / İzleme",
             "exit_price": 3500.0, "exit_date": "2026-02-20", "exit_value": 350.0,
             "realized_pnl_usd": 48.0, "fee_amount": 2.0, "fee_asset": "USDT", "fee_usd": 2.0,
             "cost_method": "Konsolide Ortalama", "notes": "", "category": "Emtia / Altın"},
        ],
        "next_tx_id": 7,
        "targets": {},
    }


@pytest.fixture
def kayitli_portfoy(ornek_portfoy):
    """Örnek portföyü izole diske yazar ve veriyi döndürür."""
    data_manager.save_portfolio(ornek_portfoy)
    return ornek_portfoy


@pytest.fixture
def client(kayitli_portfoy):
    """
    FastAPI TestClient. main.py import edilmeden ÖNCE yollar ve fiyat motoru
    zaten izole edilmiştir (izole_veri autouse olduğu için).
    """
    from fastapi.testclient import TestClient
    import main

    # main.py bu ikisini değerle import ediyor (`from data_manager import DATA_FILE`),
    # bu yüzden ayrıca yönlendirilmeleri gerekir.
    import importlib
    monkey = pytest.MonkeyPatch()
    monkey.setattr(main, "DATA_FILE", data_manager.DATA_FILE)
    monkey.setattr(main, "BACKUP_DIR", data_manager.BACKUP_DIR)

    with TestClient(main.app) as c:
        yield c

    monkey.undo()
    importlib.invalidate_caches()
