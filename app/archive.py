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
import sqlite3
import time
from datetime import datetime, timedelta

from log_config import get_logger

logger = get_logger("archive")

ARCHIVE_FILENAME = "archive.db"

# Aynı günün kaydı bu süre geçtikten sonra tazelenir (saniye).
# Amaç: bir günün satırı o günün son gözlemine yakınsasın.
SNAPSHOT_REFRESH_TTL = 3600.0

SCHEMA_VERSION = 1


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

                CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(taken_date);
                CREATE INDEX IF NOT EXISTS idx_pos_symbol ON snapshot_positions(symbol);
            """)
            conn.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
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
