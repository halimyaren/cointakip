import urllib.request
import urllib.parse
import json
import time
import threading

from log_config import get_logger

logger = get_logger("price_service")

# =====================================================================
# FİYAT KAYNAĞI KAYIT DEFTERİ (FAZ B++)
# =====================================================================
# Eskiden kademeler koda gömülüydü: Binance → MEXC → sabit
# ["RDNT", "CATERPILLAR", "CPL"] listesi. Bu, uygulamayı tek bir kişinin
# portföyüne bağlıyordu; başka bir kullanıcının bilinmeyen bir coini
# hiçbir zaman fiyat alamıyordu.
#
# Artık kaynaklar bir kayıt defteridir ve iki katmanda yapılandırılır:
#
#   1. settings["price_sources"]  — hangi kademe açık, hangi sırada
#   2. settings["symbol_sources"] — belirli bir sembol için özel kaynak
#
# İkinci katman esas esnekliktir: hiçbir kademede bulunamayan bir coin
# (örn. yalnızca WhiteBIT'te işlem gören SCM) kod değiştirmeden,
# arayüzden tanımlanarak çözülür.
# =====================================================================

CEX_SOURCE_IDS = ("binance", "mexc", "whitebit", "gateio")
DEX_SOURCE_ID = "dex"

SOURCE_LABELS = {
    "binance": "Binance",
    "mexc": "MEXC",
    "whitebit": "WhiteBIT",
    "gateio": "Gate.io",
    "dex": "DexScreener (On-Chain)",
}

# Kaynak yapılandırması bu aralıkta bir kez diskten okunur (saniye).
# Arka plan döngüsü 4 sn'de bir dönüyor; her turda settings.json açmanın
# anlamı yok.
CONFIG_TTL = 10.0

# Portföy izleme listesi bu aralıkta yenilenir (saniye).
WATCHLIST_TTL = 20.0

# Zincir üstü (DEX) sorgular bu aralıkta tekrarlanır (saniye).
# DexScreener'a her 4 sn'de bir sembol başına istek atmak hem gereksiz
# hem de hız sınırına takılma riski.
DEX_REFRESH_TTL = 60.0


def _norm_symbol(raw):
    """SCM_USDT / BTC-USDT / btc/usdt → SCMUSDT biçimine indirger."""
    return str(raw or "").upper().replace("_", "").replace("-", "").replace("/", "").strip()


def _derive_open(last_price, change_pct):
    """Borsa yalnızca yüzde değişim veriyorsa açılış fiyatını türetir."""
    factor = 1.0 + (float(change_pct) / 100.0)
    if factor == 0:
        return last_price
    return last_price / factor


class SmartPriceDiscoveryEngine:
    def __init__(self):
        self.prices = {} # { "BTCUSDT": { "price": ..., "open_price": ..., "change_pct": ..., "source": "BINANCE", "is_dead": False, "updated_at": ... } }
        self.symbol_search_index = []
        self.sparkline_cache = {}
        self.is_running = False
        self.lock = threading.Lock()
        self.last_update_ts = 0

        self._config_cache = None
        self._config_ts = 0.0
        self._watchlist_cache = []
        self._watchlist_ts = 0.0
        self._dex_last_fetch = {}   # { "SCMUSDT": timestamp }

    # -----------------------------------------------------------------
    # Yaşam döngüsü
    # -----------------------------------------------------------------
    def start_background_updater(self):
        if self.is_running:
            return
        self.is_running = True
        self.update_all_prices()

        thread = threading.Thread(target=self._background_loop, daemon=True)
        thread.start()
        aktif = " → ".join(SOURCE_LABELS.get(s, s) for s in self.get_active_source_ids())
        logger.info("Akıllı Fiyat Keşif Motoru aktif (%s, 4 sn aralık).", aktif or "kaynak yok")

    def _background_loop(self):
        while self.is_running:
            try:
                time.sleep(4)
                self.update_all_prices()
            except Exception as e:
                # 4 sn'de bir dönen döngü — WARNING seviyesinde tutuluyor ki
                # geçici ağ kesintileri log dosyasını doldurmasın.
                logger.warning("Fiyat güncelleme döngüsünde hata: %s", e)
                time.sleep(2)

    def fetch_url_json(self, url, timeout=5):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # -----------------------------------------------------------------
    # Yapılandırma
    # -----------------------------------------------------------------
    def _default_config(self):
        return {
            "sources": {
                "binance": {"enabled": True, "order": 1},
                "mexc": {"enabled": True, "order": 2},
                "whitebit": {"enabled": True, "order": 3},
                "gateio": {"enabled": False, "order": 4},
                "dex": {"enabled": True, "order": 5},
            },
            "api_urls": {},
            "symbol_sources": {},
        }

    def load_config(self, force=False):
        """
        settings.json'dan kaynak kayıt defterini okur.

        Ayarlar okunamazsa motor durmaz — varsayılan kademelerle devam eder.
        Bu bilinçli: fiyat motoru, bozuk bir ayar dosyası yüzünden sessizce
        körleşmemeli.
        """
        now = time.time()
        if not force and self._config_cache and (now - self._config_ts) < CONFIG_TTL:
            return self._config_cache

        cfg = self._default_config()
        try:
            from data_manager import load_settings
            s = load_settings() or {}
            saved_sources = s.get("price_sources") or {}
            for sid, row in saved_sources.items():
                if not isinstance(row, dict):
                    continue
                base = cfg["sources"].get(sid, {"enabled": False, "order": 99})
                cfg["sources"][sid] = {
                    "enabled": bool(row.get("enabled", base.get("enabled", False))),
                    "order": int(row.get("order", base.get("order", 99))),
                }
            cfg["api_urls"] = s.get("api_urls") or {}
            cfg["symbol_sources"] = s.get("symbol_sources") or {}
        except Exception as e:
            logger.warning("Kaynak ayarları okunamadı, varsayılanlar kullanılıyor: %s", e)

        self._config_cache = cfg
        self._config_ts = now
        return cfg

    def invalidate_config(self):
        """Ayarlar kaydedildiğinde çağrılır; bir sonraki tur yeniden okur."""
        self._config_ts = 0.0
        self._watchlist_ts = 0.0

    def get_active_source_ids(self):
        """Etkin kaynakları kullanıcı sırasına göre döndürür."""
        cfg = self.load_config()
        rows = [(sid, row) for sid, row in cfg["sources"].items() if row.get("enabled")]
        rows.sort(key=lambda kv: kv[1].get("order", 99))
        return [sid for sid, _ in rows]

    def describe_sources(self):
        """Arayüzün ayarlar ekranı için kaynak listesi."""
        cfg = self.load_config()
        out = []
        for sid, row in cfg["sources"].items():
            out.append({
                "id": sid,
                "label": SOURCE_LABELS.get(sid, sid),
                "enabled": bool(row.get("enabled")),
                "order": int(row.get("order", 99)),
                "kind": "dex" if sid == DEX_SOURCE_ID else "cex",
            })
        out.sort(key=lambda r: r["order"])
        return out

    # -----------------------------------------------------------------
    # Borsa adaptörleri — hepsi aynı sözleşmeyi uygular:
    #   fetch(api_urls) -> ( { "BTCUSDT": {...} }, [arama_index_kayitlari] )
    # -----------------------------------------------------------------
    def _adapter_binance(self, api_urls):
        prices, index = {}, []
        urls = [
            api_urls.get("binance_ticker") or "https://api.binance.com/api/v3/ticker/24hr",
            "https://data-api.binance.vision/api/v3/ticker/24hr",
        ]
        for b_url in urls:
            try:
                data = self.fetch_url_json(b_url, timeout=5)
            except Exception as e:
                logger.debug("Binance kaynağı yanıt vermedi (%s): %s", b_url, e)
                continue
            for item in data:
                sym = _norm_symbol(item.get("symbol"))
                try:
                    last_p = float(item.get("lastPrice", 0.0))
                    vol = float(item.get("volume", 0.0))
                    open_p = float(item.get("openPrice", last_p))
                    chg_pct = float(item.get("priceChangePercent", 0.0))
                except (ValueError, TypeError):
                    continue
                # Hacim süzgeci yalnızca Binance kademesinde uygulanır:
                # borsa, işlem görmeyen çiftleri de listede tuttuğu için
                # ölü fiyatların portföye sızmasını engeller.
                if last_p > 0 and vol > 0.01:
                    prices[sym] = {
                        "price": last_p,
                        "open_price": open_p,
                        "change_pct": chg_pct,
                        "source": "BINANCE",
                        "is_dead": False,
                        "updated_at": time.time(),
                    }
                    if sym.endswith("USDT"):
                        base = sym[:-4]
                        index.append({"symbol": sym, "base": base, "display": f"{base}/USDT",
                                      "exchange": "BINANCE", "price": last_p})
            break
        return prices, index

    def _adapter_mexc(self, api_urls):
        prices, index = {}, []
        url = api_urls.get("mexc_ticker") or "https://api.mexc.com/api/v3/ticker/24hr"
        try:
            data = self.fetch_url_json(url, timeout=5)
        except Exception as e:
            logger.debug("MEXC kaynağı yanıt vermedi: %s", e)
            return prices, index
        for item in data:
            sym = _norm_symbol(item.get("symbol"))
            try:
                last_p = float(item.get("lastPrice", 0.0))
                open_p = float(item.get("openPrice", last_p))
                chg_pct = float(item.get("priceChangePercent", 0.0))
            except (ValueError, TypeError):
                continue
            if last_p > 0:
                prices[sym] = {
                    "price": last_p,
                    "open_price": open_p,
                    "change_pct": chg_pct,
                    "source": "MEXC",
                    "is_dead": False,
                    "updated_at": time.time(),
                }
                if sym.endswith("USDT"):
                    base = sym[:-4]
                    index.append({"symbol": sym, "base": base, "display": f"{base}/USDT",
                                  "exchange": "MEXC", "price": last_p})
        return prices, index

    def _adapter_whitebit(self, api_urls):
        prices, index = {}, []
        url = api_urls.get("whitebit_ticker") or "https://whitebit.com/api/v4/public/ticker"
        try:
            data = self.fetch_url_json(url, timeout=6)
        except Exception as e:
            logger.debug("WhiteBIT kaynağı yanıt vermedi: %s", e)
            return prices, index
        # WhiteBIT sözlük döndürür: { "BTC_USDT": {...}, ... }
        for market, item in (data or {}).items():
            if not isinstance(item, dict) or item.get("isFrozen"):
                continue
            sym = _norm_symbol(market)
            try:
                last_p = float(item.get("last_price", 0.0))
                chg_pct = float(item.get("change", 0.0))
            except (ValueError, TypeError):
                continue
            if last_p > 0:
                prices[sym] = {
                    "price": last_p,
                    "open_price": _derive_open(last_p, chg_pct),
                    "change_pct": chg_pct,
                    "source": "WHITEBIT",
                    "market": market,
                    "is_dead": False,
                    "updated_at": time.time(),
                }
                if sym.endswith("USDT"):
                    base = sym[:-4]
                    index.append({"symbol": sym, "base": base, "display": f"{base}/USDT",
                                  "exchange": "WHITEBIT", "price": last_p})
        return prices, index

    def _adapter_gateio(self, api_urls):
        prices, index = {}, []
        url = api_urls.get("gateio_ticker") or "https://api.gateio.ws/api/v4/spot/tickers"
        try:
            data = self.fetch_url_json(url, timeout=6)
        except Exception as e:
            logger.debug("Gate.io kaynağı yanıt vermedi: %s", e)
            return prices, index
        for item in data or []:
            if not isinstance(item, dict):
                continue
            market = item.get("currency_pair", "")
            sym = _norm_symbol(market)
            try:
                last_p = float(item.get("last", 0.0) or 0.0)
                chg_pct = float(item.get("change_percentage", 0.0) or 0.0)
            except (ValueError, TypeError):
                continue
            if last_p > 0:
                prices[sym] = {
                    "price": last_p,
                    "open_price": _derive_open(last_p, chg_pct),
                    "change_pct": chg_pct,
                    "source": "GATE.IO",
                    "market": market,
                    "is_dead": False,
                    "updated_at": time.time(),
                }
                if sym.endswith("USDT"):
                    base = sym[:-4]
                    index.append({"symbol": sym, "base": base, "display": f"{base}/USDT",
                                  "exchange": "GATE.IO", "price": last_p})
        return prices, index

    def _run_adapter(self, source_id, api_urls):
        fn = {
            "binance": self._adapter_binance,
            "mexc": self._adapter_mexc,
            "whitebit": self._adapter_whitebit,
            "gateio": self._adapter_gateio,
        }.get(source_id)
        if not fn:
            return {}, []
        try:
            return fn(api_urls)
        except Exception as e:
            logger.warning("Kaynak '%s' beklenmedik hata verdi: %s", source_id, e)
            return {}, []

    # -----------------------------------------------------------------
    # Zincir üstü arama
    # -----------------------------------------------------------------
    # DexScreener arama uç noktası yalnızca TOKEN kontratıyla eşleşir.
    # Kullanıcının elindeki adres genellikle DexScreener URL'sinden kopyalanan
    # HAVUZ (pair) adresidir; bu durumda arama boş döner. Aşağıdaki zincirler
    # için özel uç nokta denenir.
    COMMON_CHAINS = ("ethereum", "bsc", "base", "arbitrum", "polygon", "solana")

    @staticmethod
    def _looks_like_address(text):
        t = str(text or "").strip()
        if t.lower().startswith("0x") and len(t) == 42:
            return True
        # Solana adresleri base58, 32-44 karakter, ayraç içermez
        return len(t) >= 32 and t.isalnum()

    def _pair_to_price(self, top):
        """DexScreener havuz kaydını normalize edilmiş fiyat sözlüğüne çevirir."""
        p_usd = float(top.get("priceUsd", 0) or 0)
        if p_usd <= 0:
            return None

        chg_24h = float(top.get("priceChange", {}).get("h24", 0) or 0)
        dex_name = top.get("dexId", "DEX").capitalize()
        chain = top.get("chainId", "chain").upper()
        liq = float(top.get("liquidity", {}).get("usd", 0) or 0)
        base_sym = (top.get("baseToken", {}).get("symbol") or "").upper()
        base_name = top.get("baseToken", {}).get("name", base_sym)
        quote_sym = top.get("quoteToken", {}).get("symbol", "USD")

        chain_id = (top.get("chainId") or "bsc").lower()
        pair_addr = top.get("pairAddress") or ""
        dex_url = top.get("url") or f"https://dexscreener.com/{chain_id}/{pair_addr}"
        embed_url = f"https://dexscreener.com/{chain_id}/{pair_addr}?embed=1&theme=dark&trades=0&info=0"

        dextools_chain = "bnb" if chain_id in ["bsc", "binance"] else ("ether" if chain_id in ["ethereum", "eth"] else chain_id)
        dextools_url = f"https://www.dextools.io/app/{dextools_chain}/pair-explorer/{pair_addr}" if pair_addr else dex_url

        open_p = p_usd / (1.0 + (chg_24h / 100.0)) if (1.0 + (chg_24h / 100.0)) != 0 else p_usd
        return {
            "price": p_usd,
            "open_price": open_p,
            "change_pct": chg_24h,
            "source": f"DEX ({chain} {dex_name})",
            "base_symbol": base_sym,
            "base_name": base_name,
            "quote_symbol": quote_sym,
            "is_dead": False,
            "liquidity_usd": liq,
            "is_dex": True,
            "chain_id": chain_id,
            "pair_address": pair_addr,
            "dex_url": dex_url,
            "embed_url": embed_url,
            "dextools_url": dextools_url,
            "updated_at": time.time()
        }

    def fetch_dex_pair(self, address):
        """
        Havuz (pair) adresinden fiyat çeker. Zincir bilinmediği için yaygın
        ağlar sırayla denenir; ilk yanıt veren kazanır.
        """
        addr = str(address or "").strip()
        if not self._looks_like_address(addr):
            return None
        for chain in self.COMMON_CHAINS:
            try:
                data = self.fetch_url_json(
                    f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{addr}", timeout=4
                )
            except Exception:
                continue
            pairs = (data or {}).get("pairs") or []
            if pairs:
                result = self._pair_to_price(pairs[0])
                if result:
                    return result
        return None

    def fetch_dex_screener(self, query):
        """
        Deep scan across all DEXes (PancakeSwap, Uniswap, Raydium, Base, Arbitrum, BSC, Solana, Ethereum)
        Supports Token Name, Symbol, Pair (CPL/WBNB), or Contract Address.
        """
        try:
            clean = query.strip()
            for sfx in ["/USDT", "/WBNB", "/USD", "/WETH", "/USDC", "USDT", "USDC", "WBNB"]:
                if clean.upper().endswith(sfx) and len(clean) > len(sfx):
                    clean = clean[:-len(sfx)].strip("/ ")
                    break

            base_url = (self.load_config().get("api_urls") or {}).get("dex_screener") \
                or "https://api.dexscreener.com/latest/dex/search"
            url = f"{base_url}?q={urllib.parse.quote(clean)}"
            data = self.fetch_url_json(url, timeout=5)
            pairs = data.get("pairs", [])
            if not pairs:
                # Arama boş döndü. Girilen değer bir HAVUZ adresi olabilir —
                # arama uç noktası yalnızca token kontratıyla eşleştiği için
                # bu durumda havuz uç noktasını deneriz.
                return self.fetch_dex_pair(clean)

            exact_matches = []
            q_up = clean.upper()
            for p in pairs:
                base_sym = (p.get("baseToken", {}).get("symbol") or "").upper()
                base_name = (p.get("baseToken", {}).get("name") or "").upper()
                base_addr = (p.get("baseToken", {}).get("address") or "").lower()
                if base_sym == q_up or base_name == q_up or base_addr == clean.lower():
                    exact_matches.append(p)

            target_list = exact_matches if exact_matches else pairs
            valid_pairs = [p for p in target_list if float(p.get("liquidity", {}).get("usd", 0) or 0) > 10]
            if not valid_pairs:
                valid_pairs = target_list

            valid_pairs.sort(key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
            return self._pair_to_price(valid_pairs[0])
        except Exception as e:
            logger.debug("DexScreener sorgusu başarısız (%s): %s", query, e)
        return None

    # -----------------------------------------------------------------
    # Sembol başına özel kaynak çözümleme
    # -----------------------------------------------------------------
    def resolve_symbol_source(self, spec, symbol="", adapter_cache=None):
        """
        Tek bir sembol tanımını fiyata çevirir. Arayüzdeki "Fiyat kaynağı
        tanımla" akışı da kaydetmeden önce bunu çağırarak önizleme alır.

        Desteklenen tanımlar:
          {"type": "cex",    "source": "whitebit", "market": "SCM_USDT"}
          {"type": "dex",    "query": "0x8353..." veya "CPL"}
          {"type": "manual", "price": 0.0000034}
        """
        if not isinstance(spec, dict):
            return None
        stype = str(spec.get("type", "")).lower()

        if stype == "manual":
            try:
                price = float(spec.get("price", 0) or 0)
            except (ValueError, TypeError):
                return None
            if price <= 0:
                return None
            return {
                "price": price,
                "open_price": price,
                "change_pct": 0.0,
                "source": "MANUEL",
                "is_manual": True,
                "is_dead": False,
                "updated_at": time.time(),
            }

        if stype == "dex":
            query = spec.get("query") or spec.get("contract") or symbol
            if not query:
                return None
            info = self.fetch_dex_screener(query)
            if info:
                info = dict(info)
                # Adresle yapılan eşleşme kesindir; sembolle yapılan değildir.
                info["match_by"] = "address" if self._looks_like_address(query) else "symbol"
            return info

        if stype == "cex":
            source_id = str(spec.get("source", "")).lower()
            if source_id not in CEX_SOURCE_IDS:
                return None
            market = spec.get("market") or symbol
            api_urls = self.load_config().get("api_urls") or {}
            if adapter_cache is None:
                adapter_cache = {}
            if source_id not in adapter_cache:
                adapter_cache[source_id] = self._run_adapter(source_id, api_urls)[0]
            found = adapter_cache[source_id].get(_norm_symbol(market))
            if found:
                # Kullanıcı bu kaynağı açıkça seçtiği için etiketi koruyoruz.
                out = dict(found)
                out["pinned_source"] = source_id
                return out
            return None

        return None

    # -----------------------------------------------------------------
    # İzleme listesi (portföyden türetilir — artık sabit liste yok)
    # -----------------------------------------------------------------
    def get_watchlist(self, force=False):
        now = time.time()
        if not force and self._watchlist_cache and (now - self._watchlist_ts) < WATCHLIST_TTL:
            return self._watchlist_cache

        symbols = []
        try:
            from data_manager import load_portfolio
            data = load_portfolio() or {}
            seen = set()
            for tx in data.get("transactions", []):
                raw = str(tx.get("coin", "")).upper().strip()
                if not raw or raw in seen:
                    continue
                seen.add(raw)
                symbols.append(raw)
        except Exception as e:
            logger.debug("İzleme listesi portföyden okunamadı: %s", e)

        self._watchlist_cache = symbols
        self._watchlist_ts = now
        return symbols

    def _store(self, prices, symbol, info):
        """Bir fiyatı tüm arama biçimleriyle (SCM, SCMUSDT, taban) yazar."""
        sym = _norm_symbol(symbol)
        base = sym[:-4] if sym.endswith("USDT") else sym
        prices[sym] = info
        prices[base] = info
        prices[f"{base}USDT"] = info
        b_sym = info.get("base_symbol")
        if b_sym:
            b_norm = _norm_symbol(b_sym)
            prices[b_norm] = info
            prices[f"{b_norm}USDT"] = info

    # -----------------------------------------------------------------
    # Ana güncelleme turu
    # -----------------------------------------------------------------
    def update_all_prices(self):
        cfg = self.load_config()
        api_urls = cfg.get("api_urls") or {}
        symbol_sources = cfg.get("symbol_sources") or {}
        active = self.get_active_source_ids()

        new_prices = {}
        new_search = []
        adapter_cache = {}

        # 1) Merkezi borsa kademeleri — kullanıcı sırasına göre, ilk bulan kazanır
        for source_id in active:
            if source_id == DEX_SOURCE_ID:
                continue
            prices, index = self._run_adapter(source_id, api_urls)
            adapter_cache[source_id] = prices
            for sym, info in prices.items():
                if sym not in new_prices:
                    new_prices[sym] = info
            new_search.extend(index)
            if not prices:
                logger.debug("Kademe '%s' hiç fiyat döndürmedi.", source_id)

        if not new_prices:
            logger.warning("Hiçbir merkezi borsa kademesi fiyat döndürmedi; "
                           "yalnızca zincir üstü ve özel tanımlı kaynaklara güveniliyor.")

        # 2) Sembole özel tanımlar — kademe sonucunu EZER.
        #    Kullanıcı bir coin için kaynağı elle seçtiyse, borsada aynı adlı
        #    başka bir çift bulunsa bile onun tercihi geçerlidir. (Eskiden bu,
        #    koda gömülü `"RDNT" not in sym` kontrolüyle yapılıyordu.)
        for symbol, spec in symbol_sources.items():
            now = time.time()
            spec_type = str((spec or {}).get("type", "")).lower()
            if spec_type == "dex":
                # DEX sorguları pahalı; sembol başına TTL uygulanır.
                key = _norm_symbol(symbol)
                if (now - self._dex_last_fetch.get(key, 0)) < DEX_REFRESH_TTL:
                    with self.lock:
                        cached = self.prices.get(key)
                    if cached:
                        self._store(new_prices, symbol, cached)
                        continue
                self._dex_last_fetch[_norm_symbol(symbol)] = now
            info = self.resolve_symbol_source(spec, symbol=symbol, adapter_cache=adapter_cache)
            if info:
                self._store(new_prices, symbol, info)
            else:
                logger.debug("Tanımlı kaynak '%s' için sonuç vermedi: %s", symbol, spec)

        # 3) Hiçbir kademede bulunamayan portföy sembolleri için zincir üstü tarama.
        #    Eskiden bu, elle yazılmış ["RDNT", "CATERPILLAR", "CPL"] listesiydi.
        if DEX_SOURCE_ID in active:
            now = time.time()
            for raw in self.get_watchlist():
                sym = _norm_symbol(raw)
                base = sym[:-4] if sym.endswith("USDT") else sym
                # DİKKAT: Merkezi borsa adaptörleri fiyatı yalnızca tam market
                # adıyla yazar ("BNBUSDT"), çıplak tabanla değil ("BNB").
                # Cüzdanda tutulan BNB/SOL/ETH gibi pozisyonlar portföyde
                # çıplak sembolle kayıtlı olduğu için, taban+USDT biçimi de
                # kontrol edilmezse bunlar "bulunamadı" sayılıp yanlışlıkla
                # zincir üstü bir havuz fiyatına düşüyordu.
                if any(k in new_prices for k in (sym, base, f"{base}USDT")):
                    continue
                if raw in symbol_sources or base in symbol_sources or sym in symbol_sources:
                    continue  # zaten 2. adımda ele alındı
                if (now - self._dex_last_fetch.get(sym, 0)) < DEX_REFRESH_TTL:
                    with self.lock:
                        cached = self.prices.get(sym)
                    if cached:
                        self._store(new_prices, raw, cached)
                    continue
                self._dex_last_fetch[sym] = now
                dex_res = self.fetch_dex_screener(base) or self.fetch_dex_screener(raw)
                if dex_res:
                    # DİKKAT: Bu eşleşme yalnızca SEMBOL adına dayanır ve
                    # sembol adları zincirler arasında benzersiz DEĞİLDİR.
                    # Gerçek örnek: kullanıcının SCM'i Ethereum'daki Scamfari,
                    # ama sembol araması Solana'daki "Social Capital Markets"
                    # tokenını buluyor. Fiyat makul göründüğü için hata fark
                    # edilmiyor. Bu yüzden eşleşmenin nasıl kurulduğunu
                    # işaretliyoruz; arayüz kullanıcıyı uyarabilsin.
                    dex_res = dict(dex_res)
                    dex_res["match_by"] = "symbol"
                    self._store(new_prices, raw, dex_res)
                else:
                    logger.debug("Portföy sembolü hiçbir kaynakta bulunamadı: %s", raw)

        with self.lock:
            if new_prices:
                self.prices.update(new_prices)
                if new_search:
                    self.symbol_search_index = new_search
                self.last_update_ts = time.time()

    def get_prices(self):
        with self.lock:
            return dict(self.prices)

    def get_price_for_symbol(self, symbol):
        sym = _norm_symbol(symbol)
        lookup = sym if sym.endswith("USDT") else f"{sym}USDT"
        base = lookup[:-4]

        # Kullanıcı bu sembol için kaynak tanımladıysa o her şeyin önündedir.
        symbol_sources = self.load_config().get("symbol_sources") or {}
        spec = symbol_sources.get(sym) or symbol_sources.get(base) or symbol_sources.get(symbol)
        if spec:
            info = self.resolve_symbol_source(spec, symbol=base)
            if info:
                with self.lock:
                    self._store(self.prices, base, info)
                return info

        with self.lock:
            for key in (lookup, sym, base):
                if key in self.prices:
                    return self.prices[key]

        dex_res = self.fetch_dex_screener(base) or self.fetch_dex_screener(sym)
        if dex_res:
            with self.lock:
                self._store(self.prices, base, dex_res)
            return dex_res

        # Hiçbir kaynak bulunamadı. DİKKAT: burada fiyat olarak maliyet
        # döndürmüyoruz — çağıran taraf `no_source` bayrağını görüp durumu
        # kullanıcıya açıkça bildirmeli. Sessizce maliyeti canlı fiyat gibi
        # göstermek, pozisyonu kalıcı olarak "%0.00 başabaş" gösteriyordu.
        return {
            "price": 0.0,
            "open_price": 0.0,
            "change_pct": 0.0,
            "source": "Kaynak Yok",
            "no_source": True,
            "is_dead": True,
            "updated_at": time.time(),
        }

    def get_sparkline_7d(self, symbol, live_price=0.0, change_24h=0.0):
        """
        Returns a dict: { "points": [p1, p2, ..., p7], "change_7d_pct": X.X }
        Cached in RAM for 15 minutes to preserve exchange rate limits.
        """
        sym = symbol.upper().strip()
        lookup = sym if sym.endswith("USDT") else f"{sym}USDT"
        now = time.time()

        with self.lock:
            cached = self.sparkline_cache.get(lookup)
            if cached and (now - cached.get("updated_at", 0) < 900): # 15 min TTL
                # update last point with latest live price
                pts = list(cached["points"])
                if live_price > 0 and len(pts) > 0:
                    pts[-1] = float(live_price)
                cached["points"] = pts
                return cached

        # Attempt to fetch 7-day daily closes from Binance
        try:
            url = f"https://api.binance.com/api/v3/klines?symbol={lookup}&interval=1d&limit=7"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) >= 2:
                    points = [float(k[4]) for k in data]
                    if live_price > 0:
                        points[-1] = float(live_price)
                    first_p = points[0]
                    last_p = points[-1]
                    chg_7d = ((last_p - first_p) / first_p * 100.0) if first_p > 0 else 0.0
                    res = {
                        "points": points,
                        "change_7d_pct": round(chg_7d, 2),
                        "min_price": min(points),
                        "max_price": max(points),
                        "updated_at": now
                    }
                    with self.lock:
                        self.sparkline_cache[lookup] = res
                    return res
        except Exception:
            pass

        # Fallback for DEX / synthetic tokens (derive smooth 7-point curve from 24h trend)
        lp = float(live_price) if live_price > 0 else 1.0
        chg = float(change_24h)
        step = (chg / 100.0) / 3.0
        # DİKKAT: Burada round(..., 8) KULLANILMAZ. Nano fiyatlı DEX tokenları
        # (CPL ~2.3e-09, RDNT ~4e-04) 8 ondalığa yuvarlandığında tüm ara noktalar
        # 0.0'a çöküyordu; grafik düz sıfır çizgisi + son noktada ani sıçrama
        # olarak görünüyordu. Ham float hassasiyeti korunur, biçimlendirmeyi
        # frontend (formatPrice) yapar.
        points = [
            lp * (1.0 - (step * (6 - i) * 0.45)) for i in range(7)
        ]
        points[-1] = lp
        chg_7d = ((points[-1] - points[0]) / points[0] * 100.0) if points[0] > 0 else 0.0
        res = {
            "points": points,
            "change_7d_pct": round(chg_7d, 2),
            "min_price": min(points),
            "max_price": max(points),
            "updated_at": now
        }
        with self.lock:
            self.sparkline_cache[lookup] = res
        return res

    def search_symbols(self, query, limit=15):
        q = query.upper().strip()
        if not q:
            return []

        matches = []
        with self.lock:
            for item in self.symbol_search_index:
                base = item["base"]
                sym = item["symbol"]
                if base == q or sym == q:
                    matches.insert(0, item)
                elif base.startswith(q) or sym.startswith(q):
                    matches.append(item)
                elif q in base or q in sym:
                    matches.append(item)
                if len(matches) >= limit:
                    break

        # If query matches an exact base symbol (e.g. ETH, BTC, SOL), add a direct DEX / Cüzdan option at the top
        exact_base_item = next((item for item in matches if item["base"] == q or item["symbol"] == f"{q}USDT" or item["symbol"] == q), None)
        if exact_base_item:
            dex_option = {
                "symbol": q,
                "base": q,
                "display": f"{q} (DEX / Cüzdan - On-Chain)",
                "exchange": "DEX",
                "price": exact_base_item["price"]
            }
            matches.insert(0, dex_option)

        # Also search DEX on-the-fly if query is not a common major CEX symbol or matches are low
        if len(matches) < limit:
            dex_info = self.fetch_dex_screener(query)
            if dex_info and dex_info.get("price", 0) > 0:
                b_sym = dex_info.get("base_symbol", q)
                b_name = dex_info.get("base_name", b_sym)
                matches.append({
                    "symbol": b_sym,
                    "base": b_sym,
                    "display": f"{b_sym} ({b_name}) / {dex_info.get('quote_symbol', 'USD')}",
                    "exchange": dex_info.get("source", "DEX"),
                    "price": dex_info.get("price", 0.0)
                })

        seen = set()
        deduped = []
        for m in matches:
            key = f"{m['symbol']}@{m['exchange']}"
            if key not in seen:
                seen.add(key)
                deduped.append(m)
            if len(deduped) >= limit:
                break
        return deduped

# Singleton instance
price_service = SmartPriceDiscoveryEngine()
