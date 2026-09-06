"""
CoinTakip — Arşiv Deposu (FAZ F2)
=====================================================================

NEDEN VAR
---------
Borsalar geçmişi süresiz saklamıyor ve pencereleri KAYIYOR:

    Binance  /api/v3/myTrades      → pratikte ~2 yıl tavanı
    Binance  para yatırma/çekme    → sorgu başına 90 gün
    Binance  accountSnapshot       → yalnızca 30 gün geriye
    MEXC     /api/v3/myTrades      → 1 ay (web dışa aktarımı ~540 gün)

Yani bugün alınmayan veri yarın alınamıyor. Bu modülün tek işi şu:
**bir kez gördüğümüzü bir daha bırakmamak.** Uygulama her çalıştığında
portföyün o anki hâlini kaydeder; böylece borsanın sildiği geçmiş bizde
kalır ve zamanla gerçek bir net varlık eğrisi oluşur — mevcut sistemin
geriye dönük üretemediği bir şey.

NEDEN SQLITE, DEFTER NEDEN JSON KALDI
-------------------------------------
Bilinçli bir ayrım:

  Defter (portfolio.json) → JSON kalır. İnsan okuyabilir, kullanıcının
      malıdır, README'deki "düz JSON dosyalarında saklanır" sözü bozulmaz.
      Zaten her istekte baştan sona belleğe okunuyor.

  Arşiv (archive.db) → SQLite. Yılda kabaca binlerce satır büyür; bunu
      portfolio.json'a koymak her istekte okunan dosyayı şişirirdi.
      "3 Mart'ta net varlığım neydi" sorgusu SQL'de doğaldır, JSON'da
      elle tarama demektir. SQLite Python'un içinde gelir — yeni bağımlılık yok.

TASARIM KURALLARI
-----------------
1. **Arşiv ASLA uygulamayı düşürmez.** Her giriş noktası kendi hatasını
   yutar ve loglar. Fiyat takibi, defter ve KPI'lar arşiv olmadan da
   çalışmaya devam eder. Arşiv bir konfor katmanıdır, kritik yol değildir.
2. **Gün başına tek satır.** Aynı günün kaydı, gün içinde daha yeni bir
   gözlemle tazelenir; böylece bir günün değeri o günün SON gözlemidir.
3. **Fiyatsız fotoğraf yazılmaz.** Uygulama henüz fiyat çekmemişken kayıt
   almak, portföyü "her şey kaynaksız" hâlde dondurup eğriyi bozardı.
4. **Boşluklar gizlenmez.** Uygulama kapalıyken kayıt oluşmaz; bu bir hata
   değil ama kullanıcıya AÇIKÇA söylenmeli. Sessizce eksik veriyle devam
   etmek, hiç veri olmamasından kötüdür.
"""

import os
import json
import sqlite3
import time
from datetime import datetime, timedelta

from log_config import get_logger

logger = get_logger("archive")

ARCHIVE_FILENAME = "archive.db"

# Aynı günün kaydı bu süre geçtikten sonra tazelenir (saniye).
# Amaç: bir günün satırı o günün son gözlemine yakınsasın.
SNAPSHOT_REFRESH_TTL = 3600.0

# 2 — `ai_reports` tablosu eklendi. Şema `CREATE TABLE IF NOT EXISTS` ile
# kurulduğu için mevcut arşivler açıldıklarında kendiliğinden tamamlanır;
# göç adımı gerekmiyor, eski satırlar da olduğu gibi kalıyor.
# 3 — `market_snapshots` tablosu eklendi (FAZ M1). Aynı yöntem.
# 4 — `exchange_events`, `exchange_sync_state`, `exchange_balance_state`
#     eklendi (FAZ F7 — borsa işlemlerinin yakalanması). Aynı yöntem.
SCHEMA_VERSION = 4


def archive_path():
    """
    Arşiv dosyasının yolu — ÇAĞRI ANINDA hesaplanır.

    data_manager.DATA_DIR modül seviyesinde monkeypatch edilebiliyor
    (testler geçici dizine yönlendiriyor). İçe aktarma anında sabitlenirse
    testler gerçek arşive yazardı.
    """
    from data_manager import DATA_DIR
    return os.path.join(DATA_DIR, ARCHIVE_FILENAME)


def _connect():
    """
    Her işlem için yeni bağlantı açar.

    Bağlantıyı paylaşmıyoruz: SQLite bağlantıları thread'ler arasında
    taşınamaz ve fiyat motoru arka planda kendi thread'inde dönüyor.
    Açıp kapamak bu ölçekte ölçülebilir bir maliyet değil.
    """
    from data_manager import ensure_data_dir
    ensure_data_dir()
    conn = sqlite3.connect(archive_path(), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_archive():
    """Şemayı oluşturur (idempotent). Hata hâlinde False döner, patlamaz."""
    try:
        with _connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );

                -- Gün başına bir satır. Portföyün o günkü toplam hâli.
                CREATE TABLE IF NOT EXISTS snapshots (
                    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                    taken_date            TEXT NOT NULL UNIQUE,   -- YYYY-MM-DD
                    taken_at              TEXT NOT NULL,          -- ISO8601
                    taken_ts              REAL NOT NULL,
                    source                TEXT NOT NULL DEFAULT 'auto',
                    total_equity_usd      REAL,
                    spot_value_usd        REAL,
                    spot_invested_usd     REAL,
                    cash_usd              REAL,
                    futures_balance_usd   REAL,
                    margin_balance_usd    REAL,
                    hedge_unrealized_usd  REAL,
                    realized_pnl_usd      REAL,
                    position_count        INTEGER,
                    no_source_count       INTEGER,
                    no_source_value_usd   REAL
                );

                -- Fotoğraf başına pozisyon detayı. Fiyatı da saklıyoruz:
                -- delist olmuş bir coinin geçmiş fiyatını hiçbir API geri vermez.
                CREATE TABLE IF NOT EXISTS snapshot_positions (
                    snapshot_id   INTEGER NOT NULL,
                    pos_key       TEXT NOT NULL,
                    symbol        TEXT,
                    location      TEXT,
                    qty           REAL,
                    avg_cost      REAL,
                    price         REAL,
                    value_usd     REAL,
                    pnl_usd       REAL,
                    no_source     INTEGER DEFAULT 0,
                    price_source  TEXT,
                    PRIMARY KEY (snapshot_id, pos_key),
                    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
                );

                -- Konum bazlı kırılım. FAZ F3'te borsa API'sinden okunan
                -- gerçek bakiyeler de buraya yazılacak (mutabakat için).
                CREATE TABLE IF NOT EXISTS snapshot_locations (
                    snapshot_id     INTEGER NOT NULL,
                    location        TEXT NOT NULL,
                    spot_value_usd  REAL,
                    cash_usd        REAL,
                    total_usd       REAL,
                    PRIMARY KEY (snapshot_id, location),
                    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
                );

                -- YZ analiz raporları.
                --
                -- Eskiden raporlar YALNIZCA tarayıcı belleğinde duruyordu
                -- (Alpine durumu); sayfa yenilenince yok oluyorlardı. Bunun iki
                -- sonucu vardı: kullanıcı geçen hafta ne önerildiğini geri
                -- okuyamıyordu ve modelin kendi geçmişinden hiç haberi olmuyordu.
                -- Gerçek örnek: model üst üste günlerde "BTC'nin %25'ini sat"
                -- dedi; kullanıcı 24 Ağustos'ta bunu zaten yapmıştı ve deftere
                -- "YZ Önerisi" diye not düşmüştü. Model bunu göremediği için
                -- aynı tavsiyeyi tekrarlayıp durdu.
                --
                -- `portfolio_digest` o anki kasanın küçük bir özeti: bir sonraki
                -- analizde "o günden bu yana ne değişti" sorusu buradan
                -- yanıtlanıyor, ham geçmişi modele yollamadan.
                CREATE TABLE IF NOT EXISTS ai_reports (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at        TEXT NOT NULL,          -- ISO8601
                    created_ts        REAL NOT NULL,
                    mode              TEXT NOT NULL,
                    source            TEXT,                   -- GEMINI_AI / LOCAL_EXPERT_ENGINE
                    model_name        TEXT,
                    custom_question   TEXT,
                    report_markdown   TEXT NOT NULL,
                    portfolio_digest  TEXT                    -- JSON
                );

                -- FAZ M1 — Günlük piyasa fotoğrafı.
                --
                -- NEDEN ARŞİVLENİYOR: BTC fiyat geçmişini ve Fear & Greed
                -- geçmişini kaynaklardan her zaman geri alabiliriz. Ama BTC
                -- DOMİNANS geçmişini ücretsiz hiçbir uç geriye dönük vermiyor.
                -- Bugün yazmazsak aradaki aylar KALICI olarak kaybolur.
                -- Aynı gerekçe `snapshot_positions.price` için de kurulmuştu:
                -- delist olmuş bir coinin geçmiş fiyatını hiçbir API geri
                -- vermez, o yüzden gördüğümüz anda saklarız.
                --
                -- `dominance_source` alanı ZORUNLU bir disiplin: dominans
                -- kaynağa göre 2.81 puan değişiyor (CoinGecko 58.84,
                -- Coinpaprika 56.52, Coinlore 59.33 — aynı anda ölçüldü).
                -- Kaynağı unutmuş bir geçmiş, kaynak değiştiğinde "dominans
                -- bir gecede 3 puan atladı" diye SAHTE bir sinyal üretir ve
                -- yapay zekâ bunun üzerine tavsiye kurar.
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    taken_date            TEXT PRIMARY KEY,       -- YYYY-MM-DD
                    taken_at              TEXT NOT NULL,          -- ISO8601
                    taken_ts              REAL NOT NULL,
                    btc_price_usd         REAL,
                    btc_change_7d_pct     REAL,
                    btc_change_30d_pct    REAL,
                    btc_sma50             REAL,
                    btc_sma200            REAL,
                    ethbtc                REAL,
                    fear_greed            INTEGER,
                    fear_greed_label      TEXT,
                    btc_dominance_pct     REAL,
                    total_market_cap_usd  REAL,
                    mcap_excl_btc_usd     REAL,
                    dominance_source      TEXT,
                    breadth_advancing_pct REAL,
                    breadth_median_pct    REAL,
                    raw_json              TEXT
                );

                -- FAZ F7 — Borsada yapılan işlemler.
                --
                -- NEDEN ARŞİVDE, NEDEN DEFTERDE DEĞİL: buradaki satırlar
                -- HENÜZ defter kaydı değil. Borsanın söylediği ham gerçek
                -- ile kullanıcının defterine yazmaya karar verdiği şey iki
                -- ayrı düzlemdir ve aynı tabloda tutulmaları, onaylanmamış
                -- bir işlemin portföy matematiğine sızması demek olurdu.
                --
                -- `event_uid` tekilleştirmenin taşıyıcısıdır: borsanın kendi
                -- işlem numarasını içerir, yani aynı işlem kaç kez çekilirse
                -- çekilsin bir kez yazılır. Deftere işlendiğinde bu kimlik
                -- defter kaydına da damgalanır (`source_ref`), böylece aynı
                -- satış iki kez işlenemez.
                CREATE TABLE IF NOT EXISTS exchange_events (
                    event_uid     TEXT PRIMARY KEY,
                    exchange      TEXT NOT NULL,
                    kind          TEXT NOT NULL,   -- TRADE | DUST
                    symbol        TEXT,
                    base_asset    TEXT,
                    quote_asset   TEXT,
                    side          TEXT,            -- BUY | SELL
                    qty           REAL,
                    price         REAL,
                    quote_qty     REAL,
                    fee_asset     TEXT,
                    fee_qty       REAL,
                    trade_at      TEXT,            -- ISO8601
                    trade_ts      REAL,
                    status        TEXT NOT NULL DEFAULT 'pending',
                    applied_tx_id INTEGER,
                    applied_at    TEXT,
                    dismissed_at  TEXT,
                    seen_at       TEXT NOT NULL,
                    raw_json      TEXT
                );

                -- Sembol başına imleç. `scope` bir sembol ('ARBUSDT') ya da
                -- sembol-dışı bir akış ('__dust__') olabilir.
                CREATE TABLE IF NOT EXISTS exchange_sync_state (
                    exchange     TEXT NOT NULL,
                    scope        TEXT NOT NULL,
                    cursor       TEXT,
                    last_sync_at TEXT,
                    last_sync_ts REAL,
                    last_error   TEXT,
                    PRIMARY KEY (exchange, scope)
                );

                -- En son görülen bakiye. Tek amacı fark almak: bir varlığın
                -- miktarı değiştiği hâlde onu açıklayan bir işlem
                -- bulunamıyorsa kullanıcıya SUSMAK yerine "şunu göremiyorum"
                -- denir. Toz dönüşümü tam olarak bu boşluktan girmişti.
                CREATE TABLE IF NOT EXISTS exchange_balance_state (
                    exchange TEXT NOT NULL,
                    asset    TEXT NOT NULL,
                    qty      REAL,
                    seen_at  TEXT,
                    seen_ts  REAL,
                    PRIMARY KEY (exchange, asset)
                );

                CREATE INDEX IF NOT EXISTS idx_exevents_status
                    ON exchange_events(status, trade_ts);
                CREATE INDEX IF NOT EXISTS idx_exevents_symbol
                    ON exchange_events(exchange, symbol);
                CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(taken_date);
                CREATE INDEX IF NOT EXISTS idx_pos_symbol ON snapshot_positions(symbol);
                CREATE INDEX IF NOT EXISTS idx_ai_reports_ts ON ai_reports(created_ts);
                CREATE INDEX IF NOT EXISTS idx_ai_reports_mode ON ai_reports(mode, created_ts);
            """)
            # OR IGNORE değil UPSERT: eski bir arşiv açıldığında meta satırı
            # "1"de takılı kalıyordu ve dosya aslında güncellenmiş olmasına
            # rağmen eski sürüm gibi görünüyordu.
            conn.execute("""
                INSERT INTO meta (key, value) VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (str(SCHEMA_VERSION),))
        return True
    except Exception as e:
        logger.warning("Arşiv şeması oluşturulamadı: %s", e)
        return False


# ---------------------------------------------------------------------
# Yazma
# ---------------------------------------------------------------------
def _bugun():
    return datetime.now().strftime("%Y-%m-%d")


def son_kayit_bilgisi():
    """(taken_date, taken_ts) veya kayıt yoksa (None, 0.0)."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT taken_date, taken_ts FROM snapshots ORDER BY taken_date DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None, 0.0
        return row["taken_date"], float(row["taken_ts"] or 0.0)
    except Exception as e:
        logger.debug("Arşiv son kayıt okunamadı: %s", e)
        return None, 0.0


def write_snapshot(metrics, wallets=None, realized_pnl_usd=0.0, source="auto"):
    """
    Portföyün o anki hâlini arşive yazar. Aynı gün varsa ÜZERİNE yazar.

    `metrics` = calculate_portfolio_metrics(...) çıktısı.
    Başarılıysa snapshot id, değilse None döner. ASLA istisna fırlatmaz.
    """
    try:
        if not init_archive():
            return None

        kpis = (metrics or {}).get("kpis") or {}
        coins = (metrics or {}).get("consolidated_coins") or []
        ex_kpis = (metrics or {}).get("exchange_kpis") or {}
        wallets = wallets or {}

        simdi = datetime.now()
        gun = simdi.strftime("%Y-%m-%d")

        with _connect() as conn:
            conn.execute("""
                INSERT INTO snapshots (
                    taken_date, taken_at, taken_ts, source,
                    total_equity_usd, spot_value_usd, spot_invested_usd, cash_usd,
                    futures_balance_usd, margin_balance_usd, hedge_unrealized_usd,
                    realized_pnl_usd, position_count, no_source_count, no_source_value_usd
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(taken_date) DO UPDATE SET
                    taken_at = excluded.taken_at,
                    taken_ts = excluded.taken_ts,
                    source = excluded.source,
                    total_equity_usd = excluded.total_equity_usd,
                    spot_value_usd = excluded.spot_value_usd,
                    spot_invested_usd = excluded.spot_invested_usd,
                    cash_usd = excluded.cash_usd,
                    futures_balance_usd = excluded.futures_balance_usd,
                    margin_balance_usd = excluded.margin_balance_usd,
                    hedge_unrealized_usd = excluded.hedge_unrealized_usd,
                    realized_pnl_usd = excluded.realized_pnl_usd,
                    position_count = excluded.position_count,
                    no_source_count = excluded.no_source_count,
                    no_source_value_usd = excluded.no_source_value_usd
            """, (
                gun, simdi.isoformat(timespec="seconds"), time.time(), source,
                float(kpis.get("total_kasa") or 0.0),
                float(kpis.get("spot_current_value") or 0.0),
                float(kpis.get("spot_invested") or 0.0),
                float(kpis.get("usdt_cash") or 0.0),
                float(wallets.get("futures_balance") or 0.0),
                float(wallets.get("margin_balance") or 0.0),
                float(kpis.get("hedge_unrealized_pnl_usd") or 0.0),
                float(realized_pnl_usd or 0.0),
                len(coins),
                int(kpis.get("no_source_count") or 0),
                float(kpis.get("no_source_value_usd") or 0.0),
            ))

            sid = conn.execute(
                "SELECT id FROM snapshots WHERE taken_date = ?", (gun,)
            ).fetchone()["id"]

            # Tazeleme durumunda eski detay satırları kalmasın.
            conn.execute("DELETE FROM snapshot_positions WHERE snapshot_id = ?", (sid,))
            conn.execute("DELETE FROM snapshot_locations WHERE snapshot_id = ?", (sid,))

            conn.executemany("""
                INSERT INTO snapshot_positions (
                    snapshot_id, pos_key, symbol, location, qty, avg_cost,
                    price, value_usd, pnl_usd, no_source, price_source
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, [(
                sid,
                c.get("pos_key") or f"{c.get('symbol')}@{c.get('exchange')}",
                c.get("symbol"),
                c.get("exchange"),
                float(c.get("total_qty") or 0.0),
                float(c.get("avg_cost") or 0.0),
                float(c.get("live_price") or 0.0),
                float(c.get("current_value") or 0.0),
                float(c.get("pnl_usd") or 0.0),
                1 if c.get("no_source") else 0,
                c.get("source"),
            ) for c in coins])

            konum_satirlari = []
            for loc, k in ex_kpis.items():
                if loc == "ALL" or not isinstance(k, dict):
                    continue
                konum_satirlari.append((
                    sid, loc,
                    float(k.get("spot_current_value") or 0.0),
                    float(k.get("usdt_cash") or 0.0),
                    float(k.get("total_kasa") or 0.0),
                ))
            conn.executemany("""
                INSERT INTO snapshot_locations
                    (snapshot_id, location, spot_value_usd, cash_usd, total_usd)
                VALUES (?,?,?,?,?)
            """, konum_satirlari)

        return sid
    except Exception as e:
        # Arşiv kritik yol değildir; uygulamayı düşürmesine izin verilmez.
        logger.warning("Arşiv kaydı yazılamadı: %s", e)
        return None


def maybe_write_daily_snapshot(metrics, live_prices, wallets=None, realized_pnl_usd=0.0):
    """
    Gerekiyorsa günlük fotoğrafı yazar. Sık çağrılmak üzere tasarlandı.

    Yazmayı ATLADIĞI durumlar:
      - Canlı fiyat yok (uygulama daha yeni açıldı) → portföyü "her şey
        kaynaksız" hâlde dondurup eğriyi bozardı.
      - Bugünün kaydı var ve TTL dolmadı.
    """
    try:
        if not live_prices:
            return None
        gun, ts = son_kayit_bilgisi()
        if gun == _bugun() and (time.time() - ts) < SNAPSHOT_REFRESH_TTL:
            return None
        return write_snapshot(metrics, wallets=wallets,
                              realized_pnl_usd=realized_pnl_usd, source="auto")
    except Exception as e:
        logger.debug("Günlük arşiv kontrolü başarısız: %s", e)
        return None


# ---------------------------------------------------------------------
# Okuma
# ---------------------------------------------------------------------
def net_worth_series(days=None):
    """Net varlık eğrisi — eskiden yeniye."""
    try:
        init_archive()
        sorgu = """
            SELECT taken_date, taken_at, total_equity_usd, spot_value_usd,
                   spot_invested_usd, cash_usd, realized_pnl_usd,
                   position_count, no_source_value_usd
            FROM snapshots
        """
        params = ()
        if days:
            sinir = (datetime.now() - timedelta(days=int(days))).strftime("%Y-%m-%d")
            sorgu += " WHERE taken_date >= ?"
            params = (sinir,)
        sorgu += " ORDER BY taken_date ASC"
        with _connect() as conn:
            return [dict(r) for r in conn.execute(sorgu, params).fetchall()]
    except Exception as e:
        logger.debug("Arşiv serisi okunamadı: %s", e)
        return []


def symbol_price_history(symbol, days=None):
    """
    Bir sembolün arşivlenmiş fiyat geçmişi.

    Delist olmuş veya küçük borsalarda işlem gören coinler için bu, zamanla
    hiçbir API'nin veremeyeceği tek kaynak hâline gelir.
    """
    try:
        init_archive()
        sorgu = """
            SELECT s.taken_date, p.price, p.qty, p.value_usd, p.location, p.no_source
            FROM snapshot_positions p
            JOIN snapshots s ON s.id = p.snapshot_id
            WHERE UPPER(p.symbol) = UPPER(?)
        """
        params = [symbol]
        if days:
            sinir = (datetime.now() - timedelta(days=int(days))).strftime("%Y-%m-%d")
            sorgu += " AND s.taken_date >= ?"
            params.append(sinir)
        sorgu += " ORDER BY s.taken_date ASC"
        with _connect() as conn:
            return [dict(r) for r in conn.execute(sorgu, params).fetchall()]
    except Exception as e:
        logger.debug("Arşiv fiyat geçmişi okunamadı: %s", e)
        return []


def location_series(days=None):
    """Konum bazlı toplam değerin zaman içindeki seyri."""
    try:
        init_archive()
        sorgu = """
            SELECT s.taken_date, l.location, l.spot_value_usd, l.cash_usd, l.total_usd
            FROM snapshot_locations l
            JOIN snapshots s ON s.id = l.snapshot_id
        """
        params = ()
        if days:
            sinir = (datetime.now() - timedelta(days=int(days))).strftime("%Y-%m-%d")
            sorgu += " WHERE s.taken_date >= ?"
            params = (sinir,)
        sorgu += " ORDER BY s.taken_date ASC, l.location ASC"
        with _connect() as conn:
            return [dict(r) for r in conn.execute(sorgu, params).fetchall()]
    except Exception as e:
        logger.debug("Arşiv konum serisi okunamadı: %s", e)
        return []


def find_gaps(limit=20):
    """
    Kayıt bulunmayan gün aralıklarını döndürür.

    Uygulama kapalıyken fotoğraf oluşmaz. Bu bir hata değil ama SÖYLENMELİ:
    sessizce eksik veriyle devam etmek, hiç veri olmamasından kötüdür.
    """
    try:
        init_archive()
        with _connect() as conn:
            gunler = [r["taken_date"] for r in conn.execute(
                "SELECT taken_date FROM snapshots ORDER BY taken_date ASC").fetchall()]
        if len(gunler) < 2:
            return []

        bosluklar = []
        for onceki, sonraki in zip(gunler, gunler[1:]):
            d1 = datetime.strptime(onceki, "%Y-%m-%d")
            d2 = datetime.strptime(sonraki, "%Y-%m-%d")
            fark = (d2 - d1).days
            if fark > 1:
                bosluklar.append({
                    "from": (d1 + timedelta(days=1)).strftime("%Y-%m-%d"),
                    "to": (d2 - timedelta(days=1)).strftime("%Y-%m-%d"),
                    "missing_days": fark - 1,
                })
        return bosluklar[-limit:]
    except Exception as e:
        logger.debug("Arşiv boşlukları hesaplanamadı: %s", e)
        return []


def archive_status():
    """Arşivin özeti — arayüzün bilgi satırı ve boşluk uyarısı için."""
    try:
        init_archive()
        with _connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*) AS adet,
                       MIN(taken_date) AS ilk,
                       MAX(taken_date) AS son
                FROM snapshots
            """).fetchone()
            pos = conn.execute(
                "SELECT COUNT(*) AS adet FROM snapshot_positions").fetchone()

        adet = int(row["adet"] or 0)
        son = row["son"]
        gun_farki = None
        if son:
            gun_farki = (datetime.now().date()
                         - datetime.strptime(son, "%Y-%m-%d").date()).days

        yol = archive_path()
        boyut = os.path.getsize(yol) if os.path.exists(yol) else 0
        bosluklar = find_gaps()

        return {
            "enabled": True,
            "snapshot_count": adet,
            "position_row_count": int(pos["adet"] or 0),
            "first_date": row["ilk"],
            "last_date": son,
            "days_since_last": gun_farki,
            "gap_count": len(bosluklar),
            "missing_days_total": sum(g["missing_days"] for g in bosluklar),
            "gaps": bosluklar[-5:],
            "file_size_bytes": boyut,
            "schema_version": SCHEMA_VERSION,
        }
    except Exception as e:
        logger.debug("Arşiv durumu okunamadı: %s", e)
        return {"enabled": False, "snapshot_count": 0, "gaps": [],
                "error": str(e)[:200]}


# ---------------------------------------------------------------------
# YZ ANALİZ RAPORLARI
#
# Raporlar eskiden yalnızca tarayıcı belleğindeydi; sayfa yenilenince
# kayboluyorlardı. Kalıcılaştırmanın iki ayrı faydası var:
#
#   1. Kullanıcı geçen hafta ne önerildiğini geri okuyabiliyor.
#   2. Bir sonraki analize "en son şunu demiştin" bilgisi verilebiliyor.
#      Amaç modeli tutarlı olmaya ZORLAMAK değil — koşullar değişmediyse
#      aynı şeyi tekrar söylemesi zaten doğrudur. Amaç tekrarı GÖRÜNÜR
#      kılmak: model "bu, 30 Ağustos'taki önerimin aynısı, bakiye
#      değişmemiş" diyebilsin.
# ---------------------------------------------------------------------

# Modele geri verilen rapor metni bu uzunlukta kesilir. Tam metni göndermek
# istem boyutunu hızla şişirir; kullanıcı ücretsiz Gemini katmanında ve kota
# sınırına takılıyor. Özet, tekrarı fark ettirmeye yetiyor.
ONCEKI_RAPOR_KARAKTER_SINIRI = 1200


def save_ai_report(mode, report_markdown, source=None, model_name=None,
                   custom_question="", portfolio_digest=None):
    """Bir YZ raporunu arşive yazar. Başarılıysa id, değilse None döner.

    ASLA istisna fırlatmaz — arşiv konfor katmanıdır; kaydetme başarısız
    olsa bile kullanıcı raporunu görmeye devam etmeli.
    """
    try:
        if not init_archive():
            return None
        if not (report_markdown or "").strip():
            return None
        simdi = datetime.now()
        with _connect() as conn:
            cur = conn.execute("""
                INSERT INTO ai_reports
                    (created_at, created_ts, mode, source, model_name,
                     custom_question, report_markdown, portfolio_digest)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                simdi.isoformat(timespec="seconds"),
                simdi.timestamp(),
                str(mode or "full_audit"),
                str(source or ""),
                str(model_name or ""),
                str(custom_question or "")[:2000],
                report_markdown,
                json.dumps(portfolio_digest or {}, ensure_ascii=False),
            ))
            return cur.lastrowid
    except Exception as e:
        logger.warning("YZ raporu arşive yazılamadı: %s", e)
        return None


def _rapor_satiri(row, metin_dahil=False):
    try:
        ozet = json.loads(row["portfolio_digest"] or "{}")
    except Exception:
        ozet = {}
    kayit = {
        "id": row["id"],
        "created_at": row["created_at"],
        "created_ts": row["created_ts"],
        "mode": row["mode"],
        "source": row["source"],
        "model_name": row["model_name"],
        "custom_question": row["custom_question"],
        "portfolio_digest": ozet,
    }
    if metin_dahil:
        kayit["report_markdown"] = row["report_markdown"]
    return kayit


def list_ai_reports(limit=50, mode=None):
    """Rapor geçmişi — yeniden eskiye. Metin DAHİL DEĞİL (liste hafif kalsın)."""
    try:
        init_archive()
        sorgu = "SELECT * FROM ai_reports"
        params = []
        if mode:
            sorgu += " WHERE mode = ?"
            params.append(str(mode))
        sorgu += " ORDER BY created_ts DESC LIMIT ?"
        params.append(int(limit))
        with _connect() as conn:
            return [_rapor_satiri(r) for r in conn.execute(sorgu, params).fetchall()]
    except Exception as e:
        logger.debug("YZ rapor listesi okunamadı: %s", e)
        return []


def get_ai_report(report_id):
    """Tek bir raporun tam metni."""
    try:
        init_archive()
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM ai_reports WHERE id = ?", (int(report_id),)).fetchone()
        return _rapor_satiri(row, metin_dahil=True) if row else None
    except Exception as e:
        logger.debug("YZ raporu okunamadı: %s", e)
        return None


def last_ai_report(mode=None):
    """En son rapor (metniyle). Bir sonraki analize bağlam olarak verilir."""
    try:
        init_archive()
        sorgu = "SELECT * FROM ai_reports"
        params = []
        if mode:
            sorgu += " WHERE mode = ?"
            params.append(str(mode))
        sorgu += " ORDER BY created_ts DESC LIMIT 1"
        with _connect() as conn:
            row = conn.execute(sorgu, params).fetchone()
        return _rapor_satiri(row, metin_dahil=True) if row else None
    except Exception as e:
        logger.debug("Son YZ raporu okunamadı: %s", e)
        return None


def delete_ai_report(report_id):
    """Tek bir raporu siler. Kullanıcının kendi verisi, silebilmeli."""
    try:
        init_archive()
        with _connect() as conn:
            cur = conn.execute("DELETE FROM ai_reports WHERE id = ?", (int(report_id),))
            return cur.rowcount > 0
    except Exception as e:
        logger.warning("YZ raporu silinemedi: %s", e)
        return False


def ai_report_count():
    try:
        init_archive()
        with _connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS a FROM ai_reports").fetchone()["a"] or 0)
    except Exception:
        return 0


# =====================================================================
# FAZ M1 — PİYASA FOTOĞRAFI
# =====================================================================
# Modülün 1 numaralı tasarım kuralı burada da geçerli: arşiv HİÇBİR ZAMAN
# uygulamayı düşürmez. Piyasa verisi yazılamazsa portföy çalışmaya devam
# eder; kaybedilen şey bir günlük geçmiştir, uygulamanın kendisi değil.

def _piyasa_alanlari(snapshot):
    """`market_service.get_snapshot()` çıktısını tablo sütunlarına indirger.

    Bayat bloklar da yazılır — ama SADECE servis onları verdiyse. Servis çok
    eskiyen bloğu zaten hiç döndürmüyor, yani buraya ulaşan her değer
    kullanılabilir yaştadır.
    """
    bloklar = (snapshot or {}).get("blocks") or {}
    btc = bloklar.get("btc_trend") or {}
    eth = bloklar.get("ethbtc") or {}
    fng = bloklar.get("fear_greed") or {}
    glb = bloklar.get("global") or {}
    gen = bloklar.get("breadth") or {}

    return {
        "btc_price_usd": btc.get("price"),
        "btc_change_7d_pct": btc.get("change_7d_pct"),
        "btc_change_30d_pct": btc.get("change_30d_pct"),
        "btc_sma50": btc.get("sma50"),
        "btc_sma200": btc.get("sma200"),
        "ethbtc": eth.get("value"),
        "fear_greed": fng.get("value"),
        "fear_greed_label": fng.get("classification"),
        "btc_dominance_pct": glb.get("btc_dominance_pct"),
        "total_market_cap_usd": glb.get("total_market_cap_usd"),
        "mcap_excl_btc_usd": glb.get("market_cap_excl_btc_usd"),
        # Kaynak adı olmadan dominans sayısının geçmişte anlamı yok.
        "dominance_source": glb.get("source"),
        "breadth_advancing_pct": gen.get("advancing_pct"),
        "breadth_median_pct": gen.get("median_change_24h_pct"),
    }


def write_market_snapshot(snapshot):
    """Günlük piyasa fotoğrafını yazar. Aynı gün varsa üzerine yazar.

    Üzerine yazmak bilinçli: gün içinde birden çok tur dönebilir ve o günün
    satırı günün SON gözlemine yakınsamalıdır — portföy fotoğrafında da aynı
    davranış var.
    """
    try:
        if not snapshot or not snapshot.get("available"):
            return False
        alanlar = _piyasa_alanlari(snapshot)
        # Tamamen boş bir satır yazmanın anlamı yok; arşivde "o gün veri
        # vardı" yanılsaması yaratır.
        if all(v is None for v in alanlar.values()):
            return False

        init_archive()
        simdi = time.time()
        with _connect() as conn:
            conn.execute("""
                INSERT INTO market_snapshots (
                    taken_date, taken_at, taken_ts,
                    btc_price_usd, btc_change_7d_pct, btc_change_30d_pct,
                    btc_sma50, btc_sma200, ethbtc,
                    fear_greed, fear_greed_label,
                    btc_dominance_pct, total_market_cap_usd, mcap_excl_btc_usd,
                    dominance_source, breadth_advancing_pct, breadth_median_pct,
                    raw_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(taken_date) DO UPDATE SET
                    taken_at = excluded.taken_at,
                    taken_ts = excluded.taken_ts,
                    btc_price_usd = excluded.btc_price_usd,
                    btc_change_7d_pct = excluded.btc_change_7d_pct,
                    btc_change_30d_pct = excluded.btc_change_30d_pct,
                    btc_sma50 = excluded.btc_sma50,
                    btc_sma200 = excluded.btc_sma200,
                    ethbtc = excluded.ethbtc,
                    fear_greed = excluded.fear_greed,
                    fear_greed_label = excluded.fear_greed_label,
                    btc_dominance_pct = excluded.btc_dominance_pct,
                    total_market_cap_usd = excluded.total_market_cap_usd,
                    mcap_excl_btc_usd = excluded.mcap_excl_btc_usd,
                    dominance_source = excluded.dominance_source,
                    breadth_advancing_pct = excluded.breadth_advancing_pct,
                    breadth_median_pct = excluded.breadth_median_pct,
                    raw_json = excluded.raw_json
            """, (
                _bugun(), datetime.now().isoformat(timespec="seconds"), simdi,
                alanlar["btc_price_usd"], alanlar["btc_change_7d_pct"],
                alanlar["btc_change_30d_pct"], alanlar["btc_sma50"],
                alanlar["btc_sma200"], alanlar["ethbtc"],
                alanlar["fear_greed"], alanlar["fear_greed_label"],
                alanlar["btc_dominance_pct"], alanlar["total_market_cap_usd"],
                alanlar["mcap_excl_btc_usd"], alanlar["dominance_source"],
                alanlar["breadth_advancing_pct"], alanlar["breadth_median_pct"],
                json.dumps(snapshot.get("blocks") or {}, ensure_ascii=False),
            ))
        return True
    except Exception as e:
        logger.warning("Piyasa fotoğrafı yazılamadı: %s", e)
        return False


def market_series(days=30):
    """Son N günün piyasa satırları, eskiden yeniye."""
    try:
        init_archive()
        sorgu = ("SELECT taken_date, btc_price_usd, btc_dominance_pct, fear_greed, "
                 "fear_greed_label, ethbtc, total_market_cap_usd, mcap_excl_btc_usd, "
                 "dominance_source, breadth_advancing_pct "
                 "FROM market_snapshots ORDER BY taken_date DESC")
        params = []
        if days:
            sorgu += " LIMIT ?"
            params.append(int(days))
        with _connect() as conn:
            rows = conn.execute(sorgu, params).fetchall()
        return [dict(r) for r in reversed(rows)]
    except Exception as e:
        logger.debug("Piyasa serisi okunamadı: %s", e)
        return []


def market_change_since(days_ago=7):
    """N gün önceki piyasa satırıyla bugünkü arasındaki farkı verir.

    Modelin "dominans yükseliyor mu düşüyor mu" sorusunu cevaplayabilmesi
    için gereken TEK şey bu — ve bu bilgiyi hiçbir ücretsiz uçtan geriye
    dönük alamıyoruz, yalnızca kendi arşivimizden.

    Kaynak değişmişse fark HESAPLANMAZ: farklı konvansiyonlardaki iki
    dominans değerini çıkarmak, gerçek olmayan bir hareket üretir.
    """
    try:
        seri = market_series(days=None)
        if len(seri) < 2:
            return None
        bugun = seri[-1]
        hedef_ts = time.time() - (int(days_ago) * 86400)
        hedef_tarih = datetime.fromtimestamp(hedef_ts).strftime("%Y-%m-%d")

        # Hedef tarihe eşit veya ondan eski EN YAKIN satır.
        eski = None
        for r in seri[:-1]:
            if r["taken_date"] <= hedef_tarih:
                eski = r
        if eski is None:
            eski = seri[0]
        if eski["taken_date"] == bugun["taken_date"]:
            return None

        cikti = {
            "from_date": eski["taken_date"],
            "to_date": bugun["taken_date"],
            "days_apart": (datetime.strptime(bugun["taken_date"], "%Y-%m-%d")
                           - datetime.strptime(eski["taken_date"], "%Y-%m-%d")).days,
        }

        ayni_kaynak = (eski.get("dominance_source") == bugun.get("dominance_source"))
        if (ayni_kaynak and eski.get("btc_dominance_pct") is not None
                and bugun.get("btc_dominance_pct") is not None):
            cikti["btc_dominance_change_pts"] = round(
                float(bugun["btc_dominance_pct"]) - float(eski["btc_dominance_pct"]), 2)
        elif not ayni_kaynak:
            cikti["btc_dominance_change_pts"] = None
            cikti["dominance_note"] = (
                "Dominans kaynagi bu aralikta degisti "
                f"({eski.get('dominance_source')} -> {bugun.get('dominance_source')}); "
                "iki farkli konvansiyonun farki alinmadi.")

        if eski.get("fear_greed") is not None and bugun.get("fear_greed") is not None:
            cikti["fear_greed_change"] = int(bugun["fear_greed"]) - int(eski["fear_greed"])
        if eski.get("btc_price_usd") and bugun.get("btc_price_usd"):
            cikti["btc_change_pct"] = round(
                100.0 * (float(bugun["btc_price_usd"]) - float(eski["btc_price_usd"]))
                / float(eski["btc_price_usd"]), 2)
        return cikti
    except Exception as e:
        logger.debug("Piyasa değişimi hesaplanamadı: %s", e)
        return None


def market_snapshot_count():
    try:
        init_archive()
        with _connect() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) AS a FROM market_snapshots").fetchone()["a"] or 0)
    except Exception:
        return 0


# =====================================================================
# FAZ F7 — BORSA İŞLEMLERİ
# =====================================================================
# Buradaki işlevler de modülün 1 numaralı kuralına uyar: hiçbiri istisna
# fırlatmaz. Ama sessiz de kalmazlar — `record_exchange_events` yazamadığında
# None döner ve çağıran taraf bunu "sıfır yeni işlem" ile karıştırmaz.

EVENT_PENDING = "pending"
EVENT_APPLIED = "applied"
EVENT_DISMISSED = "dismissed"

_EVENT_ALANLARI = (
    "event_uid", "exchange", "kind", "symbol", "base_asset", "quote_asset",
    "side", "qty", "price", "quote_qty", "fee_asset", "fee_qty",
    "trade_at", "trade_ts", "raw_json",
)


def record_exchange_events(rows):
    """Yeni borsa işlemlerini yazar. Zaten görülmüş olanlar ATLANIR.

    Dönen değer YENİ yazılan satır sayısıdır; yazamazsa None. İkisi farklı
    şeydir: "yeni işlem yok" ile "arşive ulaşamadım" aynı şekilde
    raporlanırsa kullanıcı her ikisinde de aynı boş ekranı görür.

    `INSERT OR IGNORE` bilinçli: aynı işlem tekrar çekildiğinde üzerine
    yazsaydık, kullanıcının o satır için verdiği karar (işlendi / yok sayıldı)
    silinir ve satır yeniden "bekliyor" hâline dönerdi.
    """
    try:
        if not rows:
            return 0
        if not init_archive():
            return None
        simdi = datetime.now().isoformat(timespec="seconds")
        yeni = 0
        with _connect() as conn:
            for r in rows:
                degerler = [r.get(a) for a in _EVENT_ALANLARI]
                imlec = conn.execute(f"""
                    INSERT OR IGNORE INTO exchange_events
                        ({', '.join(_EVENT_ALANLARI)}, status, seen_at)
                    VALUES ({', '.join('?' * len(_EVENT_ALANLARI))}, ?, ?)
                """, (*degerler, EVENT_PENDING, simdi))
                yeni += imlec.rowcount or 0
        return yeni
    except Exception as e:
        logger.warning("Borsa işlemleri arşive yazılamadı: %s", e)
        return None


def list_exchange_events(status=EVENT_PENDING, limit=200, exchange=None):
    """İşlem satırları, YENİDEN ESKİYE. `status=None` hepsini verir."""
    try:
        init_archive()
        sorgu = "SELECT * FROM exchange_events"
        kosullar, params = [], []
        if status:
            kosullar.append("status = ?")
            params.append(str(status))
        if exchange:
            kosullar.append("exchange = ?")
            params.append(str(exchange).upper())
        if kosullar:
            sorgu += " WHERE " + " AND ".join(kosullar)
        sorgu += " ORDER BY trade_ts DESC, event_uid DESC LIMIT ?"
        params.append(int(max(1, min(int(limit), 2000))))
        with _connect() as conn:
            return [dict(r) for r in conn.execute(sorgu, params).fetchall()]
    except Exception as e:
        logger.debug("Borsa işlemleri okunamadı: %s", e)
        return []


def get_exchange_event(event_uid):
    try:
        init_archive()
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM exchange_events WHERE event_uid = ?",
                (str(event_uid),)).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.debug("Borsa işlemi okunamadı (%s): %s", event_uid, e)
        return None


def set_event_status(event_uid, status, tx_id=None):
    """Satırın durumunu değiştirir. Yalnızca `pending` satır değiştirilebilir.

    Bu kısıt bilinçli: deftere işlenmiş bir satırı tekrar işlemek çift kayıt,
    yok sayılmış bir satırı sessizce yeniden açmak da kaybolmuş bir karar
    demektir. İkisi de kullanıcının haberi olmadan olmamalı.
    """
    try:
        init_archive()
        simdi = datetime.now().isoformat(timespec="seconds")
        with _connect() as conn:
            if status == EVENT_APPLIED:
                imlec = conn.execute("""
                    UPDATE exchange_events
                       SET status = ?, applied_tx_id = ?, applied_at = ?
                     WHERE event_uid = ? AND status = ?
                """, (EVENT_APPLIED, tx_id, simdi, str(event_uid), EVENT_PENDING))
            elif status == EVENT_DISMISSED:
                imlec = conn.execute("""
                    UPDATE exchange_events
                       SET status = ?, dismissed_at = ?
                     WHERE event_uid = ? AND status = ?
                """, (EVENT_DISMISSED, simdi, str(event_uid), EVENT_PENDING))
            else:
                return False
        return (imlec.rowcount or 0) > 0
    except Exception as e:
        logger.warning("Borsa işleminin durumu değiştirilemedi (%s): %s",
                       event_uid, e)
        return False


def exchange_event_counts():
    """{'pending': n, 'applied': n, 'dismissed': n} — arayüzün rozeti."""
    out = {EVENT_PENDING: 0, EVENT_APPLIED: 0, EVENT_DISMISSED: 0}
    try:
        init_archive()
        with _connect() as conn:
            for r in conn.execute(
                    "SELECT status, COUNT(*) AS a FROM exchange_events "
                    "GROUP BY status").fetchall():
                out[r["status"]] = int(r["a"] or 0)
    except Exception as e:
        logger.debug("Borsa işlem sayıları okunamadı: %s", e)
    return out


def applied_source_refs():
    """Deftere işlenmiş satırların kimlikleri — çift kayıt denetimi için."""
    try:
        init_archive()
        with _connect() as conn:
            return {r["event_uid"] for r in conn.execute(
                "SELECT event_uid FROM exchange_events WHERE status = ?",
                (EVENT_APPLIED,)).fetchall()}
    except Exception:
        return set()


# ---------------------------------------------------------------------
# Eşitleme imleci
# ---------------------------------------------------------------------
def get_sync_cursor(exchange, scope):
    try:
        init_archive()
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM exchange_sync_state WHERE exchange = ? AND scope = ?",
                (str(exchange).upper(), str(scope))).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.debug("Eşitleme imleci okunamadı: %s", e)
        return None


def set_sync_cursor(exchange, scope, cursor=None, error=None):
    """İmleci ve son deneme bilgisini yazar.

    Hata durumunda imleç KORUNUR (`COALESCE`): başarısız bir çağrı yüzünden
    imleci sıfırlamak, bir sonraki turda tüm geçmişi yeniden çekmek ya da
    daha kötüsü aradaki işlemleri atlamak demek olurdu.
    """
    try:
        init_archive()
        simdi = time.time()
        with _connect() as conn:
            conn.execute("""
                INSERT INTO exchange_sync_state
                    (exchange, scope, cursor, last_sync_at, last_sync_ts, last_error)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(exchange, scope) DO UPDATE SET
                    cursor = COALESCE(excluded.cursor, exchange_sync_state.cursor),
                    last_sync_at = excluded.last_sync_at,
                    last_sync_ts = excluded.last_sync_ts,
                    last_error = excluded.last_error
            """, (str(exchange).upper(), str(scope),
                  None if cursor is None else str(cursor),
                  datetime.now().isoformat(timespec="seconds"), simdi,
                  str(error)[:300] if error else None))
        return True
    except Exception as e:
        logger.warning("Eşitleme imleci yazılamadı: %s", e)
        return False


def sync_state(exchange=None):
    try:
        init_archive()
        sorgu = "SELECT * FROM exchange_sync_state"
        params = []
        if exchange:
            sorgu += " WHERE exchange = ?"
            params.append(str(exchange).upper())
        with _connect() as conn:
            return [dict(r) for r in conn.execute(sorgu, params).fetchall()]
    except Exception:
        return []


# ---------------------------------------------------------------------
# Bakiye fotoğrafı (fark almak için)
# ---------------------------------------------------------------------
def get_balance_state(exchange):
    """{varlık: miktar}. Hiç kayıt yoksa boş sözlük — "ilk tarama" demektir."""
    try:
        init_archive()
        with _connect() as conn:
            rows = conn.execute(
                "SELECT asset, qty FROM exchange_balance_state WHERE exchange = ?",
                (str(exchange).upper(),)).fetchall()
        return {r["asset"]: float(r["qty"] or 0.0) for r in rows}
    except Exception as e:
        logger.debug("Bakiye durumu okunamadı: %s", e)
        return {}


def set_balance_state(exchange, balances):
    """Bakiye fotoğrafını tazeler. Artık görülmeyen varlıklar SİLİNİR.

    Silmek şart: bir varlık bakiyeden tamamen çıktığında satırı bırakırsak
    her turda aynı "kayboldu" farkını yeniden üretirdik.
    """
    try:
        init_archive()
        borsa = str(exchange).upper()
        simdi = time.time()
        iso = datetime.now().isoformat(timespec="seconds")
        temiz = {str(k).upper(): float(v) for k, v in (balances or {}).items()}
        with _connect() as conn:
            conn.execute("DELETE FROM exchange_balance_state WHERE exchange = ?",
                         (borsa,))
            conn.executemany("""
                INSERT INTO exchange_balance_state
                    (exchange, asset, qty, seen_at, seen_ts)
                VALUES (?,?,?,?,?)
            """, [(borsa, a, q, iso, simdi) for a, q in temiz.items()])
        return True
    except Exception as e:
        logger.warning("Bakiye durumu yazılamadı: %s", e)
        return False
