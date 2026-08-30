import os
import re
import hashlib
import uvicorn
import shutil
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
import time

from data_manager import (
    load_portfolio, save_portfolio, calculate_portfolio_metrics,
    save_target, delete_target, execute_target_sale,
    load_settings, save_settings, merge_settings, ping_services,
    calculate_realized_metrics, export_portfolio_excel,
    verify_pin, set_pin, disable_pin, change_pin, update_security_settings,
    verify_recovery_key, reset_pin_with_recovery,
    initialize_portfolio_if_missing, DEFAULT_CATEGORIES, DATA_FILE, BACKUP_DIR,
    get_symbol_sources, set_symbol_source, delete_symbol_source,
    set_price_sources, validate_source_spec, normalize_symbol_key,
    open_hedge, close_hedge, delete_hedge, hedge_scenario,
    write_off_position, undo_write_off, transfer_position, undo_transfer,
    list_transfers, list_write_offs, WRITE_OFF_REASONS,
    get_rebuild_plan, apply_rebuild, undo_rebuild, list_rebuilds,
    known_locations, symbol_for_location, run_pending_migrations
)
from price_service import price_service
import archive
import reconcile
import connections
import keyvault
from log_config import get_logger, LOG_FILE

logger = get_logger("main")

app = FastAPI(title="Kripto Portföy Takip & Canlı Terminal")

# Uygulama tamamen yereldir; arayüz de aynı origin'den (127.0.0.1:8000) sunulur.
# Joker "*" yerine sadece kendi origin'lerimize izin veriyoruz — aksi halde tarayıcıda
# açık olan herhangi bir web sitesi yerel API'den portföy verisini okuyabilir.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("=" * 62)
logger.info("CoinTakip başlatılıyor — log dosyası: %s", LOG_FILE)
initialize_portfolio_if_missing()
# Bir kez uygulanacak veri düzeltmeleri. Sessizce değil, loglayarak.
run_pending_migrations()
price_service.start_background_updater()
logger.info("Sunucu hazır: http://127.0.0.1:8000")

class TransactionCreate(BaseModel):
    date: Optional[str] = None
    coin: str
    exchange: Optional[str] = "BINANCE"
    qty: float
    cost: float
    status: Optional[str] = "Aktif"
    notes: Optional[str] = ""
    category: Optional[str] = None
    fee_amount: Optional[float] = 0.0
    fee_asset: Optional[str] = "USDT"
    fee_usd: Optional[float] = 0.0

class TransactionUpdate(BaseModel):
    date: Optional[str] = None
    coin: Optional[str] = None
    exchange: Optional[str] = None
    qty: Optional[float] = None
    cost: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    category: Optional[str] = None
    fee_amount: Optional[float] = None
    fee_asset: Optional[str] = None
    fee_usd: Optional[float] = None

class SellRequest(BaseModel):
    sell_qty: float
    sell_price: float
    date: Optional[str] = None
    notes: Optional[str] = ""
    fee_amount: Optional[float] = 0.0
    fee_asset: Optional[str] = "USDT"
    fee_usd: Optional[float] = 0.0
    cost_method: Optional[str] = "Konsolide Ortalama"

def compute_fee_usd(fee_amount: float, fee_asset: str, total_value: float, live_prices: dict) -> float:
    if not fee_amount or fee_amount <= 0:
        return 0.0
    asset_clean = (fee_asset or "USDT").upper().strip()
    if asset_clean in ["USDT", "USD"]:
        return round(float(fee_amount), 4)
    if asset_clean == "%":
        return round(float(total_value) * (float(fee_amount) / 100.0), 4)
    if asset_clean in ["BNB", "BNBUSDT"]:
        bnb_p = float(live_prices.get("BNBUSDT", {}).get("price", 600.0))
        return round(float(fee_amount) * bnb_p, 4)
    lookup = f"{asset_clean}USDT" if not asset_clean.endswith("USDT") else asset_clean
    p = float(live_prices.get(lookup, {}).get("price", 1.0))
    return round(float(fee_amount) * p, 4)

class WalletsUpdate(BaseModel):
    usdt_cash: Optional[float] = None
    exchange_cash: Optional[Dict[str, float]] = None
    futures_balance: Optional[float] = 0.0
    margin_balance: Optional[float] = 0.0

class TargetIn(BaseModel):
    pos_key: str
    target_price: float
    target_sell_pct: Optional[float] = 100.0
    notes: Optional[str] = ""

@app.get("/api/portfolio")
def get_portfolio():
    data = load_portfolio()
    live_prices = price_service.get_prices()
    metrics = calculate_portfolio_metrics(data, live_prices)
    metrics["last_update_ts"] = price_service.last_update_ts
    metrics["wallets"] = data.get("wallets", {"usdt_cash": 500.0})
    metrics["settings"] = data.get("settings", {})

    # FAZ F2 — Günlük arşiv fotoğrafı.
    # Ayrı bir zamanlayıcı thread'i yerine buraya bağlandı: arayüz zaten
    # düzenli olarak bu ucu çağırıyor, yani uygulama açıkken kayıt kendiliğinden
    # oluşuyor. Kontrol tek indeksli sorgu; fonksiyon kendi hatasını yutar ve
    # ASLA bu ucu düşürmez — arşiv konfor katmanıdır, kritik yol değildir.
    archive.maybe_write_daily_snapshot(
        metrics, live_prices,
        wallets=data.get("wallets") or {},
        realized_pnl_usd=(calculate_realized_metrics(data) or {}).get("total_realized_pnl_usd", 0.0),
    )
    return metrics


# -------------------------------------------------------------
# FAZ F2: ARŞİV UÇLARI
# -------------------------------------------------------------
@app.get("/api/archive/status")
def get_archive_status():
    """Arşiv özeti: kaç kayıt, hangi aralık, hangi günler eksik."""
    return archive.archive_status()


@app.get("/api/archive/networth")
def get_archive_networth(days: int = 0):
    """Net varlık eğrisi. days=0 → tüm geçmiş."""
    return {
        "series": archive.net_worth_series(days or None),
        "status": archive.archive_status(),
    }


@app.get("/api/archive/locations")
def get_archive_locations(days: int = 0):
    """Konum bazlı değerin zaman içindeki seyri."""
    return {"series": archive.location_series(days or None)}


@app.get("/api/archive/price-history/{symbol}")
def get_archive_price_history(symbol: str, days: int = 0):
    """
    Arşivlenmiş fiyat geçmişi.

    Delist olmuş coinler için bu zamanla hiçbir API'nin veremeyeceği
    tek kaynak hâline gelir — arşivin asıl varlık sebebi.
    """
    return {"symbol": symbol.upper(), "history": archive.symbol_price_history(symbol, days or None)}


# -------------------------------------------------------------
# FAZ F3: BORSA MUTABAKATI (DOSYA TABANLI, SALT OKUNUR)
# -------------------------------------------------------------
@app.get("/api/reconcile/files")
def list_reconcile_files():
    """Hangi dışa aktarım dosyaları bulundu — mutabakattan önce görünürlük."""
    dosyalar = reconcile.discover_export_files()
    return {
        "root": reconcile.export_root(),
        "files": [{"name": d["name"], "exchange": d["exchange"], "kind": d["kind"]}
                  for d in dosyalar],
        "count": len(dosyalar),
    }


@app.get("/api/reconcile")
def run_reconcile():
    """
    Borsa dışa aktarımlarını defterle karşılaştırır.

    **SALT OKUNURDUR — deftere hiçbir şey yazmaz.** Maliyet tabanı kullanıcının
    elle girdiği hâliyle kalır; bu uç yalnızca farkları raporlar.
    """
    return reconcile.reconcile(load_portfolio())


# -------------------------------------------------------------
# FAZ F5: MUTABAKAT DÜZELTMESİ
# -------------------------------------------------------------
@app.get("/api/reconcile/rebuild")
def get_reconcile_rebuild_plan():
    """
    Borsa kayıtlarından yeniden kurulmuş lot önerileri. **Salt okunurdur.**

    Öneriyi görmek deftere hiçbir şey yazmaz; yazma yalnızca kullanıcının
    pozisyon başına verdiği açık onayla, aşağıdaki POST ucundan olur.
    """
    return get_rebuild_plan()


@app.post("/api/reconcile/rebuild/{pos_key:path}")
def api_apply_rebuild(pos_key: str, payload: dict = Body(None)):
    """
    Tek bir pozisyonun lotlarını borsa kayıtlarıyla değiştirir.

    Nakit hareketi yok, gerçekleşmiş K/Z yok — bu bir kayıt düzeltmesidir.
    İşlem geri alınabilir. İstemcinin gönderdiği lotlara güvenilmez: sunucu
    planı yeniden üretir ve yalnızca imza uyuşursa uygular.

    `verified_qty` — kullanıcının borsa ekranından okuduğu güncel bakiye —
    zorunludur. Kararı sunucu verir: bakiye öneriyle uyuşuyorsa uygulanır,
    defterle uyuşuyorsa eksik olan dosyadır ve deftere DOKUNULMAZ.
    """
    payload = payload or {}
    try:
        kayit = apply_rebuild(
            pos_key,
            signature=payload.get("signature"),
            note=payload.get("note", ""),
            verified_qty=payload.get("verified_qty"),
        )
    except ValueError as e:
        kod = 404 if "önerisi yok" in str(e).lower() else 400
        raise HTTPException(status_code=kod, detail=str(e))
    logger.info("Mutabakat düzeltmesi #%s: %s — %s lot → %s lot, miktar %+.8f",
                kayit["id"], pos_key, kayit["before"]["lot_count"],
                kayit["after"]["lot_count"], kayit["diff_qty"])
    return {"success": True, "rebuild": kayit, **_f1_snapshot()}


@app.get("/api/rebuilds")
def get_rebuilds():
    return {"rebuilds": list_rebuilds()}


@app.post("/api/rebuilds/{rebuild_id}/undo")
def api_undo_rebuild(rebuild_id: int):
    try:
        sonuc = undo_rebuild(rebuild_id)
    except ValueError as e:
        kod = 404 if "bulunamadı" in str(e).lower() else 400
        raise HTTPException(status_code=kod, detail=str(e))
    logger.info("Mutabakat düzeltmesi geri alındı: #%s (%s lot geri açıldı)",
                rebuild_id, sonuc["restored_lots"])
    return {"success": True, "result": sonuc, **_f1_snapshot()}


# -------------------------------------------------------------
# FAZ F6: ANAHTAR KASASI VE BAĞLANTILAR
# -------------------------------------------------------------
@app.get("/api/vault/status")
def api_vault_status():
    """Kasanın durumu. İçerik DÖNMEZ, yalnızca durum bilgisi."""
    return keyvault.status()


@app.post("/api/vault/unlock")
def api_vault_unlock(payload: dict = Body(...)):
    try:
        sonuc = keyvault.unlock(str((payload or {}).get("pin") or ""))
    except keyvault.VaultError as e:
        raise HTTPException(status_code=401, detail=str(e))
    logger.info("Anahtar kasası açıldı.")
    return {"success": True, **sonuc, **keyvault.status()}


@app.post("/api/vault/lock")
def api_vault_lock():
    keyvault.lock()
    return {"success": True, **keyvault.status()}


@app.post("/api/vault/secret/{name}")
def api_vault_put(name: str, payload: dict = Body(...)):
    """Kasaya sır yazar. Yazılan değer bir daha OKUNMAK ÜZERE dönmez."""
    try:
        keyvault.put(name, str((payload or {}).get("value") or ""))
    except keyvault.VaultLocked as e:
        raise HTTPException(status_code=423, detail=str(e))
    except keyvault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "name": name, "stored": keyvault.has(name)}


@app.delete("/api/vault/secret/{name}")
def api_vault_forget(name: str):
    keyvault.forget(name)
    return {"success": True, "name": name, "stored": keyvault.has(name)}


@app.get("/api/connections")
def api_list_connections():
    """
    Bağlantı kayıt defteri + desteklenen zincirler.

    Adresler herkese açık veridir; gizli bir şey döndürülmez. Kasa sırları
    bu uçtan ASLA çıkmaz.
    """
    return {
        "connections": connections.list_connections(),
        "chains": connections.supported_chains(),
        "locations": connections.location_suggestions(),
        "warnings": connections.duplicate_address_warnings(),
        "vault": keyvault.status(),
        "provider_key_set": keyvault.has(connections.ETHERSCAN_KEY_NAME),
    }


# Konum ve zincir artık YOLDA taşınmıyor, gövdede geliyor. Sebep: yol
# parametresi kullanıldığında `{location:path}` açgözlülüğü `.../PHANTOM/test`
# isteğini kaydetme ucuna düşürdü ve kullanıcı farkında olmadan sahte bir
# bağlantı kaydedildi. Sabit yollar bu sınıf hatayı tamamen ortadan kaldırıyor.
@app.post("/api/connections/test")
def api_test_connection(payload: dict = Body(...)):
    """
    Bağlantıyı dener. **Hiçbir şey kaydetmez.**
    Ağ hatası 500 değil, `ok:false` olarak döner — kullanıcı sebebi görmeli.
    """
    spec, hata = connections.validate_connection(payload or {})
    if hata:
        raise HTTPException(status_code=400, detail=hata)
    spec["location"] = (payload or {}).get("location") or ""
    return connections.test_connection((payload or {}).get("id"), spec)


@app.post("/api/connections/token-info")
def api_token_info(payload: dict = Body(...)):
    """
    Bir token kontratının sembolünü ve ondalık hanesini zincirden okur.

    Otomatik keşif her zincirde ücretsiz değil (Etherscan'ın ücretsiz planı
    BNB Chain, Base, Optimism ve Avalanche'ı kapsamıyor). Elle token tanımlama
    o boşluğu kapatır ve bu uç onu kullanıcı için zahmetsiz kılar: kullanıcı
    yalnızca kontrat adresini yapıştırır, sembolü ve ondalığı zincir söyler.
    **Anahtar gerekmez, hiçbir şey kaydedilmez.**
    """
    payload = payload or {}
    try:
        return {"success": True, "token": connections.evm_token_info(
            str(payload.get("chain") or "").strip().lower(),
            payload.get("contract"))}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Kontrat okunamadı: {e}")


@app.post("/api/connections")
def api_save_connection(payload: dict = Body(...)):
    """Bağlantı ekler veya günceller. Kimlik gövdedeki `id` alanıdır."""
    payload = payload or {}
    try:
        kayit = connections.save_connection(
            payload.get("location"), payload, conn_id=payload.get("id"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "connection": kayit,
            "connections": connections.list_connections(),
            "warnings": connections.duplicate_address_warnings()}


@app.delete("/api/connections/{conn_id}")
def api_delete_connection(conn_id: str):
    if not connections.delete_connection(conn_id):
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı.")
    return {"success": True, "connections": connections.list_connections()}


@app.get("/api/connections/balances")
def api_connection_balances():
    """Tüm açık bağlantıların canlı bakiyeleri. **Salt okunur.**"""
    return {"readings": connections.read_all(), "read_only": True}


@app.get("/api/connections/reconcile")
def api_connection_reconcile():
    """
    Canlı cüzdan bakiyeleri ile defterin karşılaştırması. **Yazma yok.**

    Kasa durumu da dönüyor: anahtar kasada durup kasa kilitliyken okuma sessizce
    eksik kalıyordu ve kullanıcı sebebini göremiyordu. Arayüz bunu okumadan
    ÖNCE söyleyebilsin diye rapora ekli.
    """
    rapor = connections.compare_with_ledger()
    rapor["vault"] = {**keyvault.status(),
                      "provider_key_set": keyvault.has(connections.ETHERSCAN_KEY_NAME)}
    return rapor


@app.post("/api/archive/snapshot")
def create_archive_snapshot():
    """Elle fotoğraf al. Bugünün kaydı varsa üzerine yazar."""
    data = load_portfolio()
    live_prices = price_service.get_prices()
    if not live_prices:
        raise HTTPException(
            status_code=400,
            detail="Canlı fiyat yok; fotoğraf portföyü kaynaksız hâlde donduracağı için alınmadı."
        )
    metrics = calculate_portfolio_metrics(data, live_prices)
    sid = archive.write_snapshot(
        metrics,
        wallets=data.get("wallets") or {},
        realized_pnl_usd=(calculate_realized_metrics(data) or {}).get("total_realized_pnl_usd", 0.0),
        source="manual",
    )
    if sid is None:
        raise HTTPException(status_code=500, detail="Arşiv kaydı yazılamadı.")
    logger.info("Elle arşiv fotoğrafı alındı (#%s).", sid)
    return {"success": True, "snapshot_id": sid, "status": archive.archive_status()}

# -------------------------------------------------------------
# FAZ E: HEDGE / KALDIRAÇLI POZİSYON UÇLARI
# -------------------------------------------------------------
def _hedge_snapshot():
    """Hedge hesapları için ortak anlık görüntü (portföy + canlı fiyatlar)."""
    data = load_portfolio()
    live_prices = price_service.get_prices()
    metrics = calculate_portfolio_metrics(data, live_prices)
    return data, live_prices, metrics


@app.get("/api/hedges")
def list_hedges():
    _, _, metrics = _hedge_snapshot()
    return {
        "hedges": metrics.get("hedges", []),
        "hedge_kpis": metrics.get("hedge_kpis", {}),
        "exposures": metrics.get("exposures", []),
    }


@app.post("/api/hedges")
def create_hedge(payload: dict = Body(...)):
    record, err = open_hedge(payload)
    if err:
        raise HTTPException(status_code=400, detail=err)
    _, _, metrics = _hedge_snapshot()
    return {"success": True, "hedge": record,
            "hedges": metrics.get("hedges", []),
            "hedge_kpis": metrics.get("hedge_kpis", {}),
            "exposures": metrics.get("exposures", [])}


@app.post("/api/hedges/{hedge_id}/close")
def close_hedge_endpoint(hedge_id: int, payload: dict = Body(...)):
    record, err = close_hedge(
        hedge_id,
        payload.get("close_price"),
        payload.get("fee_usd", 0.0),
        payload.get("close_date"),
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    _, _, metrics = _hedge_snapshot()
    return {"success": True, "hedge": record,
            "realized_pnl_usd": record.get("realized_pnl_usd"),
            "hedges": metrics.get("hedges", []),
            "hedge_kpis": metrics.get("hedge_kpis", {}),
            "exposures": metrics.get("exposures", [])}


@app.delete("/api/hedges/{hedge_id}")
def remove_hedge(hedge_id: int):
    if not delete_hedge(hedge_id):
        raise HTTPException(status_code=404, detail="Hedge kaydı bulunamadı.")
    _, _, metrics = _hedge_snapshot()
    return {"success": True,
            "hedges": metrics.get("hedges", []),
            "hedge_kpis": metrics.get("hedge_kpis", {}),
            "exposures": metrics.get("exposures", [])}


@app.get("/api/hedges/scenario")
def get_hedge_scenario(move_pct: float = -20.0):
    """'Fiyat %X hareket ederse ne olur?' — spot ve hedge etkisi ayrı ayrı."""
    data, live_prices, metrics = _hedge_snapshot()
    return hedge_scenario(data, live_prices, metrics.get("consolidated_coins", []), move_pct)


# -------------------------------------------------------------
# FAZ F1: DEĞER KAYBI YAZIMI (MEZARLIK) VE TRANSFER UÇLARI
# -------------------------------------------------------------
def _f1_snapshot():
    """Yazım/transfer sonrası arayüzün tazelenmesi için ortak anlık görüntü."""
    data = load_portfolio()
    metrics = calculate_portfolio_metrics(data, price_service.get_prices())
    return {
        "kpis": metrics.get("kpis", {}),
        "consolidated_coins": metrics.get("consolidated_coins", []),
        "transfers": list_transfers(data),
        "write_offs": list_write_offs(data),
        "rebuilds": list_rebuilds(data),
    }


@app.get("/api/write-offs")
def get_write_offs():
    """Yazım kayıtları ve seçilebilir gerekçe listesi."""
    return {
        "write_offs": list_write_offs(),
        "reasons": [{"key": k, "label": v} for k, v in WRITE_OFF_REASONS.items()],
    }


@app.post("/api/positions/{pos_key:path}/write-off")
def api_write_off(pos_key: str, payload: dict = Body(None)):
    """
    Ölmüş bir pozisyonu 0'dan kapatır ve maliyetini zarar yazar.

    Nakit eklenmez — bu bir satış değildir. İşlem geri alınabilir.
    """
    payload = payload or {}
    try:
        sonuc = write_off_position(
            pos_key,
            reason=payload.get("reason", "worthless"),
            note=payload.get("note", ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info("Yazım: %s — %s lot, $%.2f zarar (%s)",
                pos_key, sonuc["lot_count"], sonuc["realized_loss_usd"], sonuc["reason"])
    return {"success": True, "result": sonuc, **_f1_snapshot()}


@app.post("/api/write-offs/{write_off_id}/undo")
def api_undo_write_off(write_off_id: int):
    try:
        sonuc = undo_write_off(write_off_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    logger.info("Yazım geri alındı: #%s (%s lot)", write_off_id, sonuc["restored_lots"])
    return {"success": True, "result": sonuc, **_f1_snapshot()}


@app.get("/api/transfers")
def get_transfers():
    return {"transfers": list_transfers()}


@app.post("/api/transfers")
def api_create_transfer(payload: dict = Body(...)):
    """
    Varlığı borsalar/cüzdanlar arasında taşır. Satış DEĞİLDİR:
    nakit hareketi yok, gerçekleşmiş K/Z yok, maliyet tabanı korunur.
    """
    try:
        kayit = transfer_position(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info("Transfer #%s: %s %s  %s → %s",
                kayit["id"], kayit["qty"], kayit["coin"],
                kayit["from_exchange"], kayit["to_exchange"])
    return {"success": True, "transfer": kayit, **_f1_snapshot()}


@app.delete("/api/transfers/{transfer_id}")
def api_undo_transfer(transfer_id: int):
    try:
        sonuc = undo_transfer(transfer_id)
    except ValueError as e:
        # "Bulunamadı" 404, "geri alınamaz" 400 olmalı.
        kod = 404 if "bulunamadı" in str(e).lower() else 400
        raise HTTPException(status_code=kod, detail=str(e))
    logger.info("Transfer geri alındı: #%s", transfer_id)
    return {"success": True, "result": sonuc, **_f1_snapshot()}


@app.get("/api/transactions")
def get_transactions():
    data = load_portfolio()
    live_prices = price_service.get_prices()
    metrics = calculate_portfolio_metrics(data, live_prices)
    return metrics.get("transactions", [])

@app.post("/api/transactions")
def create_transaction(tx_in: TransactionCreate):
    data = load_portfolio()
    tx_list = data.get("transactions", [])
    next_id = data.get("next_tx_id", len(tx_list) + 1)
    
    clean_coin = tx_in.coin.strip()
    exchange = (tx_in.exchange or "BINANCE").upper().strip()
    
    # Borsada USDT çifti, cüzdanda yalın sembol. Kural burada satır arasında
    # gömülüydü ve transfer tarafı ondan habersizdi; artık tek tanım
    # `data_manager.symbol_for_location` içinde ve iki taraf da onu kullanıyor.
    symbol = symbol_for_location(clean_coin, exchange)

    category = tx_in.category or DEFAULT_CATEGORIES.get(symbol, DEFAULT_CATEGORIES.get(clean_coin.upper(), "Altcoin"))
    date_str = tx_in.date or datetime.now().strftime("%Y-%m-%d")

    tot_val = float(tx_in.qty) * float(tx_in.cost)
    live_prices = price_service.get_prices()
    fee_amount = float(tx_in.fee_amount or 0.0)
    fee_asset = (tx_in.fee_asset or "USDT").upper().strip()
    fee_usd = float(tx_in.fee_usd or 0.0)
    if fee_amount > 0 and (fee_usd == 0 or fee_usd is None):
        fee_usd = compute_fee_usd(fee_amount, fee_asset, tot_val, live_prices)

    new_tx = {
        "id": next_id,
        "date": date_str,
        "coin": symbol,
        "exchange": exchange,
        "qty": float(tx_in.qty),
        "cost": float(tx_in.cost),
        "status": tx_in.status or "Aktif",
        "notes": tx_in.notes or "",
        "category": category,
        "fee_amount": fee_amount,
        "fee_asset": fee_asset,
        "fee_usd": round(fee_usd, 4)
    }

    tx_list.append(new_tx)
    data["transactions"] = tx_list
    data["next_tx_id"] = next_id + 1
    save_portfolio(data)
    return {"success": True, "transaction": new_tx}

@app.post("/api/transactions/{tx_id}/sell")
def sell_transaction(tx_id: int, req: SellRequest):
    data = load_portfolio()
    tx_list = data.get("transactions", [])
    wallets = data.get("wallets", {"usdt_cash": 500.0})
    
    target = None
    for tx in tx_list:
        if tx["id"] == tx_id:
            target = tx
            break
            
    if not target:
        raise HTTPException(status_code=404, detail="İşlem bulunamadı")

    available_qty = float(target["qty"])
    sell_qty = min(available_qty, float(req.sell_qty))
    if sell_qty <= 0:
        raise HTTPException(status_code=400, detail="Geçersiz satış miktarı")

    sell_price = float(req.sell_price)
    sell_amount = sell_qty * sell_price
    live_prices = price_service.get_prices()

    fee_amount = float(req.fee_amount or 0.0)
    fee_asset = (req.fee_asset or "USDT").upper().strip()
    fee_usd = float(req.fee_usd or 0.0)
    if fee_amount > 0 and (fee_usd == 0 or fee_usd is None):
        fee_usd = compute_fee_usd(fee_amount, fee_asset, sell_amount, live_prices)

    net_realized_pnl = ((sell_price - float(target["cost"])) * sell_qty) - fee_usd
    date_str = req.date or datetime.now().strftime("%Y-%m-%d")
    tx_exchange = target.get("exchange", "BINANCE").upper().strip()

    # Update USDT cash (both total and exchange specific)
    cash_to_add = sell_amount - fee_usd if fee_asset == "USDT" else sell_amount
    wallets["usdt_cash"] = float(wallets.get("usdt_cash", 500.0)) + cash_to_add
    ex_cash = wallets.get("exchange_cash", {})
    ex_cash[tx_exchange] = float(ex_cash.get(tx_exchange, 0.0)) + cash_to_add
    wallets["exchange_cash"] = ex_cash
    data["wallets"] = wallets

    fee_info_str = f" | Komisyon: {fee_amount} {fee_asset} (${fee_usd:,.2f})" if fee_amount > 0 else ""

    cost_method = req.cost_method or "Konsolide Ortalama"

    if sell_qty >= available_qty:
        target["status"] = "Kapandı / İzleme"
        target["exit_price"] = sell_price
        target["exit_date"] = date_str
        target["exit_value"] = sell_amount
        target["realized_pnl_usd"] = round(net_realized_pnl, 2)
        target["fee_amount"] = fee_amount
        target["fee_asset"] = fee_asset
        target["fee_usd"] = round(fee_usd, 4)
        target["cost_method"] = cost_method
        existing_notes = target.get("notes", "")
        sale_note = f"Satıldı ({date_str} @ ${sell_price:,.4f}) | Gelir: +${sell_amount:,.2f}{fee_info_str} | Net K/Z: {'+' if net_realized_pnl >= 0 else ''}${net_realized_pnl:,.2f}"
        target["notes"] = f"{existing_notes} | {sale_note}".strip(" |")
    else:
        target["qty"] = available_qty - sell_qty
        next_id = data.get("next_tx_id", len(tx_list) + 1)
        data["next_tx_id"] = next_id + 1
        
        closed_record = {
            "id": next_id,
            "date": date_str,
            "coin": target["coin"],
            "exchange": tx_exchange,
            "qty": sell_qty,
            "cost": float(target["cost"]),
            "status": "Kapandı / İzleme",
            "exit_price": sell_price,
            "exit_date": date_str,
            "exit_value": sell_amount,
            "realized_pnl_usd": round(net_realized_pnl, 2),
            "fee_amount": fee_amount,
            "fee_asset": fee_asset,
            "fee_usd": round(fee_usd, 4),
            "cost_method": cost_method,
            "notes": f"Kısmi Satış ({date_str} @ ${sell_price:,.4f}) | Gelir: +${sell_amount:,.2f}{fee_info_str} | Net K/Z: {'+' if net_realized_pnl >= 0 else ''}${net_realized_pnl:,.2f}",
            "category": target.get("category", "Altcoin")
        }
        tx_list.append(closed_record)

    save_portfolio(data)
    return {
        "success": True,
        "cash_added": cash_to_add,
        "new_usdt_cash": wallets["usdt_cash"],
        "realized_pnl": net_realized_pnl,
        "fee_usd": fee_usd
    }

@app.put("/api/transactions/{tx_id}")
def update_transaction(tx_id: int, tx_in: TransactionUpdate):
    data = load_portfolio()
    tx_list = data.get("transactions", [])
    target = None
    for tx in tx_list:
        if tx["id"] == tx_id:
            target = tx
            break
    
    if not target:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if tx_in.date is not None:
        target["date"] = tx_in.date
    if tx_in.coin is not None:
        c = tx_in.coin.strip()
        ex = (tx_in.exchange or target.get("exchange", "BINANCE")).upper()
        if ex in ["BINANCE", "MEXC", "GATE.IO"] and not c.upper().endswith("USDT") and "/" not in c:
            target["coin"] = f"{c.upper()}USDT"
        else:
            target["coin"] = c.upper()
    if tx_in.exchange is not None:
        target["exchange"] = tx_in.exchange
    if tx_in.qty is not None:
        target["qty"] = float(tx_in.qty)
    if tx_in.cost is not None:
        target["cost"] = float(tx_in.cost)
    if tx_in.status is not None:
        target["status"] = tx_in.status
    if tx_in.notes is not None:
        target["notes"] = tx_in.notes
    if tx_in.category is not None:
        target["category"] = tx_in.category
    if tx_in.fee_amount is not None:
        target["fee_amount"] = float(tx_in.fee_amount)
    if tx_in.fee_asset is not None:
        target["fee_asset"] = tx_in.fee_asset.upper()
    if tx_in.fee_usd is not None:
        target["fee_usd"] = float(tx_in.fee_usd)

    save_portfolio(data)
    return {"success": True, "transaction": target}

@app.patch("/api/transactions/{tx_id}/status")
def toggle_transaction_status(tx_id: int):
    data = load_portfolio()
    tx_list = data.get("transactions", [])
    for tx in tx_list:
        if tx["id"] == tx_id:
            current = tx.get("status", "Aktif")
            tx["status"] = "Kapandı / İzleme" if current == "Aktif" else "Aktif"
            save_portfolio(data)
            return {"success": True, "new_status": tx["status"]}
    raise HTTPException(status_code=404, detail="Transaction not found")

@app.delete("/api/transactions/{tx_id}")
def delete_transaction(tx_id: int):
    data = load_portfolio()
    tx_list = data.get("transactions", [])
    new_list = [t for t in tx_list if t["id"] != tx_id]
    if len(new_list) == len(tx_list):
        raise HTTPException(status_code=404, detail="Transaction not found")
    data["transactions"] = new_list
    save_portfolio(data)
    return {"success": True}

@app.post("/api/wallets")
def update_wallets(w_in: WalletsUpdate):
    data = load_portfolio()
    current_wallets = data.get("wallets", {})
    
    ex_cash = w_in.exchange_cash or current_wallets.get("exchange_cash", {})
    if w_in.exchange_cash is not None:
        total_c = sum(float(v or 0.0) for v in ex_cash.values())
    elif w_in.usdt_cash is not None:
        total_c = float(w_in.usdt_cash)
        ex_cash["BINANCE"] = total_c * 0.8
        ex_cash["MEXC"] = total_c * 0.2
    else:
        total_c = float(current_wallets.get("usdt_cash", 500.0))

    data["wallets"] = {
        "usdt_cash": total_c,
        "exchange_cash": ex_cash,
        "futures_balance": float(w_in.futures_balance or 0.0),
        "margin_balance": float(w_in.margin_balance or 0.0)
    }
    save_portfolio(data)
    return {"success": True, "wallets": data["wallets"]}

# -------------------------------------------------------------
# Faz 1: Hedef Fiyat & Kâr Alma (Take-Profit) Endpoints
# -------------------------------------------------------------
@app.post("/api/targets")
def api_save_target(tgt: TargetIn):
    if not tgt.pos_key or tgt.target_price <= 0:
        raise HTTPException(status_code=400, detail="Geçersiz hedef fiyat veya varlık seçimi")
    res = save_target(tgt.pos_key, tgt.target_price, tgt.target_sell_pct or 100.0, tgt.notes or "")
    return {"success": True, "target": res}

@app.delete("/api/targets/{pos_key}")
def api_delete_target(pos_key: str):
    res = delete_target(pos_key)
    return {"success": res}

@app.post("/api/targets/{pos_key}/execute")
def api_execute_target(pos_key: str, payload: dict = Body(None)):
    sell_price = payload.get("sell_price") if payload else None
    sell_qty = payload.get("sell_qty") if payload else None
    fee_amount = float(payload.get("fee_amount", 0.0)) if payload else 0.0
    fee_asset = payload.get("fee_asset", "USDT") if payload else "USDT"
    fee_usd = float(payload.get("fee_usd", 0.0)) if payload else 0.0

    if fee_amount > 0 and (fee_usd == 0 or fee_usd is None):
        tot_val = (float(sell_qty or 1.0)) * (float(sell_price or 1.0))
        live_prices = price_service.get_prices()
        fee_usd = compute_fee_usd(fee_amount, fee_asset, tot_val, live_prices)

    cost_method = payload.get("cost_method", "Konsolide Ortalama") if payload else "Konsolide Ortalama"

    try:
        res = execute_target_sale(pos_key, sell_price=sell_price, sell_qty=sell_qty, fee_amount=fee_amount, fee_asset=fee_asset, fee_usd=fee_usd, cost_method=cost_method)
        return {"success": True, **res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class DcaBuyIn(BaseModel):
    pos_key: Optional[str] = None
    coin: str
    exchange: Optional[str] = "BINANCE"
    buy_qty: float
    buy_price: float
    invest_amount: float
    deduct_cash: Optional[bool] = True
    notes: Optional[str] = ""
    category: Optional[str] = "Altcoin"

@app.post("/api/dca/execute")
def api_execute_dca(req: DcaBuyIn):
    data = load_portfolio()
    tx_list = data.get("transactions", [])
    next_id = data.get("next_tx_id", len(tx_list) + 1)

    clean_coin = req.coin.strip()
    exchange = (req.exchange or "BINANCE").upper().strip()

    if exchange in ["BINANCE", "MEXC", "GATE.IO"] and not clean_coin.endswith("USDT") and "/" not in clean_coin:
        symbol = f"{clean_coin.upper()}USDT"
    else:
        symbol = clean_coin.upper()

    category = req.category or DEFAULT_CATEGORIES.get(symbol, DEFAULT_CATEGORIES.get(clean_coin.upper(), "Altcoin"))

    new_tx = {
        "id": next_id,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "coin": symbol,
        "exchange": exchange,
        "qty": float(req.buy_qty),
        "cost": float(req.buy_price),
        "status": "Aktif",
        "notes": req.notes or f"Akıllı DCA Alımı (${req.invest_amount:.2f})",
        "category": category
    }

    tx_list.append(new_tx)
    data["transactions"] = tx_list
    data["next_tx_id"] = next_id + 1

    if req.deduct_cash:
        wallets = data.get("wallets", {})
        exchange_cash = wallets.get("exchange_cash", {})
        ex_norm = "BINANCE" if "BINANCE" in exchange else ("MEXC" if "MEXC" in exchange else ("DEX" if "DEX" in exchange else ("GATE.IO" if "GATE" in exchange else "BINANCE")))
        current_cash = float(exchange_cash.get(ex_norm, 0.0))
        new_cash = max(0.0, current_cash - float(req.invest_amount))
        exchange_cash[ex_norm] = new_cash
        wallets["exchange_cash"] = exchange_cash
        wallets["usdt_cash"] = sum(float(v) for v in exchange_cash.values())
        data["wallets"] = wallets

    save_portfolio(data)
    return {"success": True, "transaction": new_tx}

# -------------------------------------------------------------
# 1-Click Backup & Restore Endpoints
# -------------------------------------------------------------
@app.get("/api/backup/download")
def download_backup():
    if os.path.exists(DATA_FILE):
        filename = f"portfolio_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        return FileResponse(DATA_FILE, filename=filename, media_type="application/json")
    raise HTTPException(status_code=404, detail="Yedek dosyası bulunamadı")

@app.post("/api/backup/restore")
def restore_backup(payload: dict = Body(...)):
    if not payload or "transactions" not in payload:
        raise HTTPException(status_code=400, detail="Geçersiz yedek dosyası formatı")
    
    # Save a safety backup before restoring
    today_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    safety_backup = os.path.join(BACKUP_DIR, f"pre_restore_backup_{today_str}.json")
    if os.path.exists(DATA_FILE):
        try:
            shutil.copyfile(DATA_FILE, safety_backup)
        except Exception:
            pass
        
    save_portfolio(payload)
    return {"success": True, "message": "Yedek başarıyla geri yüklendi"}

@app.get("/api/search")
def search_coin(q: str = ""):
    results = price_service.search_symbols(q, limit=12)
    return results

@app.get("/api/live-price/{symbol}")
def get_live_price(symbol: str):
    info = price_service.get_price_for_symbol(symbol)
    if info:
        return {"symbol": symbol.upper(), **info}
    return {"symbol": symbol.upper(), "price": None, "source": "Bulunamadı"}

@app.get("/api/refresh")
def force_refresh():
    price_service.update_all_prices()
    return {"success": True, "timestamp": price_service.last_update_ts}

# -------------------------------------------------------------
# FAZ 5: SETTINGS & HEALTH CHECK ENDPOINTS
# -------------------------------------------------------------
@app.get("/api/settings")
def get_settings():
    return load_settings()

@app.post("/api/settings")
def update_settings(payload: dict = Body(...)):
    # Kısmi güncelleme: gönderilmeyen bölümler korunur. Doğrudan save_settings
    # çağırmak, arayüzün göndermediği `security` (PIN) ve fiyat kaynağı
    # bölümlerini siliyordu.
    merged = merge_settings(payload)
    save_settings(merged)
    # Fiyat motoru ayarları önbelleğe alıyor; kaydedilen API adresleri ve
    # kaynak tercihleri bir sonraki turda geçerli olsun.
    price_service.invalidate_config()
    return {"success": True, "settings": merged}


# -------------------------------------------------------------
# FAZ B++: FİYAT KAYNAĞI KAYIT DEFTERİ
# -------------------------------------------------------------
@app.get("/api/price-sources")
def list_price_sources():
    """Kademe kayıt defteri + sembole özel tanımlar."""
    return {
        "registry": price_service.describe_sources(),
        "symbol_sources": get_symbol_sources(),
        "active_order": price_service.get_active_source_ids(),
    }


@app.post("/api/price-sources")
def update_price_sources(payload: dict = Body(...)):
    """Hangi kademe açık ve hangi sırada denenecek."""
    registry = payload.get("registry") or payload
    ok, err = set_price_sources(registry)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    price_service.invalidate_config()
    return {"success": True, "registry": price_service.describe_sources()}


@app.post("/api/symbol-sources/preview")
def preview_symbol_source(payload: dict = Body(...)):
    """
    Bir kaynak tanımını KAYDETMEDEN dener. Arayüz, kullanıcı "Kaydet"e
    basmadan önce fiyatın gerçekten gelip gelmediğini gösterir — yanlış
    market adı yüzünden sessizce boş kalan bir pozisyon olmasın.
    """
    symbol = payload.get("symbol", "")
    clean, err = validate_source_spec(payload.get("source") or {})
    if err:
        raise HTTPException(status_code=400, detail=err)

    info = price_service.resolve_symbol_source(clean, symbol=normalize_symbol_key(symbol))
    if not info:
        return {
            "success": False,
            "message": "Bu tanımla fiyat bulunamadı. Market adını veya kontrat adresini kontrol edin.",
        }
    return {
        "success": True,
        "price": info.get("price"),
        "change_pct": info.get("change_pct"),
        "source": info.get("source"),
        "is_dex": bool(info.get("is_dex")),
        "chain_id": info.get("chain_id"),
        "pair_address": info.get("pair_address"),
    }


@app.post("/api/symbol-sources")
def save_symbol_source(payload: dict = Body(...)):
    symbol = payload.get("symbol", "")
    ok, err = set_symbol_source(symbol, payload.get("source") or {})
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    price_service.invalidate_config()
    price_service.update_all_prices()
    return {"success": True, "symbol": normalize_symbol_key(symbol),
            "symbol_sources": get_symbol_sources()}


@app.delete("/api/symbol-sources/{symbol}")
def remove_symbol_source(symbol: str):
    removed = delete_symbol_source(symbol)
    if not removed:
        raise HTTPException(status_code=404, detail="Bu sembol için tanımlı kaynak yok.")
    price_service.invalidate_config()
    price_service.update_all_prices()
    return {"success": True, "symbol_sources": get_symbol_sources()}

@app.get("/api/health/ping")
def check_health_ping():
    return ping_services()

@app.post("/api/health/test-telegram")
def test_telegram(payload: dict = Body(...)):
    bot_token = payload.get("bot_token", "").strip()
    chat_id = payload.get("chat_id", "").strip()
    if not bot_token or not chat_id:
        raise HTTPException(status_code=400, detail="Bot Token ve Chat ID gereklidir.")
    
    import urllib.request
    import urllib.parse
    import json
    msg = "🚀 CoinTakip Canlı Terminal Test Mesajı!\n\nTelegram bot ve kanal bağlantınız başarıyla sağlandı. Fiyat alarmları ve hedef bildirimleri bu kanala iletilecektir."
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    post_data = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=post_data, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return {"success": True, "message": "Test mesajı Telegram'a başarıyla iletildi!"}
            else:
                return {"success": False, "message": data.get("description", "Telegram hatası")}
    except Exception as e:
        return {"success": False, "message": f"Telegram bağlantı hatası: {str(e)}"}

# -------------------------------------------------------------
# FAZ 6: YAPAY ZEKA FİNANSAL DANIŞMAN ENDPOINT'İ
# -------------------------------------------------------------
@app.post("/api/ai/analyze")
def analyze_with_ai(payload: dict = Body(...)):
    from ai_service import ai_advisor
    mode = payload.get("mode", "full_audit")
    question = payload.get("custom_question", "")
    return ai_advisor.analyze(mode=mode, custom_question=question)

# -------------------------------------------------------------
# FAZ 7: GERÇEKLEŞMİŞ KÂR/ZARAR & EXCEL DIŞA AKTARIM ENDPOINT'LERİ
# -------------------------------------------------------------
@app.get("/api/realized-pnl")
def get_realized_pnl():
    data = load_portfolio()
    return calculate_realized_metrics(data)

@app.get("/api/export/excel")
def export_excel():
    data = load_portfolio()
    prices = price_service.get_prices()
    excel_bytes = export_portfolio_excel(data, prices)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"CoinTakip_Portfoy_Raporu_{timestamp}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# -------------------------------------------------------------
# FAZ 8: SECURITY & PIN AUTHENTICATION MODELS & ENDPOINTS
# -------------------------------------------------------------
class PinVerifyRequest(BaseModel):
    pin: str

class PinSetupRequest(BaseModel):
    current_pin: Optional[str] = None
    new_pin: str
    auto_lock_minutes: Optional[int] = 15

class PinDisableRequest(BaseModel):
    current_pin: str

class RecoveryRequest(BaseModel):
    recovery_key: str
    new_pin: str
    auto_lock_minutes: Optional[int] = 15

class SecuritySettingsUpdate(BaseModel):
    auto_lock_minutes: Optional[int] = None
    privacy_mode: Optional[bool] = None

@app.get("/api/auth/status")
def get_auth_status():
    settings = load_settings()
    sec = settings.get("security", {})
    return {
        "pin_enabled": sec.get("pin_enabled", False),
        "auto_lock_minutes": sec.get("auto_lock_minutes", 15),
        "privacy_mode": sec.get("privacy_mode", False),
        "recovery_available": bool(sec.get("recovery_hash", ""))
    }

@app.post("/api/auth/verify")
def api_verify_pin(req: PinVerifyRequest):
    if not req.pin:
        raise HTTPException(status_code=400, detail="PIN gereklidir.")
    valid = verify_pin(req.pin)
    if not valid:
        raise HTTPException(status_code=401, detail="Hatalı PIN kodu.")
    import secrets as _sec
    session_token = _sec.token_urlsafe(32)
    return {"success": True, "message": "PIN doğrulandı", "session_token": session_token}

@app.post("/api/auth/setup")
def api_setup_pin(req: PinSetupRequest):
    settings = load_settings()
    sec = settings.get("security", {})
    pin_enabled = sec.get("pin_enabled", False)

    clean_new_pin = str(req.new_pin).strip()
    if not clean_new_pin or len(clean_new_pin) < 4:
        raise HTTPException(status_code=400, detail="PIN en az 4 haneli olmalıdır.")

    if pin_enabled:
        if not req.current_pin:
            raise HTTPException(status_code=400, detail="Mevcut PIN gereklidir.")
        ok = change_pin(req.current_pin, clean_new_pin)
        if not ok:
            raise HTTPException(status_code=401, detail="Mevcut PIN hatalı.")
        return {"success": True, "message": "PIN başarıyla güncellendi."}
    else:
        result = set_pin(clean_new_pin, auto_lock_minutes=req.auto_lock_minutes or 15)
        return {"success": True, "message": "PIN başarıyla ayarlandı.", "recovery_key": result.get("recovery_key")}

@app.post("/api/auth/recover")
def api_recover_pin(req: RecoveryRequest):
    clean_new_pin = str(req.new_pin).strip()
    if not clean_new_pin or len(clean_new_pin) < 4:
        raise HTTPException(status_code=400, detail="Yeni PIN en az 4 haneli olmalıdır.")
    result = reset_pin_with_recovery(req.recovery_key, clean_new_pin, req.auto_lock_minutes or 15)
    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error", "Geçersiz kurtarma anahtarı."))
    return {"success": True, "message": "PIN başarıyla sıfırlandı.", "recovery_key": result.get("recovery_key")}

@app.post("/api/auth/disable")
def api_disable_pin(req: PinDisableRequest):
    if not req.current_pin:
        raise HTTPException(status_code=400, detail="Mevcut PIN gereklidir.")
    ok = disable_pin(req.current_pin)
    if not ok:
        raise HTTPException(status_code=401, detail="Mevcut PIN hatalı.")
    return {"success": True, "message": "PIN koruması kaldırıldı."}

@app.post("/api/auth/settings")
def api_update_security_settings(req: SecuritySettingsUpdate):
    sec = update_security_settings(auto_lock_minutes=req.auto_lock_minutes, privacy_mode=req.privacy_mode)
    return {"success": True, "security": sec}

static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

# -------------------------------------------------------------
# FAZ D: ÖNBELLEK KIRMA (cache busting)
# -------------------------------------------------------------
# Sorun: `app.js` elle yazılmış `?v=2.2` etiketiyle sunuluyordu. Sürüm
# elle güncellenmediği sürece tarayıcı eski dosyayı önbellekten veriyor;
# kullanıcı düzeltilmiş kodu görmüyor ama bunu anlamasının bir yolu yok.
#
# Çözüm: index.html sunulurken içindeki her yerel /static/ referansına
# dosyanın İÇERİK HASH'i ekleniyor. Dosya değişince adres değişir, tarayıcı
# yeniden indirir; değişmezse önbellekten gelir. Elle sürüm yönetimi yok.
_index_cache = {"imza": None, "html": None}

_STATIK_REF = re.compile(r'((?:src|href)=")(/static/[^"?]+)(\?[^"]*)?(")')


def _statik_dosya_yolu(url_yolu: str) -> str:
    """/static/vendor/x.js → <static_dir>/vendor/x.js"""
    return os.path.join(static_dir, url_yolu[len("/static/"):].replace("/", os.sep))


def _icerik_hash(dosya_yolu: str) -> str:
    try:
        with open(dosya_yolu, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:8]
    except OSError:
        return ""


def _index_html_uret() -> str:
    index_file = os.path.join(static_dir, "index.html")
    with open(index_file, "r", encoding="utf-8") as f:
        html = f.read()

    def degistir(m):
        onek, yol, _eski_surum, sonek = m.groups()
        h = _icerik_hash(_statik_dosya_yolu(yol))
        return f"{onek}{yol}?v={h}{sonek}" if h else f"{onek}{yol}{sonek}"

    return _STATIK_REF.sub(degistir, html)


def _index_imzasi() -> tuple:
    """index.html ve referans verdiği yerel dosyaların değişiklik damgası."""
    index_file = os.path.join(static_dir, "index.html")
    parcalar = []
    try:
        parcalar.append(os.path.getmtime(index_file))
        with open(index_file, "r", encoding="utf-8") as f:
            for m in _STATIK_REF.finditer(f.read()):
                try:
                    parcalar.append(os.path.getmtime(_statik_dosya_yolu(m.group(2))))
                except OSError:
                    parcalar.append(0)
    except OSError:
        return ()
    return tuple(parcalar)


@app.get("/")
def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_file):
        return {"message": "Crypto Terminal Frontend is loading..."}

    imza = _index_imzasi()
    if _index_cache["imza"] != imza:
        _index_cache["html"] = _index_html_uret()
        _index_cache["imza"] = imza
        logger.debug("index.html yeniden üretildi (önbellek kırma damgaları güncellendi).")

    # HTML'in kendisi önbelleğe alınmamalı; aksi halde yeni sürüm etiketleri
    # tarayıcıya hiç ulaşmaz ve önbellek kırma anlamsızlaşır.
    return Response(
        content=_index_cache["html"],
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )

if __name__ == "__main__":
    import webbrowser
    import threading
    def open_browser():
        time.sleep(1.0)
        webbrowser.open("http://localhost:8000")
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
