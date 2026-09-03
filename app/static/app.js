/* =============================================================================
 * CoinTakip — Alpine.js Uygulama Durumu ve İş Mantığı
 * =============================================================================
 *
 * Tek dosyada tutulan Alpine.js bileşeni. Build aracı yoktur; index.html bu
 * dosyayı düz <script> olarak yükler ve x-data="portfolioApp()" ile bağlar.
 *
 * İÇİNDEKİLER (FAZ C3 — bölüm haritası)
 * -----------------------------------------------------------------------------
 *   BÖLÜM  0  Durum (state) tanımları
 *   BÖLÜM  1  Başlatma & ana veri akışı
 *   BÖLÜM  2  Borsa filtreleri & türetilmiş görünümler
 *   FAZ    1  Hedef fiyat & kâr alma (take-profit)
 *   BÖLÜM  3  Gerçek satış kaydı (realize & kasaya ekleme)
 *   FAZ    2  Akıllı DCA maliyet düşürme (what-if)
 *   BÖLÜM  4  Simülasyon ekranı filtreleri
 *   BÖLÜM  5  Sıralama
 *   BÖLÜM  6  Coin arama & öneriler
 *   BÖLÜM  7  İşlem ekle / düzenle / sil (DCA defteri CRUD)
 *   BÖLÜM  8  Yedekleme & geri yükleme
 *   BÖLÜM  9  Notlar
 *   BÖLÜM 10  Cüzdan & kasa yönetimi
 *   FAZ    3  TradingView, ısı haritası & sağlık analizi
 *   FAZ    4  7 günlük sparkline vektörel motoru
 *   BÖLÜM 11  Kategori dağılımı & portföy sağlık skoru
 *   BÖLÜM 12  Kazanan/kaybeden listeleri & ısı haritası verisi
 *   BÖLÜM 13  Chart.js grafik yönetimi
 *   FAZ    5  Ayarlar & bağlantı sağlık kontrolü
 *   FAZ    6  Yapay zeka danışmanı
 *   BÖLÜM 14  Biçimlendiriciler & yardımcılar
 *   FAZ    7  Gerçekleşmiş kâr/zarar & dışa aktarma
 *   FAZ    8  Güvenlik & kilit (PIN, recovery, gizlilik modu)
 *   BÖLÜM 15  Toast bildirim sistemi
 *
 * NOT: Tam ES-module bölünmesi bilinçli olarak ertelenmiştir (FAZ C3 kararı).
 * Bu haritalama, ileride güvenli bölme yapılabilmesi için ön hazırlıktır.
 * ============================================================================= */

function portfolioApp() {
  return {
    // -------------------------------------------------------------
    // BÖLÜM 0: DURUM (STATE) TANIMLARI
    // -------------------------------------------------------------
    activeTab: 'dashboard',
    isRefreshing: false,
    lastUpdateTs: 0,
    searchQuery: '',
    ledgerFilter: 'all',
    simCategoryFilter: 'all',
    dashboardExchangeFilter: 'all',
    selectedKasaExchange: 'ALL',
    
    // Sort Keys (Default: En Kârlıdan En Az Kârlıya / Zarara Doğru)
    sortKey: 'pnl_usd',
    sortAsc: false,
    ledgerSortKey: 'pnl_usd',
    ledgerSortAsc: false,
    simSortKey: 'sim_pnl_usd',
    simSortAsc: false,
    
    // Core Data
    kpis: {
      total_kasa: 0,
      spot_invested: 0,
      spot_current_value: 0,
      net_pnl_usd: 0,
      net_pnl_pct: 0,
      daily_diff_24h_usd: 0,
      usdt_cash: 500,
      active_coins_count: 0,
      active_tx_count: 0,
      kasa_share_pct: 100
    },
    exchangeKpis: {},
    consolidatedCoins: [],
    transactions: [],
    simulations: [],
    simCategories: [],
    simSummary: {
      total_old_invested: 0,
      total_sim_value: 0,
      total_sim_pnl_usd: 0,
      total_sim_pnl_pct: 0
    },

    // FAZ 8: Kilit & Şifreli Giriş (PIN & Security) State
    isLocked: false,
    pinEnabled: false,
    autoLockMinutes: 15,
    privacyMode: false,
    pinInput: '',
    pinError: '',
    isVerifyingPin: false,
    lastActivityTime: Date.now(),
    showPinSetupModal: false,
    pinSetupMode: 'enable', // 'enable' | 'change' | 'disable'
    pinSetupForm: {
      current_pin: '',
      new_pin: '',
      confirm_pin: '',
      auto_lock_minutes: 15
    },
    pinSetupError: '',
    // Recovery Key System
    showRecoveryMode: false,
    recoveryForm: { key: '', new_pin: '' },
    recoveryError: '',
    newRecoveryKey: '',
    showNewRecoveryKey: false,
    // Modern Toast Notification System
    toasts: [],

    // Modals
    showTxModal: false,
    isEditMode: false,
    searchSuggestions: [],
    txForm: {
      id: null,
      coin: '',
      date: '',
      qty: '',
      cost: '',
      status: 'Aktif',
      exchange: 'BINANCE',
      notes: '',
      category: '',
      fee_amount: '',
      fee_asset: 'USDT',
      fee_usd: 0
    },

    // Realize / Sell Modal (Borsadaki Gerçek Satış Kaydı)
    showSellModal: false,
    sellingTx: null,
    sellingCoin: null,
    sellForm: {
      title: '',
      coin_name: '',
      exchange: 'BINANCE',
      available_qty: 0,
      cost: 0,
      qty: '',
      price: '',
      fee_amount: '',
      fee_asset: 'BNB',
      fee_usd: 0
    },

    // Faz 1: Hedef Fiyat & Kâr Alma (Take-Profit) Simülasyon Modalı
    showTargetModal: false,
    targetCoin: null,
    targetForm: {
      pos_key: '',
      target_price: '',
      target_sell_pct: 100,
      notes: ''
    },

    // Faz 2: Akıllı DCA Maliyet Düşürme (What-If) Modalı
    showDcaModal: false,
    dcaCoin: null,
    dcaForm: {
      pos_key: '',
      coin_name: '',
      exchange: 'BINANCE',
      current_qty: 0,
      current_avg_cost: 0,
      live_price: 0,
      buy_price: 0,
      invest_amount: 100,
      deduct_cash: true,
      notes: ''
    },

    // Multi-Exchange Cash Management Modal
    showWalletModal: false,
    walletForm: {
      usdt_cash: 500,
      exchange_cash: {
        'BINANCE': 400,
        'MEXC': 100,
        'GATE.IO': 0,
        'DEX': 0
      },
      futures_balance: 0,
      margin_balance: 0
    },

    // Interactive Note Modal / Popover
    showNoteModal: false,
    selectedNoteTx: null,
    editingNoteText: '',

    // Faz 3: Kurumsal Görsel Analiz, Isı Haritası & TradingView Terminali
    tvSubTab: 'tv', // 'tv' | 'heatmap' | 'health' | 'pnl'
    selectedTvCoin: null,
    selectedTvPosKey: '',
    tvInterval: '60',
    heatmapMode: 'change_24h', // 'change_24h' | 'pnl'

    // Uygulama içi onay penceresi — tarayıcının confirm()/prompt() kutuları
    // arayüzün geri kalanıyla uyumsuz görünüyor ve stil verilemiyor.
    confirmDialog: {
      open: false, title: '', message: '', detail: '',
      confirmText: 'Onayla', tone: 'danger',
      withInput: false, inputLabel: '', inputValue: '', inputSuffix: ''
    },
    _confirmResolve: null,

    // Faz E: Hedge / Kaldıraçlı Pozisyon
    hedges: [],
    hedgeKpis: {},
    exposures: [],
    scenario: null,
    showHedgeForm: false,
    hedgeBusy: false,
    hedgeForm: {
      coin: '', direction: 'SHORT', exchange: 'BINANCE',
      // Kullanıcı pozisyonu genelde "100$ teminatla 2X" diye düşünür,
      // coin miktarı diye değil. İki giriş biçimi de destekleniyor.
      sizeMode: 'margin',   // 'margin' | 'qty'
      margin_usd: '', qty: '', entry_price: '', leverage: 2
    },

    // Faz F3: Borsa mutabakatı (salt okunur)
    reconcileReport: null,
    reconcileBusy: false,
    reconcileFilter: 'all',

    // Faz F5: Mutabakat düzeltmesi (öneri salt okunur, uygulama onaylı)
    rebuildPlan: null,
    rebuildBusy: false,
    rebuildApplying: null,     // uygulanmakta olan pos_key
    rebuildFilter: 'actionable',
    rebuildExpanded: null,     // lot dökümü açık olan satırın pos_key'i
    rebuilds: [],
    // Uygulama onayı kendi modalını kullanır: karşılaştırma tablosu, etki/uyarı
    // ayrımı ve alım dökümü düz metne sığmıyor.
    // FAZ F5b: `verifyQty` kullanıcının borsa ekranından okuyup girdiği güncel
    // bakiyedir. Kararı sunucu verir; buradaki değerlendirme sadece kullanıcı
    // yazarken ne olacağını göstermek içindir.
    rebuildConfirm: { open: false, row: null, verifyQty: '' },
    showReconcileHelp: false,

    // Faz F6: Anahtar kasası ve cüzdan bağlantıları
    vaultStatus: { unlocked: false, pin_enabled: false, sealed: false, entry_count: 0 },
    vaultPin: '',
    vaultBusy: false,
    providerKeyInput: '',
    providerKeySet: false,
    connections: {},
    connChains: [],
    connLocations: [],
    // `id` boşsa yeni kayıt, doluysa güncelleme. `label` kullanıcının hesabı
    // ayırt etmesi için: bir cüzdanda aynı zincirde birden çok hesap olabilir
    // (Phantom Hesap 2 / Hesap 3) ve ikisi de ayrı bağlantıdır.
    // `tokens`: elle tanımlanmış token kontratları. Otomatik keşif her zincirde
    // ücretsiz olmadığı için (BNB Chain, Base, Optimism, Avalanche ücretli
    // plana bağlı) bu liste bazı zincirlerde tokenı görmenin TEK yolu.
    connForm: { id: '', location: '', chain: 'ethereum', address: '', label: '',
                tokens: [] },
    connTokenInput: '',       // eklenecek kontrat adresi
    connTokenBusy: false,

    // ---- Faz F6b: borsa API bağlantıları ----
    // Cüzdan adresi herkese açıktır; borsa API anahtarı DEĞİLDİR. Bu yüzden
    // anahtarlar burada tutulmaz, girildikleri anda sunucuya gönderilip
    // şifreli kasaya yazılır ve form temizlenir.
    exProfiles: {},
    exFamilies: [],
    exBuiltin: [],
    exCredentials: {},
    exKeyExpiry: {},
    exEditing: null,          // duzenlenen profilin konumu (yeni kayitta null)
    exExpiryWarnDays: 14,
    exForm: { location: '', name: '', family: 'binance', base_url: '',
              account_path: '', time_path: '', restrictions_path: '',
              key_header: '', key_expires_at: '', balances_field: 'balances', asset_field: 'asset',
              free_field: 'free', locked_field: 'locked', label: '' },
    exKeyInput: '',
    exSecretInput: '',
    exBusy: false,
    exTestResult: null,
    exShowAdvanced: false,
    // İzinleri doğrulanamayan borsa için kullanıcının açık onayı. Veremeyeceğimiz
    // bir güvenceyi vermemek için var: onay kutusu işaretlenmeden kaydedilmez.
    exAcknowledge: false,
    // İşlem formu zincir tablosundan mı açıldı? Kayıttan sonra karşılaştırmayı
    // tazelemek için: satır "Zincirde var"dan "Eşleşiyor"a dönmeli, kullanıcı
    // işin bittiğini görmeli.
    chainAddPending: false,
    connNewLocation: false,   // konum kutusu serbest metne geçti mi
    connWarnings: [],         // aynı adres birden çok konumda gibi bütünlük uyarıları
    connBusy: false,
    connTestResult: null,
    connReport: null,
    // Bu tutarın altındaki farklar katlanır. Miktar tek başına "buna bakmalı
    // mıyım?" sorusunu cevaplamıyordu; borsa bağlantısı geldikten sonra tablo
    // ücret kırıntılarıyla dolduğu için bu bir konfor değil kullanılabilirlik
    // şartı. Değeri `settings.preferences.reconcile_dust_usd` içinde kalıcı.
    connDustUsd: 1.0,
    connShowDust: false,
    // Karşılaştırma tablosunun görünüm durumu. Bilerek KALICI DEĞİL: eşik
    // ($1) bir tercihtir, ama "şu an neye bakıyorum" oturumluk bir durumdur.
    // Kaydedilseydi kullanıcı yarın tabloyu eksik görüp sebebini arardı.
    connLocation: '',        // boş = tüm konumlar
    connOnlyDiff: true,      // eşleşen satırlar tanımı gereği sorun değildir
    // Solana'da istenmeden gönderilen spam token yaygın; gerçek bir cüzdanda
    // yüzlerce satır üretir. Gizlenmiyor, katlanıyor — kullanıcı açabilir.
    connShowSpam: false,

    // Faz F2: Arşiv (net varlık geçmişi)
    archiveStatus: {},
    archiveSeries: [],
    archiveRange: 90,          // gün; 0 = tümü
    archiveBusy: false,
    netWorthChart: null,

    // Faz F1c: Bilinen konumlar (borsa + kendi cüzdanların). Sunucudan gelir.
    locations: [],
    newLocationName: '',      // cüzdan modalındaki "konum ekle" alanı

    // Faz F1: Değer kaybı yazımı (mezarlık) ve transfer
    transfers: [],
    writeOffs: [],
    writeOffReasons: [],
    showTransferForm: false,
    transferBusy: false,
    transferForm: {
      pos_key: '', coin: '', from_exchange: '', available: 0,
      to_exchange: '', qty: '', fee_qty: '', date: '', note: ''
    },
    showWriteOffForm: false,
    writeOffBusy: false,
    writeOffForm: {
      pos_key: '', coin: '', exchange: '', qty: 0, invested: 0,
      reason: 'delist', note: ''
    },
    showLedgerHistory: false,   // transfer + yazım geçmişi paneli

    // Faz B++: Fiyat Kaynağı Kayıt Defteri
    sourceRegistry: [],        // [{id, label, enabled, order, kind}]
    symbolSources: {},         // { "SCM": {type, source, market} }
    sourceForm: {
      symbol: '',
      type: 'cex',             // 'cex' | 'dex' | 'manual'
      source: 'whitebit',
      market: '',
      query: '',
      price: ''
    },
    sourcePreview: null,       // {success, price, source, message}
    sourceBusy: false,
    sourceFormOpenedFromCoin: false,   // pozisyon rozetinden mi gelindi?

    // Faz 5: Settings & Health Check Hub
    showSettingsModal: false,
    settingsTab: 'health', // 'health' | 'sources' | 'urls' | 'keys' | 'prefs'
    settings: {
      api_urls: {
        binance_ticker: 'https://api.binance.com/api/v3/ticker/24hr',
        binance_ping: 'https://api.binance.com/api/v3/ping',
        mexc_ticker: 'https://api.mexc.com/api/v3/ticker/24hr',
        mexc_ping: 'https://api.mexc.com/api/v3/ping',
        whitebit_ticker: 'https://whitebit.com/api/v4/public/ticker',
        gateio_ticker: 'https://api.gateio.ws/api/v4/spot/tickers',
        dex_screener: 'https://api.dexscreener.com/latest/dex/search'
      },
      api_keys: {
        gemini_api_key: '',
        telegram_bot_token: '',
        telegram_chat_id: ''
      },
      preferences: {
        refresh_interval_sec: 3.5,
        default_tab: 'dashboard',
        sound_alerts: true,
        theme: 'dark'
      }
    },
    pingResults: {},
    pingLoading: false,
    showGeminiKey: false,
    showTelegramToken: false,
    telegramTestLoading: false,
    telegramTestResult: null,
    settingsSaveSuccess: false,
    bgIntervalTimer: null,

    // Faz 6: Yapay Zeka Danışmanı (AI Advisor Hub with Session Cache)
    aiMode: 'full_audit', // 'full_audit' | 'recovery' | 'brutal' | 'take_profit'
    aiReports: {
      full_audit: null,
      recovery: null,
      brutal: null,
      take_profit: null
    },
    aiReportSources: {
      full_audit: null,
      recovery: null,
      brutal: null,
      take_profit: null
    },
    aiReportTimes: {
      full_audit: null,
      recovery: null,
      brutal: null,
      take_profit: null
    },
    aiLoading: false,
    aiCustomQuestion: '',
    copiedReportSuccess: false,

    // Faz 7: Gerçekleşmiş Kâr/Zarar (Realized PnL) & Dışa Aktarma
    realizedMetrics: null,
    exportLoading: false,

    // Vergi-hazır dışa aktarım. `taxYear` boş = tüm yıllar.
    taxSummary: null,
    taxYear: '',
    taxLoading: false,
    copiedRichSuccess: false,

    // Chart instances
    allocationChart: null,
    pnlChart: null,
    categoryChart: null,

    // -------------------------------------------------------------
    // BÖLÜM 1: BAŞLATMA & ANA VERİ AKIŞI
    // -------------------------------------------------------------
    initApp() {
      this.fetchPortfolio();
      this.fetchSettings();
      this.fetchPriceSources();
      this.fetchRealizedMetrics();
      // Transfer/yazım sayıları açılışta bilinmeli — "Defter Geçmişi" girişi
      // buna göre görünür oluyor, yoksa geri alma yolu keşfedilemez.
      this.fetchLedgerHistory();
      // Arşiv durumu (kaç kayıt, boşluk var mı) açılışta bilinsin.
      this.fetchArchive();
      this.checkAuthStatus();
      this.initInactivityListener();
      this.startBackgroundLoop();

      // Re-init icons when tab changes
      this.$watch('activeTab', (val) => {
        this.$nextTick(() => {
          if (window.lucide) lucide.createIcons();
          if (val === 'charts') {
            this.renderCharts();
          }
          if (val === 'ledger') {
            this.fetchRealizedMetrics();
          }
        });
      });

      // Synchronize Kasa tab with table filter
      this.$watch('selectedKasaExchange', (val) => {
        this.dashboardExchangeFilter = val === 'ALL' ? 'all' : val;
      });
    },

    get lastUpdateFormatted() {
      if (!this.lastUpdateTs) return 'Canlı';
      const d = new Date(this.lastUpdateTs * 1000);
      return d.toLocaleTimeString();
    },

    get currentKpis() {
      if (this.exchangeKpis && this.exchangeKpis[this.selectedKasaExchange]) {
        return this.exchangeKpis[this.selectedKasaExchange];
      }
      return this.kpis;
    },

    get totalWalletCashPreview() {
      let sum = 0;
      if (this.walletForm && this.walletForm.exchange_cash) {
        for (const v of Object.values(this.walletForm.exchange_cash)) {
          sum += (parseFloat(v) || 0);
        }
      }
      return sum;
    },

    async fetchPortfolio(manual = false) {
      if (manual) this.isRefreshing = true;
      try {
        const resp = await fetch('/api/portfolio');
        if (!resp.ok) throw new Error('API Error');
        const data = await resp.json();
        
        this.kpis = data.kpis || this.kpis;
        this.exchangeKpis = data.exchange_kpis || {};
        this.locations = data.locations || this.locations;
        this.consolidatedCoins = data.consolidated_coins || [];
        this.transactions = data.transactions || [];
        this.simulations = data.simulations || [];
        this.simCategories = data.sim_categories || [];
        this.simSummary = data.sim_summary || this.simSummary;
        this.lastUpdateTs = data.last_update_ts || Date.now() / 1000;

        // Hedge durumu da her turda tazelenir. Eskiden yalnızca sekmeye
        // tıklandığında yükleniyordu; sunucu yeniden başlatıldığında veya
        // kayıt başka bir yerden değiştiğinde liste bayatlıyor ve silinmiş
        // bir kaydın "Sil" düğmesi 404 döndürüyordu.
        this.hedges = data.hedges || [];
        this.hedgeKpis = data.hedge_kpis || {};
        this.exposures = data.exposures || [];
        
        if (!this.showWalletModal && data.wallets) {
          const w = data.wallets;
          this.walletForm.usdt_cash = w.usdt_cash || 500;
          this.walletForm.exchange_cash = w.exchange_cash || {
            'BINANCE': (w.usdt_cash || 500) * 0.8,
            'MEXC': (w.usdt_cash || 500) * 0.2,
            'GATE.IO': 0,
            'DEX': 0
          };
          this.walletForm.futures_balance = w.futures_balance || 0;
          this.walletForm.margin_balance = w.margin_balance || 0;
        }

        if (this.activeTab === 'charts') {
          this.updateChartsData();
        }

        this.$nextTick(() => {
          if (window.lucide) lucide.createIcons();
        });
      } catch (err) {
        console.error('Error fetching portfolio:', err);
      } finally {
        if (manual) {
          setTimeout(() => { this.isRefreshing = false; }, 350);
        }
      }
    },

    // Dynamic Exchanges present in active coins
    // -------------------------------------------------------------
    // BÖLÜM 2: BORSA FİLTRELERİ & TÜRETİLMİŞ GÖRÜNÜMLER
    // -------------------------------------------------------------
    get availableExchanges() {
      const set = new Set();
      for (const c of this.consolidatedCoins) {
        let src = c.exchange || c.source || 'BINANCE';
        if (src.includes('DEX')) src = 'DEX (On-Chain)';
        set.add(src);
      }
      return Array.from(set);
    },

    countCoinsByExchange(exch) {
      return this.consolidatedCoins.filter(c => {
        let src = c.exchange || c.source || 'BINANCE';
        if (exch === 'DEX (On-Chain)') return src.includes('DEX');
        return src.toUpperCase() === exch.toUpperCase();
      }).length;
    },

    // Filtered & Sorted Consolidated Coins
    get filteredConsolidatedCoins() {
      let list = [...this.consolidatedCoins];

      // Exchange filter
      if (this.dashboardExchangeFilter !== 'all') {
        const target = this.dashboardExchangeFilter;
        list = list.filter(c => {
          let src = c.exchange || c.source || 'BINANCE';
          if (target === 'DEX (On-Chain)') return src.includes('DEX');
          return src.toUpperCase() === target.toUpperCase();
        });
      }

      // Search query
      if (this.searchQuery) {
        const q = this.searchQuery.toUpperCase().trim();
        list = list.filter(c => c.display_name.toUpperCase().includes(q) || (c.category && c.category.toUpperCase().includes(q)));
      }

      list.sort((a, b) => {
        let valA = a[this.sortKey];
        let valB = b[this.sortKey];
        if (valA === undefined || valA === null) valA = 0;
        if (valB === undefined || valB === null) valB = 0;
        if (typeof valA === 'string') {
          return this.sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        return this.sortAsc ? (valA - valB) : (valB - valA);
      });
      return list;
    },

    // Dynamic Totals for Consolidated Table Footer
    get filteredDashboardTotals() {
      const list = this.filteredConsolidatedCoins;
      let invested = 0;
      let currentValue = 0;
      let dailyDiff = 0;
      let txCount = 0;
      let shareTotal = 0;

      for (const c of list) {
        invested += (c.total_invested || 0);
        currentValue += (c.current_value || 0);
        txCount += (c.dca_count || 0);
        shareTotal += (c.portfolio_share_pct || 0);
        dailyDiff += (c.daily_diff_usd || 0);
      }

      const pnl_usd = currentValue - invested;
      const pnl_pct = invested > 0 ? (pnl_usd / invested * 100) : 0;
      const prevDayVal = currentValue - dailyDiff;
      const dailyDiffPct = prevDayVal > 0 ? (dailyDiff / prevDayVal * 100) : 0;

      return { invested, currentValue, pnl_usd, pnl_pct, dailyDiff, dailyDiffPct, txCount, shareTotal };
    },

    // -------------------------------------------------------------
    // FAZ F3: BORSA MUTABAKATI (SALT OKUNUR)
    // -------------------------------------------------------------
    // Bu ekran deftere HİÇBİR ŞEY YAZMAZ. Amaç içe aktarmak değil, farkı
    // görmek. Maliyet tabanı kullanıcının girdiği hâliyle kalır.

    // Durum etiketleri tek yerde: hem filtre düğmeleri hem tablo rozetleri
    // aynı sözlükten besleniyor, böylece ikisi ayrışamaz.
    reconcileStatusMeta: {
      mismatch:           { label: 'Fark var',          badge: 'bg-rose-500/15 text-rose-300 border border-rose-700/50',       active: 'bg-rose-600 text-white border-transparent' },
      only_exchange:      { label: 'Sadece borsada',    badge: 'bg-amber-500/15 text-amber-300 border border-amber-700/50',    active: 'bg-amber-600 text-white border-transparent' },
      coverage_gap:       { label: 'Kapsam dışı',       badge: 'bg-slate-500/15 text-slate-300 border border-slate-600',       active: 'bg-slate-500 text-white border-transparent' },
      off_exchange:       { label: 'Borsadan çekilmiş', badge: 'bg-sky-500/15 text-sky-300 border border-sky-700/50',          active: 'bg-sky-600 text-white border-transparent' },
      only_ledger:        { label: 'Sadece defterde',   badge: 'bg-orange-500/15 text-orange-300 border border-orange-700/50', active: 'bg-orange-600 text-white border-transparent' },
      uncovered_location: { label: 'Konum kapsanmıyor', badge: 'bg-indigo-500/15 text-indigo-300 border border-indigo-700/50', active: 'bg-indigo-600 text-white border-transparent' },
      match:              { label: 'Eşleşiyor',         badge: 'bg-emerald-500/15 text-emerald-300 border border-emerald-700/50', active: 'bg-emerald-600 text-white border-transparent' },
      closed:             { label: 'Kapanmış',          badge: 'bg-slate-700/40 text-slate-400 border border-slate-700',       active: 'bg-slate-600 text-white border-transparent' },
      stablecoin:         { label: 'Nakit birimi',      badge: 'bg-slate-700/40 text-slate-400 border border-slate-700',       active: 'bg-slate-600 text-white border-transparent' },
    },

    // Filtre düğmelerinin sırası — en çok ilgi isteyen durum önde.
    reconcileStatusOrder: ['mismatch', 'only_exchange', 'coverage_gap', 'off_exchange',
                           'only_ledger', 'uncovered_location', 'match', 'closed', 'stablecoin'],

    get filteredReconcileRows() {
      if (!this.reconcileReport) return [];
      const rows = this.reconcileReport.rows || [];
      if (this.reconcileFilter === 'all') return rows;
      return rows.filter(r => r.status === this.reconcileFilter);
    },

    async runReconcile() {
      if (this.reconcileBusy) return;
      this.reconcileBusy = true;
      try {
        const resp = await fetch('/api/reconcile');
        if (!resp.ok) throw new Error('Mutabakat çalıştırılamadı.');
        this.reconcileReport = await resp.json();
        this.$nextTick(() => { if (window.lucide) lucide.createIcons(); });
      } catch (e) {
        this.notify(e.message || 'Mutabakat çalıştırılamadı.', 'error', 5000);
      } finally {
        this.reconcileBusy = false;
      }
    },

    // -------------------------------------------------------------
    // FAZ F5: MUTABAKAT DÜZELTMESİ
    // -------------------------------------------------------------
    // Öneriyi görmek deftere hiçbir şey yazmaz. Uygulama pozisyon başınadır:
    // toplu bir "hepsini uygula" düğmesi BİLEREK yok — her düzeltme maliyet
    // tabanını değiştirir ve kullanıcının onu tek tek görmesi gerekir.
    // Etiketler kullanıcının sorduğu soruyu cevaplamalı: "ne yapmalıyım?"
    // Önceki "Dikkatli bak" etiketi neyin dikkat gerektirdiğini söylemiyordu.
    // FAZ F5b — 'Uygulanabilir' (yeşil) rozeti KALDIRILDI. Dosyalar hangi
    // tarafın haklı olduğunu tek başına söyleyemez; söyleyen tek şey borsadaki
    // gerçek bakiyedir. Yeşil rozet hak edilmemiş bir güven veriyordu.
    rebuildStatusMeta: {
      needs_check: {
        label: 'Bakiye sorulacak', badge: 'bg-sky-500/15 text-sky-300 border border-sky-700/50',
        help: 'Öneri hesaplandı ama tek başına yeterli değil. Borsa ekranınızdaki ' +
              'güncel bakiyeyi soracak; öneriyle uyuşursa uygulanır, defterinizle ' +
              'uyuşursa eksik olan dosyadır ve defterinize DOKUNULMAZ.'
      },
      caution: {
        label: 'Önce uyarıyı oku', badge: 'bg-amber-500/15 text-amber-300 border border-amber-700/50',
        help: 'Öneri hesaplanabildi ama bilmeniz gereken bir şey var — genelde ' +
              'o borsadan coin çekmiş olmanız ya da önerinin pozisyonu küçültmesi. ' +
              'Satırdaki ⚠ ile başlayan cümleyi okuyun. Burada da bakiye sorulur.'
      },
      blocked: {
        label: 'Kapsam yetersiz', badge: 'bg-slate-500/15 text-slate-400 border border-slate-600',
        help: 'Öneri VERİLMİYOR: dosya o kadar geriye gitmiyor ya da dışarıdan gelmiş, ' +
              'maliyeti bilinmeyen coin var. Uydurmaktansa susmayı tercih ediyor.'
      },
      identical: {
        label: 'Zaten uyumlu', badge: 'bg-slate-700/40 text-slate-500 border border-slate-700',
        help: 'Defteriniz borsa kayıtlarıyla tutuyor. Yapılacak bir şey yok.'
      },
    },

    get rebuildRows() {
      if (!this.rebuildPlan) return [];
      const rows = this.rebuildPlan.rows || [];
      if (this.rebuildFilter === 'all') return rows;
      if (this.rebuildFilter === 'actionable') {
        return rows.filter(r => r.status === 'needs_check' || r.status === 'caution');
      }
      return rows.filter(r => r.status === this.rebuildFilter);
    },

    async fetchRebuildPlan() {
      if (this.rebuildBusy) return;
      this.rebuildBusy = true;
      try {
        const resp = await fetch('/api/reconcile/rebuild');
        if (!resp.ok) throw new Error('Düzeltme önerileri hesaplanamadı.');
        this.rebuildPlan = await resp.json();
      } catch (e) {
        this.notify(e.message || 'Düzeltme önerileri hesaplanamadı.', 'error', 5000);
      } finally {
        this.rebuildBusy = false;
      }
    },

    openRebuildConfirm(r) {
      // Kutu bilerek BOŞ açılır. Öneriyle doldurulsaydı kullanıcı borsaya
      // bakmadan onaylardı ve doğrulama bir tiyatroya dönerdi.
      this.rebuildConfirm = { open: true, row: r, verifyQty: '' };
    },

    // Girilen bakiye hangi tarafı destekliyor? Sunucudaki `evaluate_verified_qty`
    // ile aynı ölçüt: "hangi adaya daha yakın". Buradaki yalnızca önizlemedir;
    // uygulamayı reddetme yetkisi sunucudadır.
    get rebuildVerifyVerdict() {
      const r = this.rebuildConfirm.row;
      const ham = String(this.rebuildConfirm.verifyQty || '').trim().replace(',', '.');
      if (!r || ham === '') return null;
      const v = Number(ham);
      if (!isFinite(v) || v < 0) {
        return { ok: false, tone: 'error', text: 'Geçerli bir bakiye yazın.' };
      }
      const yakin = (a, b) => {
        const fark = Math.abs(a - b);
        if (fark <= 1e-8) return true;
        const olcek = Math.max(Math.abs(a), Math.abs(b));
        return olcek > 0 && (fark / olcek * 100) <= 0.5;
      };
      const oneri = Number(r.proposed_qty || 0);
      const defter = Number(r.ledger_qty || 0);
      if (yakin(oneri, defter)) {
        return yakin(v, oneri)
          ? { ok: true, tone: 'ok', text: 'Miktar teyit edildi. Düzeltme maliyet tabanını güncelleyecek.' }
          : { ok: false, tone: 'error', text: 'Girilen bakiye bu pozisyonun miktarıyla uyuşmuyor.' };
      }
      const dOneri = Math.abs(v - oneri), dDefter = Math.abs(v - defter);
      if (dOneri < dDefter && yakin(v, oneri)) {
        return { ok: true, tone: 'ok',
                 text: 'Borsa kayıtlarıyla uyuşuyor — fark defterden kaynaklanıyor. Düzeltme uygulanabilir.' };
      }
      if (dDefter < dOneri) {
        return { ok: false, tone: 'warn',
                 text: 'Bu rakam DEFTERİNİZLE uyuşuyor: defteriniz doğru, eksik olan dosya. ' +
                       'Bu coin muhtemelen dosya penceresinden önce alınmış ve hiç satılmamış. ' +
                       'Düzeltme uygulanmayacak — defteriniz olduğu gibi kalacak.' };
      }
      return { ok: false, tone: 'error',
               text: 'Bu rakam ne defterdeki ne de hesaplanan miktarla uyuşuyor. ' +
                     'Üçüncü bir kaynak eksik olabilir (başka cüzdan, kilitli bakiye, kapsam dışı borsa).' };
    },

    async applyRebuild(r) {
      if (this.rebuildApplying) return;
      const bakiye = String(this.rebuildConfirm.verifyQty || '').trim().replace(',', '.');
      this.rebuildConfirm.open = false;
      this.rebuildApplying = r.pos_key;
      try {
        const resp = await fetch('/api/reconcile/rebuild/' + encodeURI(r.pos_key), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            signature: r.signature,
            verified_qty: bakiye === '' ? null : Number(bakiye)
          })
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Düzeltme uygulanamadı.');
        this._applyLedgerSnapshot(body);
        const k = body.rebuild;
        let mesaj = `${k.asset} düzeltildi: ${this.formatNum(k.before.qty, 6)} → ` +
                    `${this.formatNum(k.after.qty, 6)} adet, maliyet ` +
                    `$${this.formatNum(k.before.invested, 2)} → $${this.formatNum(k.after.invested, 2)}.`;
        if (k.realized && k.realized.booked) {
          mesaj += ` Geçmiş satışların $${this.formatNum(Math.abs(k.realized.pnl_usd), 2)} ` +
                   `gerçekleşmiş ${k.realized.pnl_usd < 0 ? 'zararı' : 'kârı'} da deftere geçti.`;
        }
        this.notify(mesaj, 'success', 7000);
        await this.fetchRebuildPlan();
        await this.fetchPortfolio();
      } catch (e) {
        this.notify(e.message || 'Düzeltme uygulanamadı.', 'error', 8000);
      } finally {
        this.rebuildApplying = null;
      }
    },

    async undoRebuildRecord(k) {
      const id = (k && k.id != null) ? k.id : k;
      const kayit = (k && k.id != null) ? k : null;
      const onay = await this.askConfirm({
        title: 'Düzeltmeyi geri al',
        message: kayit ? `${kayit.asset} — ${kayit.exchange} pozisyonu elle girdiğiniz hâline dönecek.`
                       : 'Pozisyon elle girdiğiniz eski hâline dönecek.',
        detail: (kayit
          ? `Borsa kayıtlarından kurulmuş ${kayit.after.lot_count} alım silinecek, ` +
            `eski ${kayit.before.lot_count} kayıt geri açılacak ` +
            `(${this.formatNum(kayit.after.qty, 6)} → ${this.formatNum(kayit.before.qty, 6)} adet). `
          : '') +
          ((kayit && kayit.realized && kayit.realized.booked)
            ? `Düzeltmeyle deftere geçen $${this.formatNum(kayit.realized.pnl_usd, 2)} ` +
              'gerçekleşmiş K/Z kaydı da silinecek. '
            : '') +
          'Düzeltmeden sonra bu varlığı sattıysanız işlem reddedilir.',
        confirmText: 'Geri Al',
        tone: 'danger'
      });
      if (!onay) return;
      try {
        const resp = await fetch('/api/rebuilds/' + id + '/undo', { method: 'POST' });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Düzeltme geri alınamadı.');
        this._applyLedgerSnapshot(body);
        this.notify(`Düzeltme geri alındı: ${body.result.restored_lots} lot eski hâline döndü.`,
                    'success', 5000);
        await this.fetchRebuildPlan();
        await this.fetchPortfolio();
      } catch (e) {
        this.notify(e.message || 'Düzeltme geri alınamadı.', 'error', 6000);
      }
    },

    // -------------------------------------------------------------
    // FAZ F6: ANAHTAR KASASI VE CÜZDAN BAĞLANTILARI
    // -------------------------------------------------------------
    // Bu ekran ADRES ister, sır istemez. Adres herkese açık bir bilgidir ve
    // okuma yapı gereği salt okunurdur. Kullanıcıya kurtarma ifadesi veya
    // özel anahtar sorulmaz; sunucu tarafı da böyle bir girdiyi reddeder.

    connStatusMeta: {
      mismatch: { label: 'Fark var', badge: 'bg-rose-500/15 text-rose-300 border border-rose-700/50' },
      only_chain: { label: 'Zincirde var', badge: 'bg-amber-500/15 text-amber-300 border border-amber-700/50' },
      only_ledger: { label: 'Zincirde yok', badge: 'bg-orange-500/15 text-orange-300 border border-orange-700/50' },
      unreadable: { label: 'Okunamadı', badge: 'bg-slate-500/15 text-slate-400 border border-slate-600' },
      match: { label: 'Eşleşiyor', badge: 'bg-emerald-500/15 text-emerald-300 border border-emerald-700/50' },
    },

    // Bağlantılar `KONUM@zincir` ile anahtarlanır; ekranda konuma göre
    // gruplanır. Aynı cüzdan birden çok zincirde olabilir ve biri diğerini
    // ezmemelidir — ilk sürümde tam olarak bu oldu.
    get connByLocation() {
      const grup = {};
      for (const [id, spec] of Object.entries(this.connections || {})) {
        const konum = spec.location || '?';
        (grup[konum] = grup[konum] || []).push({ id, spec });
      }
      for (const k of Object.keys(grup)) {
        grup[k].sort((a, b) => (a.spec.chain || '').localeCompare(b.spec.chain || '') ||
                               (a.spec.label || '').localeCompare(b.spec.label || ''));
      }
      return grup;
    },

    get connLocationsWithConn() {
      return Object.keys(this.connByLocation).sort();
    },

    // Okuma raporu: hangi bağlantı okundu, ne oldu, ne eksik kaldı.
    // Bunu göstermek ŞART: başarıyla okunan bir bağlantının uyarısı (örneğin
    // "Etherscan anahtarı yok, tokenlar bulunamadı") daha önce sessizce
    // düşüyordu ve kullanıcı tokenının neden gelmediğini göremiyordu.
    get connReadings() {
      if (!this.connReport) return [];
      return Object.entries(this.connReport.connections || {})
        .map(([id, v]) => ({ id, ...v }))
        .sort((a, b) => (a.location || '').localeCompare(b.location || '') ||
                        (a.chain || '').localeCompare(b.chain || ''));
    },

    // EVM bağlantısı var mı? Etherscan anahtarı yalnızca EVM için gerekli;
    // sadece Solana kullanan birine anahtar uyarısı göstermek gürültü olurdu.
    get connHasEvm() {
      return Object.values(this.connections || {})
        .some(c => c.chain && c.chain !== 'solana');
    },

    get connHasWarnings() {
      return this.connReadings.some(r => !r.ok || r.incomplete);
    },

    // Not seviyeleri: ⛔ okunamadı, ⚠ eksik okundu, ℹ bilgi. Üçünü aynı
    // kırmızıyla göstermek gerçek sorunu gürültüde kaybettiriyordu.
    noteMeta: {
      error: { icon: '⛔', cls: 'text-rose-300' },
      warn:  { icon: '⚠',  cls: 'text-amber-300/90' },
      info:  { icon: 'ℹ',  cls: 'text-slate-400' },
    },

    // Seçili zincirde otomatik token keşfi çalışıyor mu? Kullanıcı bunu zinciri
    // SEÇERKEN görmeli; tokenı gelmedikten sonra öğrenmesi geç oluyor.
    get connChainDiscovery() {
      const c = (this.connChains || []).find(x => x.id === this.connForm.chain);
      return c ? (c.discovery || 'free') : 'free';
    },

    get connPaidChains() {
      return (this.connChains || []).filter(c => c.discovery === 'paid')
        .map(c => c.name).join(', ');
    },

    get connFreeChains() {
      return (this.connChains || []).filter(c => c.discovery === 'free')
        .map(c => c.name).join(', ');
    },

    // Eşiğin altındaki fark "önemsiz"dir — ama yalnızca DEĞERİ BİLİNİYORSA.
    // Fiyatı bulunamayan satır asla önemsiz sayılmaz: bilinmeyen değer sıfır
    // değer değildir ve gerçekten değerli bir mikro-cap'i gürültü sanıp
    // gizlemek, projede birkaç kez düzelttiğimiz hatanın aynısı olurdu.
    connRowIsDust(r) {
      if (!r || r.diff_value === null || r.diff_value === undefined) return false;
      if (r.status === 'match') return false;      // zaten sorun değil
      const esik = parseFloat(this.connDustUsd);
      if (!(esik > 0)) return false;
      return Math.abs(r.diff_value) < esik;
    },

    // -------------------------------------------------------------
    // KONUM SÜZGECİ
    //
    // Tablo artık üç kaynaktan besleniyor (zincir cüzdanları + Binance +
    // MEXC) ve konum ayrımı olmadan tek uzun listeye dönüşüyor.
    //
    // Konumlar VERİDEN türetilir, koda gömülmez: kullanıcı Gate.io eklediği
    // gün düğmesi kendiliğinden çıkar. Sabit bir liste, projenin her
    // katmanında bilinçle kaçınılan şeydir.
    // -------------------------------------------------------------
    // Konum süzgecinden GEÇEN ama diğer süzgeçlere girmemiş satırlar.
    // Sayımların dayanağı budur; böylece rozetler kırıntı katlandığında
    // değişmez — değişseydi "3 fark var" yazarken tabloda 1 satır görünürdü.
    get connScopedRows() {
      if (!this.connReport) return [];
      const rows = this.connReport.rows || [];
      if (!this.connLocation) return rows;
      return rows.filter(r => r.location === this.connLocation);
    },

    // [{ location, count }] — sayı, o konuma tıklayınca GÖRECEĞİN satır sayısı.
    get connLocationList() {
      if (!this.connReport) return [];
      const sayac = {};
      for (const r of (this.connReport.rows || [])) {
        if (!this.connRowPassesFilters(r)) continue;
        sayac[r.location] = (sayac[r.location] || 0) + 1;
      }
      return Object.keys(sayac).sort()
        .map(location => ({ location, count: sayac[location] }));
    },

    get connVisibleTotal() {
      return this.connLocationList.reduce((t, l) => t + l.count, 0);
    },

    // Konum DIŞINDAKİ tüm süzgeçler tek yerde; hem satır listesi hem konum
    // sayaçları bunu kullanır, yoksa ikisi ayrışır.
    connRowPassesFilters(r) {
      if (!this.connShowSpam && r.likely_spam) return false;
      if (!this.connShowDust && this.connRowIsDust(r)) return false;
      if (this.connOnlyDiff && r.status === 'match') return false;
      return true;
    },

    get connDustRows() {
      return this.connScopedRows.filter(r => !r.likely_spam && this.connRowIsDust(r));
    },

    get connDustTotal() {
      return this.connDustRows.reduce((t, r) => t + Math.abs(r.diff_value || 0), 0);
    },

    // Rozetler ve bantlar seçili konumu anlatmalı; global sayı gösterirsek
    // başlık listeyle çelişir ve kullanıcı hangisine inanacağını bilemez.
    get connStatusCounts() {
      const sayac = {};
      for (const r of this.connScopedRows) {
        if (r.likely_spam) continue;      // sunucudaki kuralla aynı
        sayac[r.status] = (sayac[r.status] || 0) + 1;
      }
      return sayac;
    },

    get connSpamCount() {
      return this.connScopedRows.filter(r => r.likely_spam).length;
    },

    get connReviewCount() {
      return this.connScopedRows.filter(r => r.needs_review).length;
    },

    // Bir yanlış konum tabloda İKİ satır üretir (biri defterin yazdığı
    // konumda, biri varlığın gerçekten durduğu konumda) ama TEK sorundur.
    //
    // Sunucu bunu "role == chain" satırlarını sayarak yapıyor; burada
    // yapamayız, çünkü konum süzgeci çiftin yalnızca bir yarısını kapsama
    // alabilir. Defterin yanlış yazdığı konumu seçtiğinizde satır görünür
    // ama sayaç sıfır çıkardı ve satırı açıklayan bant kaybolurdu — yani
    // uyarı, tam olarak en çok gerektiği yerde yok olurdu.
    //
    // Bu yüzden çift, hangi yarısı görünürse görünsün kimliğinden sayılır.
    get connMisplacedCount() {
      const ciftler = new Set();
      for (const r of this.connScopedRows) {
        const m = r.misplaced;
        if (!m) continue;
        ciftler.add(`${m.asset}|${m.ledger_location}|${m.correct_location}`);
      }
      return ciftler.size;
    },

    // "Sadece farklar" ile gizlenen eşleşen satır sayısı. Sessizce gizlemek
    // yok: kaç satırın saklandığı anahtarın yanında yazar.
    get connMatchCount() {
      return this.connScopedRows.filter(r => {
        if (!this.connShowSpam && r.likely_spam) return false;
        return r.status === 'match';
      }).length;
    },

    get connRows() {
      return this.connScopedRows.filter(r => this.connRowPassesFilters(r));
    },

    // "$1,23" / çok küçükse "<$0,01" / fiyat yoksa "—".
    // Sıfır göstermek yanlış olurdu: 0,004 dolar sıfır değildir, sadece küçüktür.
    fmtUsd(v) {
      if (v === null || v === undefined) return '—';
      const m = Math.abs(v);
      if (m === 0) return '$0';
      if (m < 0.01) return (v < 0 ? '-' : '') + '<$0,01';
      return (v < 0 ? '-' : '') + '$' + this.formatNum(m, m < 1 ? 4 : 2);
    },

    async saveDustThreshold() {
      const esik = parseFloat(this.connDustUsd);
      if (!(esik >= 0)) return;
      try {
        this.settings.preferences = { ...this.settings.preferences,
                                      reconcile_dust_usd: esik };
        await fetch('/api/settings', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ preferences: this.settings.preferences })
        });
      } catch (e) {
        // Eşik kaydedilemezse tablo yine doğru çalışır; yalnızca kalıcı olmaz.
        console.warn('Eşik kaydedilemedi:', e);
      }
    },

    chainName(id) {
      const c = (this.connChains || []).find(x => x.id === id);
      return c ? c.name : (id || '—');
    },

    get connTestMessage() {
      const r = this.connTestResult;
      if (!r) return '';
      // Beklenmeyen bir cevap şekli sessizce "kurulamadı"ya düşmemeli; sebebi
      // olmayan bir hata mesajı kullanıcıyı yanlış yere bakmaya iter.
      if (r.ok === undefined) return 'Sunucudan beklenmeyen bir cevap geldi.';
      const notlar = r.notes || [];
      if (!r.ok) return (notlar[0] || {}).message || 'Bağlantı kurulamadı.';
      const n = r.asset_count != null ? r.asset_count : (r.balances || []).length;
      // Denemede de en ağır not gösterilir; bilgi notu bir hatanın önüne geçmemeli.
      const onemli = notlar.find(w => w.level === 'error') ||
                     notlar.find(w => w.level === 'warn') || notlar[0];
      return `Bağlantı çalışıyor — ${n} varlık okundu.` +
             (onemli ? ' ' + onemli.message : '');
    },

    async fetchConnections() {
      try {
        const resp = await fetch('/api/connections');
        if (!resp.ok) throw new Error('Bağlantılar okunamadı.');
        const body = await resp.json();
        this.connections = body.connections || {};
        this.connChains = body.chains || [];
        this.connLocations = body.locations || [];
        this.connWarnings = body.warnings || [];
        this.vaultStatus = body.vault || this.vaultStatus;
        this.providerKeySet = !!body.provider_key_set;
      } catch (e) {
        this.notify(e.message || 'Bağlantılar okunamadı.', 'error', 5000);
      }
    },

    // -------------------------------------------------------------
    // FAZ F6b: BORSA API BAĞLANTILARI
    // -------------------------------------------------------------
    async fetchExchanges() {
      try {
        const resp = await fetch('/api/exchanges');
        if (!resp.ok) throw new Error('Borsa profilleri okunamadı.');
        this.applyExchangeStatus(await resp.json());
      } catch (e) {
        this.notify(e.message || 'Borsa profilleri okunamadı.', 'error', 5000);
      }
    },

    applyExchangeStatus(body) {
      this.exProfiles = body.profiles || {};
      this.exFamilies = body.families || [];
      this.exBuiltin = body.builtin || [];
      this.exCredentials = body.credentials || {};
      this.exKeyExpiry = body.key_expiry || {};
      this.exExpiryWarnDays = body.expiry_warn_days || 14;
    },

    // Süresi dolmuş veya dolmak üzere olan anahtarlar. Bağlantı paneli
    // açılmasa bile görülebilsin diye ayrı bir liste.
    get exExpiringKeys() {
      return Object.entries(this.exKeyExpiry)
        .filter(([, d]) => d && (d.state === 'expired' || d.state === 'expiring'))
        .map(([konum, d]) => ({ konum, ...d }))
        .sort((a, b) => (a.days_left ?? 0) - (b.days_left ?? 0));
    },

    // "+90 gün" düğmesi. Borsanın verdiği süreyi elle hesaplatmak, kullanıcıyı
    // takvim açmaya zorlamak demekti.
    setKeyExpiryInDays(gun) {
      const d = new Date();
      d.setDate(d.getDate() + gun);
      // YYYY-AA-GG, yerel saate göre — toISOString() UTC'ye kaydırıp
      // tarihi bir gün geriye alabiliyor.
      const ay = String(d.getMonth() + 1).padStart(2, '0');
      const gunAd = String(d.getDate()).padStart(2, '0');
      this.exForm.key_expires_at = `${d.getFullYear()}-${ay}-${gunAd}`;
    },

    get exProfileList() {
      return Object.entries(this.exProfiles)
                   .map(([konum, spec]) => ({ konum, spec }))
                   .sort((a, b) => a.konum.localeCompare(b.konum));
    },

    // Hazır profil seçilince form doldurulur. Kullanıcı yine de her alanı
    // değiştirebilir: profil koda gömülü değil veridir.
    pickBuiltinExchange(konum) {
      const hazir = (this.exBuiltin || []).find(p => p.location === konum);
      if (!hazir) return;
      this.exForm = { ...this.exForm, ...hazir, label: this.exForm.label || '' };
      this.exTestResult = null;
      this.exAcknowledge = false;
    },

    resetExchangeForm() {
      this.exForm = { location: '', name: '', family: 'binance', base_url: '',
                      account_path: '', time_path: '', restrictions_path: '',
                      key_header: '', key_expires_at: '', balances_field: 'balances', asset_field: 'asset',
                      free_field: 'free', locked_field: 'locked', label: '' };
      this.exKeyInput = '';
      this.exSecretInput = '';
      this.exTestResult = null;
      this.exAcknowledge = false;
      this.exEditing = null;
    },

    editExchange(konum) {
      const spec = this.exProfiles[konum];
      if (!spec) return;
      this.exForm = { ...this.exForm, ...spec };
      // Anahtar kasada; buraya geri getirilmez. Değiştirmek isterse yeniden
      // girer — sırrı ekrana basmak için hiçbir sebep yok.
      this.exKeyInput = '';
      this.exSecretInput = '';
      this.exTestResult = null;
      this.exAcknowledge = false;
      this.exEditing = konum;
    },

    // Var olan bir profili düzenliyoruz ve anahtarı zaten kasada mı?
    // Öyleyse ad/etiket/bitiş tarihi için anahtarı yeniden istemeye gerek yok.
    get exCanSaveSettingsOnly() {
      return !!this.exEditing && !!this.exCredentials[this.exEditing];
    },

    // Anahtara DOKUNMADAN profili günceller.
    //
    // Buna neden ayrı bir yol gerekiyor: gizli anahtar (secret) borsada
    // yalnızca oluşturulurken bir kez gösterilir. Sadece bitiş tarihi girmek
    // için anahtarın tamamını yeniden istemek, elinde secret olmayan
    // kullanıcıyı yepyeni bir API anahtarı almaya zorlardı.
    async saveExchangeSettings() {
      if (this.exBusy || !this.exEditing) return;
      this.exBusy = true;
      try {
        const resp = await fetch(`/api/exchanges/${encodeURIComponent(this.exEditing)}`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.exForm)
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Ayarlar kaydedilemedi.');
        this.applyExchangeStatus(body);
        const konum = this.exEditing;
        this.resetExchangeForm();
        this.notify(`${konum} ayarları güncellendi. Anahtarınıza dokunulmadı.`,
                    'success', 5000);
      } catch (e) {
        this.notify(e.message || 'Ayarlar kaydedilemedi.', 'error', 12000);
      } finally {
        this.exBusy = false;
      }
    },

    get exPermissionUnverifiable() {
      const r = this.exTestResult;
      return !!(r && r.permission && r.permission.status === 'unverifiable');
    },

    async testExchange() {
      if (this.exBusy) return;
      if (!this.exKeyInput || !this.exSecretInput) {
        this.notify('API anahtarı ve gizli anahtar gerekli.', 'error', 4000);
        return;
      }
      this.exBusy = true;
      this.exTestResult = null;
      try {
        const resp = await fetch('/api/exchanges/test', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ profile: this.exForm,
                                 api_key: this.exKeyInput,
                                 api_secret: this.exSecretInput })
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Bağlantı denenemedi.');
        this.exTestResult = body;
        this.notify(`${body.name}: ${body.asset_count} varlık okundu.`,
                    'success', 5000);
      } catch (e) {
        this.exTestResult = { ok: false, error: e.message };
        this.notify(e.message || 'Bağlantı denenemedi.', 'error', 9000);
      } finally {
        this.exBusy = false;
      }
    },

    async saveExchange() {
      if (this.exBusy) return;
      if (!this.vaultStatus.unlocked) {
        this.notify('Borsa anahtarı şifreli kasaya yazılır; önce kasayı açın ' +
                    '(Anahtar Kasası → PIN → Kasayı Aç).', 'error', 8000);
        return;
      }
      if (!this.exKeyInput || !this.exSecretInput) {
        this.notify('API anahtarı ve gizli anahtar gerekli.', 'error', 4000);
        return;
      }
      this.exBusy = true;
      try {
        const resp = await fetch('/api/exchanges', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ profile: this.exForm,
                                 api_key: this.exKeyInput,
                                 api_secret: this.exSecretInput,
                                 acknowledge_unverified: this.exAcknowledge })
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Borsa kaydedilemedi.');
        this.applyExchangeStatus(body);
        const konum = (body.profile || {}).location || this.exForm.location;
        this.resetExchangeForm();
        this.notify(`${konum} bağlantısı kaydedildi. Anahtar şifreli kasada ` +
                    'duruyor.', 'success', 6000);
      } catch (e) {
        this.notify(e.message || 'Borsa kaydedilemedi.', 'error', 12000);
      } finally {
        this.exBusy = false;
      }
    },

    async removeExchange(konum) {
      const onay = await this.askConfirm({
        title: 'Borsa bağlantısını sil',
        message: `${konum} bağlantısı silinecek.`,
        detail: 'Profil ve kasadaki API anahtarınız birlikte silinir — ' +
                '"sildim" dediğiniz bir sırrın diskte durmaya devam etmesi ' +
                'doğru olmazdı. Defterinizdeki kayıtlara DOKUNULMAZ.',
        confirmText: 'Sil', tone: 'danger'
      });
      if (!onay) return;
      try {
        const resp = await fetch('/api/exchanges/' + encodeURIComponent(konum),
                                 { method: 'DELETE' });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Silinemedi.');
        this.applyExchangeStatus(body);
        this.notify(`${konum} bağlantısı silindi.`, 'success', 3000);
      } catch (e) {
        this.notify(e.message || 'Silinemedi.', 'error', 5000);
      }
    },

    async unlockVault() {
      if (this.vaultBusy) return;
      this.vaultBusy = true;
      try {
        const resp = await fetch('/api/vault/unlock', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin: this.vaultPin })
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Kasa açılamadı.');
        this.vaultStatus = body;
        this.notify(body.created ? 'Anahtar kasası oluşturuldu ve açıldı.'
                                 : 'Anahtar kasası açıldı.', 'success', 4000);
      } catch (e) {
        this.notify(e.message || 'Kasa açılamadı.', 'error', 6000);
      } finally {
        // PIN bellekte tutulmaz; kutu her denemeden sonra temizlenir.
        this.vaultPin = '';
        this.vaultBusy = false;
      }
    },

    async lockVault() {
      try {
        const resp = await fetch('/api/vault/lock', { method: 'POST' });
        this.vaultStatus = await resp.json();
        this.notify('Anahtar kasası kilitlendi.', 'success', 3000);
      } catch (e) {
        this.notify('Kasa kilitlenemedi.', 'error', 4000);
      }
    },

    async saveProviderKey() {
      if (!this.providerKeyInput.trim()) {
        this.notify('Önce anahtarı yazın.', 'error', 4000);
        return;
      }
      this.vaultBusy = true;
      try {
        const resp = await fetch('/api/vault/secret/etherscan_api_key', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ value: this.providerKeyInput.trim() })
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Anahtar kaydedilemedi.');
        this.providerKeySet = !!body.stored;
        this.notify('Anahtar kasaya şifrelenerek kaydedildi.', 'success', 4000);
      } catch (e) {
        this.notify(e.message || 'Anahtar kaydedilemedi.', 'error', 6000);
      } finally {
        // Kutu temizlenir: kaydedilen sır ekranda asılı kalmaz ve geri okunmaz.
        this.providerKeyInput = '';
        this.vaultBusy = false;
      }
    },

    async forgetProviderKey() {
      const onay = await this.askConfirm({
        title: 'Sağlayıcı anahtarını sil',
        message: 'Etherscan API anahtarı kasadan silinecek.',
        detail: 'Anahtar olmadan yalnızca yerel coin bakiyeleri okunabilir; ' +
                'token listesi otomatik bulunamaz. İstediğiniz zaman yeniden girebilirsiniz.',
        confirmText: 'Sil', tone: 'danger'
      });
      if (!onay) return;
      try {
        await fetch('/api/vault/secret/etherscan_api_key', { method: 'DELETE' });
        this.providerKeySet = false;
        this.notify('Anahtar silindi.', 'success', 3000);
      } catch (e) {
        this.notify('Anahtar silinemedi.', 'error', 4000);
      }
    },

    _connPayload() {
      return {
        id: this.connForm.id || null,
        type: 'onchain',
        location: (this.connForm.location || '').trim(),
        chain: this.connForm.chain,
        address: (this.connForm.address || '').trim(),
        label: (this.connForm.label || '').trim(),
        tokens: this.connForm.tokens || [],
        enabled: true,
      };
    },

    // Kontrat adresinden sembol ve ondalık haneyi zincire sorar. Kullanıcıdan
    // ondalık hane istemek anlamsız olurdu — zincir zaten biliyor ve yanlış
    // girilen bir ondalık bakiyeyi sessizce 10^n kat yanlış gösterirdi.
    async addFormToken() {
      const kontrat = (this.connTokenInput || '').trim();
      if (!kontrat) return;
      if ((this.connForm.tokens || []).some(t => t.contract.toLowerCase() === kontrat.toLowerCase())) {
        this.notify('Bu token zaten listede.', 'error', 3000);
        return;
      }
      this.connTokenBusy = true;
      try {
        const resp = await fetch('/api/connections/token-info', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chain: this.connForm.chain, contract: kontrat })
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Kontrat okunamadı.');
        this.connForm.tokens = [...(this.connForm.tokens || []), body.token];
        this.connTokenInput = '';
        this.notify(`${body.token.symbol} eklendi. Kaydet'e basmayı unutmayın.`,
                    'success', 4000);
      } catch (e) {
        this.notify(e.message || 'Kontrat okunamadı.', 'error', 8000);
      } finally {
        this.connTokenBusy = false;
      }
    },

    removeFormToken(kontrat) {
      this.connForm.tokens = (this.connForm.tokens || [])
        .filter(t => t.contract !== kontrat);
    },

    async testConnection() {
      const konum = (this.connForm.location || '').trim();
      if (!konum || !this.connForm.address.trim()) {
        this.notify('Konum ve adres gerekli.', 'error', 4000);
        return;
      }
      this.connBusy = true;
      this.connTestResult = null;
      try {
        const resp = await fetch('/api/connections/test', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this._connPayload())
        });
        const body = await resp.json();
        if (!resp.ok) {
          // Doğrulama hatası (sır yapıştırma dâhil) burada yakalanır ve
          // kullanıcıya olduğu gibi gösterilir — sessizce yutulmaz.
          this.connTestResult = { ok: false, notes: [
            { level: 'error', message: body.detail || 'Geçersiz tanım.' }] };
          return;
        }
        this.connTestResult = body;
      } catch (e) {
        this.connTestResult = { ok: false, notes: [
          { level: 'error', message: e.message || 'Bağlantı denenemedi.' }] };
      } finally {
        this.connBusy = false;
      }
    },

    async saveConnection() {
      const konum = (this.connForm.location || '').trim();
      if (!konum || !this.connForm.address.trim()) {
        this.notify('Konum ve adres gerekli.', 'error', 4000);
        return;
      }
      // GERÇEK HATA: kullanıcı kontrat adresini kutuya yazıp doğrudan Kaydet'e
      // bastı. Adres listeye girmemişti, kayıt boş token listesiyle yapıldı ve
      // sistem bunu SÖYLEMEDİ. Kullanıcı tokenını eklediğini sanıyordu.
      // Artık bekleyen adres önce çözülür; çözülemezse kayıt yapılmaz.
      if ((this.connTokenInput || '').trim()) {
        await this.addFormToken();
        if ((this.connTokenInput || '').trim()) {
          this.notify('Kutudaki kontrat adresi çözülemediği için kayıt ' +
                      'yapılmadı. Adresi düzeltin veya kutuyu boşaltın — ' +
                      'aksi hâlde o token sessizce kaybolurdu.', 'error', 9000);
          return;
        }
      }
      this.connBusy = true;
      try {
        const resp = await fetch('/api/connections', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this._connPayload())
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Bağlantı kaydedilemedi.');
        this.connections = body.connections || {};
        this.connWarnings = body.warnings || [];
        const zincir = this.chainName(this.connForm.chain);
        // Konum ve zincir BİLEREK korunuyor: aynı cüzdana başka bir hesap veya
        // başka bir zincir eklemek yaygın durum; kullanıcı baştan yazmamalı.
        this.connForm = { id: '', location: konum, chain: this.connForm.chain,
                          address: '', label: '', tokens: [] };
        this.connTokenInput = '';
        this.connTestResult = null;
        this.notify(`${konum} — ${zincir} bağlantısı kaydedildi. Aynı cüzdanda başka ` +
                    'bir hesabınız veya başka bir zinciriniz varsa adresi değiştirip ' +
                    'tekrar kaydedin; öncekiler silinmez.', 'success', 6000);
        // Çift sayma uyarısı varsa kaybolmasın — bu tabloyu bozan bir durumdur.
        if (this.connWarnings.length) {
          this.notify(this.connWarnings[0], 'error', 12000);
        }
      } catch (e) {
        this.notify(e.message || 'Bağlantı kaydedilemedi.', 'error', 7000);
      } finally {
        this.connBusy = false;
      }
    },

    editConnection(id, spec) {
      this.connForm = { id, location: spec.location, chain: spec.chain,
                        address: spec.address, label: spec.label || '',
                        tokens: (spec.tokens || []).map(t => ({ ...t })) };
      this.connTokenInput = '';
      this.connTestResult = null;
    },

    async removeConnection(id, konum, zincirAdi) {
      const onay = await this.askConfirm({
        title: 'Bağlantıyı sil',
        message: `${konum} — ${zincirAdi} bağlantısı silinecek.`,
        detail: 'Yalnızca bu adresin bağlantı tanımı silinir; aynı konumdaki ' +
                'diğer hesaplar, diğer zincirler ve defterinizdeki kayıtlar ' +
                'olduğu gibi kalır. İstediğiniz zaman yeniden ekleyebilirsiniz.',
        confirmText: 'Sil', tone: 'danger'
      });
      if (!onay) return;
      try {
        const resp = await fetch('/api/connections/' + encodeURIComponent(id),
                                 { method: 'DELETE' });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Bağlantı silinemedi.');
        this.connections = body.connections || {};
        this.connWarnings = body.warnings || [];
        this.notify(`${konum} — ${zincirAdi} bağlantısı silindi.`, 'success', 3000);
      } catch (e) {
        this.notify(e.message || 'Bağlantı silinemedi.', 'error', 5000);
      }
    },

    // -------------------------------------------------------------
    // FAZ F6a: ZİNCİRDEKİ VARLIĞI DEFTERE EKLEME
    // -------------------------------------------------------------
    // Zincir MİKTARI bilir, MALİYETİ bilmez. Bu yüzden otomatik yazma yok:
    // sıfır maliyetle yazmak %100 kâr uydurmak olurdu — F5b'de düzeltilen
    // sahte kâr hatasının aynısı. Form coin/miktar/konumla dolu açılır,
    // tarih ve maliyet kullanıcıya bırakılır. Varlık başına BİR kez.
    chainAddableQty(r) {
      if (!r || r.chain_qty === null || r.chain_qty === undefined) return 0;
      if (r.likely_spam) return 0;                 // spam token deftere girmez
      // Hakkında hüküm olmayan token da deftere girmez. Fark şu: spam
      // KATLANIR, bu satır GÖRÜNÜR kalır — yalnızca ekleme önerilmez.
      // Kullanıcı "Bu gerçek" derse düğme gelir.
      if (r.needs_review) return 0;
      // Yanlış konuma yazılmış varlık: aynı varlık defterde başka bir konumda
      // duruyor. Eklemek ÇİFT SAYAR. Burada yapılacak şey eklemek değil,
      // mevcut kaydın konumunu düzeltmektir.
      if (r.misplaced) return 0;
      if (r.status === 'only_chain') return r.chain_qty;
      // Kısmi eksik de aynı durumun küçük hâli: zincirde defterden FAZLA var.
      if (r.status === 'mismatch' && r.diff_qty > 0) return r.diff_qty;
      return 0;
    },

    addFromChain(r) {
      const miktar = this.chainAddableQty(r);
      if (!miktar) return;
      this.openAddModal('Aktif');
      this.txForm.coin = r.asset;
      this.txForm.exchange = r.location;
      // 8 hane: zincir bakiyeleri ondalıklı ve yuvarlamak miktarı bozar.
      this.txForm.qty = Number(miktar.toFixed(8));
      this.txForm.date = '';
      this.txForm.cost = '';
      this.txForm.notes = `Zincirden okundu (${(r.chains || []).join(', ')}). ` +
                          'Maliyeti zincir bilmiyor; kendiniz girdiniz.';
      this.chainAddPending = true;
      this.notify(
        `${r.asset} — ${r.location}: miktar zincirden dolduruldu. ` +
        'ALIM TARİHİ ve BİRİM ALIŞ FİYATI alanlarını siz doldurun — ' +
        'zincir maliyeti bilmez.', 'info', 9000);
    },

    // Doğrulanmamış bir tokenı kullanıcı kendisi işaretler. Sistemin tahmini
    // tahmindir: gerçek bir airdrop başlangıçta değersiz görünebilir. Son söz
    // kullanıcınındır ve bu işaret tüm otomatik sinyalleri ezer.
    async markToken(r, isaret) {
      const kontratlar = (r && r.contracts) || [];
      if (!kontratlar.length) {
        this.notify(`${r.asset} bir kontrat adresi taşımıyor; işaretlenemez.`,
                    'error', 4000);
        return;
      }
      if (isaret === 'spam') {
        const onay = await this.askConfirm({
          title: 'Spam olarak işaretle',
          message: `${r.asset} spam sayılacak.`,
          detail: 'Karşılaştırma tablosunda katlanır ve deftere ekleme düğmesi ' +
                  'gösterilmez. Defterinizdeki kayıtlara DOKUNULMAZ; istediğiniz ' +
                  'zaman "Bu gerçek" diyerek geri alabilirsiniz.',
          confirmText: 'Spam işaretle', tone: 'danger'
        });
        if (!onay) return;
      }
      try {
        for (const k of kontratlar) {
          const resp = await fetch('/api/connections/token-mark', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chain: k.chain, contract: k.contract,
                                   mark: isaret })
          });
          const body = await resp.json();
          if (!resp.ok) throw new Error(body.detail || 'İşaret kaydedilemedi.');
        }
        this.notify(
          isaret === 'real'
            ? `${r.asset} gerçek olarak işaretlendi; artık deftere ekleyebilirsiniz.`
            : `${r.asset} spam olarak işaretlendi.`, 'success', 4000);
        await this.runConnectionReconcile();
      } catch (e) {
        this.notify(e.message || 'İşaret kaydedilemedi.', 'error', 5000);
      }
    },

    // Yanlış konuma yazılmış varlığın kaydını doğru konuma taşır.
    // Ekleme DEĞİL düzeltme: varlık o konumda hiç bulunmadı, kayıt yanlış
    // yazıldı. Yeni kayıt açmak defterde aynı varlıktan iki tane yaratırdı.
    async fixLocation(r) {
      const m = r && r.misplaced;
      if (!m) return;
      const adet = (m.tx_ids || []).length;
      const onay = await this.askConfirm({
        title: 'Kaydın konumunu düzelt',
        message: `${m.asset}: defterde ${m.ledger_location} yazıyor, zincirde ` +
                 `${m.correct_location} adresinde duruyor.`,
        detail: `${adet || 'İlgili'} aktif kaydın konumu ${m.correct_location} ` +
                'olarak güncellenecek ve sembol o konuma göre yeniden ' +
                'yazılacak. Miktar, maliyet, tarih ve notlar değişmez; kapalı ' +
                'kayıtlara dokunulmaz. Bu bir transfer değildir — varlık ' +
                'gerçekte hiç taşınmadı, yalnızca yanlış yazılmıştı.',
        confirmText: 'Konumu düzelt'
      });
      if (!onay) return;
      try {
        const resp = await fetch('/api/connections/relocate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ asset: m.asset,
                                 from_location: m.ledger_location,
                                 to_location: m.correct_location })
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Konum düzeltilemedi.');
        this.notify(`${m.asset}: ${body.count} kayıt ${m.correct_location} ` +
                    'konumuna alındı.', 'success', 5000);
        await this.fetchPortfolio();
        await this.runConnectionReconcile();
      } catch (e) {
        this.notify(e.message || 'Konum düzeltilemedi.', 'error', 5000);
      }
    },

    async runConnectionReconcile() {
      if (this.connBusy) return;
      // Kasa kilitliyken okuma sessizce eksik kalıyordu. Anahtar kasada
      // duruyorsa bunu okumadan ÖNCE söylemek, sonra "eksik okundu" demekten
      // iyidir — kullanıcı zaten anahtarı girmiş, eksik olan tek şey kasayı
      // açmak.
      if (this.connHasEvm && this.providerKeySet && !this.vaultStatus.unlocked) {
        this.notify('Kasa kilitli — Etherscan anahtarınız kullanılamıyor ve EVM ' +
                    'tokenlarınız okunmayacak. Anahtar Kasası bölümünden PIN ile ' +
                    'açıp tekrar deneyin.', 'error', 10000);
      }
      this.connBusy = true;
      try {
        const resp = await fetch('/api/connections/reconcile');
        if (!resp.ok) throw new Error('Bakiyeler okunamadı.');
        this.connReport = await resp.json();
        this.connWarnings = this.connReport.warnings || [];
        // Seçili konum bu raporda hiç geçmiyorsa süzgeç tabloyu boşaltırdı
        // ve kullanıcı sebebini aramak zorunda kalırdı (bağlantı silinmiş
        // veya kapatılmış olabilir). Sessizce tüm konumlara dönülür.
        if (this.connLocation &&
            !(this.connReport.rows || []).some(r => r.location === this.connLocation)) {
          this.connLocation = '';
        }
        // Kasa durumu rapordan tazelenir: kullanıcı başka bir sekmede kasayı
        // açmış veya kilitlemiş olabilir ve ekrandaki rozet yanıltmamalı.
        if (this.connReport.vault) {
          this.vaultStatus = this.connReport.vault;
          this.providerKeySet = !!this.connReport.vault.provider_key_set;
        }
        // Okunamayan bağlantı gizlenmez: kullanıcı boş listeyi "varlığım yok"
        // sanmamalı, sebebini görmeli.
        const okumalar = this.connReadings;
        const sorunlu = okumalar.filter(r => !r.ok);
        if (sorunlu.length) {
          this.notify(`${sorunlu.length} bağlantı okunamadı: ` +
                      sorunlu.map(r => r.location + ' / ' + this.chainName(r.chain)).join(', '),
                      'error', 8000);
        }
        // Okunan ama EKSİK okunan bağlantılar da bildirilmeli. Daha önce bunlar
        // sessizce düşüyordu: kullanıcı BNB Chain'deki tokenının neden
        // gelmediğini göremedi, çünkü uyarı hiçbir yere çıkmıyordu.
        //
        // Ama "her not = eksiklik" saymak da yanlıştı ve tersine hata yaptı:
        // Solana'nın spam token BİLGİSİ de alarm üretince "3 bağlantı eksik
        // okundu" dendi, gerçekte eksik olan bir taneydi. Sunucu artık her
        // notu seviyelendiriyor; burada yalnızca gerçek eksikler sayılıyor.
        const eksik = okumalar.filter(r => r.ok && r.incomplete);
        if (eksik.length) {
          this.notify(`${eksik.length} bağlantı eksik okundu (` +
                      eksik.map(r => r.location + ' / ' + this.chainName(r.chain)).join(', ') +
                      ') — "Okunan bağlantılar" bölümüne bakın.', 'error', 9000);
        }
      } catch (e) {
        this.notify(e.message || 'Bakiyeler okunamadı.', 'error', 6000);
      } finally {
        this.connBusy = false;
      }
    },

    // -------------------------------------------------------------
    // FAZ F2: ARŞİV & NET VARLIK EĞRİSİ
    // -------------------------------------------------------------
    // Arşiv bir konfor katmanıdır, kritik yol değildir: burada bir şey
    // ters giderse sessizce boş görünür, uygulamanın geri kalanı çalışır.

    get archiveSizeLabel() {
      const b = this.archiveStatus.file_size_bytes || 0;
      if (b < 1024) return b + ' B';
      if (b < 1024 * 1024) return (b / 1024).toFixed(0) + ' KB';
      return (b / 1024 / 1024).toFixed(1) + ' MB';
    },

    async fetchArchive() {
      try {
        const resp = await fetch('/api/archive/networth?days=' + (this.archiveRange || 0));
        if (!resp.ok) return;
        const data = await resp.json();
        this.archiveSeries = data.series || [];
        this.archiveStatus = data.status || {};
        this.$nextTick(() => this.renderNetWorthChart());
      } catch (e) {
        console.error('Arşiv okunamadı:', e);
      }
    },

    async takeSnapshot() {
      if (this.archiveBusy) return;
      this.archiveBusy = true;
      try {
        const resp = await fetch('/api/archive/snapshot', { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Fotoğraf alınamadı.');
        this.notify('Arşiv fotoğrafı alındı.', 'success');
        await this.fetchArchive();
      } catch (e) {
        this.notify(e.message || 'Fotoğraf alınamadı.', 'error', 5000);
      } finally {
        this.archiveBusy = false;
      }
    },

    renderNetWorthChart() {
      const el = document.getElementById('netWorthChart');
      // Tek noktayla çizgi grafiği anlamsız; arayüz onun yerine
      // "arşiv bugün başladı" mesajını gösteriyor.
      if (!el || this.archiveSeries.length < 2 || !window.Chart) return;
      if (this.netWorthChart) this.netWorthChart.destroy();

      const seri = this.archiveSeries;
      this.netWorthChart = new Chart(el, {
        type: 'line',
        data: {
          labels: seri.map(r => r.taken_date),
          datasets: [
            {
              label: 'Net Varlık ($)',
              data: seri.map(r => r.total_equity_usd),
              borderColor: '#38bdf8',
              backgroundColor: 'rgba(56, 189, 248, 0.12)',
              borderWidth: 2, pointRadius: 2, tension: 0.25, fill: true,
            },
            {
              label: 'Spot Değer ($)',
              data: seri.map(r => r.spot_value_usd),
              borderColor: '#2dd4bf',
              borderWidth: 1.5, pointRadius: 0, tension: 0.25, fill: false,
              borderDash: [4, 3],
            },
            {
              label: 'Maliyet ($)',
              data: seri.map(r => r.spot_invested_usd),
              borderColor: '#f59e0b',
              borderWidth: 1.5, pointRadius: 0, tension: 0.25, fill: false,
              borderDash: [2, 3],
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: {
              labels: { color: '#94a3b8', font: { family: 'Inter', size: 10 },
                        boxWidth: 12, padding: 12 },
            },
            tooltip: {
              callbacks: {
                label: (c) => c.dataset.label + ': $' + this.formatNum(c.parsed.y, 2),
              },
            },
          },
          scales: {
            x: { ticks: { color: '#64748b', font: { family: 'Inter', size: 9 }, maxTicksLimit: 10 },
                 grid: { display: false } },
            y: { ticks: { color: '#64748b', font: { family: 'Inter', size: 9 },
                          callback: (v) => '$' + this.formatNum(v, 0) },
                 grid: { color: '#1e293b' } },
          },
        },
      });
    },

    // -------------------------------------------------------------
    // FAZ F1c: KONUM (BORSA / CÜZDAN) KAYNAĞI
    // -------------------------------------------------------------
    // Tek doğruluk kaynağı. Kasa sekmesi, cüzdan modalı, transfer hedefi ve
    // dashboard filtresi hep buradan beslenir. Sunucu `locations` gönderir;
    // gelmezse elimizdeki veriden türetiriz (eski sürümle uyum).
    get knownLocations() {
      const set = new Set(['BINANCE', 'MEXC', 'GATE.IO', 'DEX']);
      (this.locations || []).forEach(l => set.add(String(l).toUpperCase()));
      (this.consolidatedCoins || []).forEach(c =>
        set.add(this.normalizeLocation(c.exchange)));
      Object.keys((this.walletForm && this.walletForm.exchange_cash) || {})
        .forEach(k => set.add(String(k).toUpperCase()));
      (this.transfers || []).forEach(t => {
        set.add(this.normalizeLocation(t.from_exchange));
        set.add(this.normalizeLocation(t.to_exchange));
      });
      const varsayilan = ['BINANCE', 'MEXC', 'GATE.IO', 'DEX'];
      const ekstra = Array.from(set).filter(x => !varsayilan.includes(x)).sort();
      return varsayilan.concat(ekstra);
    },

    // İşlem formundaki "Borsa / Kaynak" kutusu. Sabit liste bir tuzaktı:
    // kullanıcı cüzdanındaki varlığı girerken seçecek konum bulamayınca
    // "DEX'teymiş gibi" girmek zorunda kaldı ve defteri gerçeği yansıtmaz
    // oldu. Kaynak üç yerden geliyor:
    //   1. `knownLocations` — verisinde fiilen geçen konumlar,
    //   2. bağlantı tanımlı cüzdanlar — henüz defterinde varlığı olmayabilir,
    //      ki "Deftere Ekle" tam da o durumu çözüyor,
    //   3. formda o an duran değer — düzenlenen eski bir kaydın konumu
    //      listede yoksa kutu boş görünür ve kaydetmek konumu değiştirirdi.
    get txExchangeOptions() {
      const set = new Set(this.knownLocations);
      Object.values(this.connections || {}).forEach(c => {
        if (c && c.location) set.add(String(c.location).toUpperCase());
      });
      ['COINGECKO', 'MANUEL'].forEach(x => set.add(x));
      const mevcut = (this.txForm && this.txForm.exchange || '').toUpperCase();
      if (mevcut) set.add(mevcut);
      const varsayilan = ['BINANCE', 'MEXC', 'GATE.IO', 'DEX'];
      return varsayilan.filter(v => set.has(v)).concat(
        Array.from(set).filter(x => !varsayilan.includes(x))
          .sort((a, b) => a.localeCompare(b, 'tr')));
    },

    // Kasa sekmesinde gösterilecek konumlar: içinde varlık VEYA nakit olanlar.
    // Boş konum sekmesi göstermek gürültü; ama varlığı olan hiçbir konum
    // gizlenmemeli — asıl düzeltilen hata buydu.
    get kasaLocationTabs() {
      return this.knownLocations.filter(loc => {
        const k = this.exchangeKpis[loc];
        if (!k) return false;
        return (k.active_coins_count || 0) > 0
            || (k.spot_invested || 0) > 0
            || (k.usdt_cash || 0) > 0;
      });
    },

    // data_manager.normalize_location ile aynı kural — zincir üstü adlar tek
    // "DEX" kovasında toplanır, diğer her ad olduğu gibi korunur.
    normalizeLocation(name) {
      const t = String(name || '').toUpperCase().trim();
      if (!t) return 'BINANCE';
      if (t.startsWith('DEX') || t.includes('PANCAKE') || t.includes('UNISWAP')) return 'DEX';
      return t;
    },

    // Kullanıcının kendi eklediği konumlar için renk: adın hash'inden sabit bir
    // palet rengi seçilir. Böylece METAMASK her ekranda aynı renkte görünür,
    // ama yeni konum eklemek kod değişikliği gerektirmez.
    _locationPaletteIndex(exch) {
      const s = String(exch || '');
      let h = 0;
      for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
      return h % 6;
    },

    getExchangeActiveStyle(exch) {
      if (exch === 'BINANCE') return 'bg-yellow-600 text-white shadow-sm';
      if (exch === 'MEXC') return 'bg-blue-600 text-white shadow-sm';
      if (exch === 'GATE.IO') return 'bg-emerald-600 text-white shadow-sm';
      if (String(exch).includes('DEX')) return 'bg-purple-600 text-white shadow-sm';
      return ['bg-teal-600', 'bg-orange-600', 'bg-pink-600',
              'bg-indigo-600', 'bg-lime-600', 'bg-rose-600'
             ][this._locationPaletteIndex(exch)] + ' text-white shadow-sm';
    },

    getExchangeDotColor(exch) {
      if (exch === 'BINANCE') return 'bg-yellow-400';
      if (exch === 'MEXC') return 'bg-blue-400';
      if (exch === 'GATE.IO') return 'bg-emerald-400';
      if (String(exch).includes('DEX')) return 'bg-purple-400';
      return ['bg-teal-400', 'bg-orange-400', 'bg-pink-400',
              'bg-indigo-400', 'bg-lime-400', 'bg-rose-400'
             ][this._locationPaletteIndex(exch)];
    },

    // Pozisyon satırı ve işlem defterindeki küçük konum rozeti.
    getExchangeBadgeStyle(exch) {
      if (exch === 'BINANCE') return 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20';
      if (exch === 'MEXC') return 'bg-blue-500/10 text-blue-400 border border-blue-500/20';
      if (exch === 'GATE.IO') return 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
      if (String(exch).includes('DEX')) return 'bg-purple-500/10 text-purple-400 border border-purple-500/20';
      return ['bg-teal-500/10 text-teal-400 border border-teal-500/20',
              'bg-orange-500/10 text-orange-400 border border-orange-500/20',
              'bg-pink-500/10 text-pink-400 border border-pink-500/20',
              'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20',
              'bg-lime-500/10 text-lime-400 border border-lime-500/20',
              'bg-rose-500/10 text-rose-400 border border-rose-500/20'
             ][this._locationPaletteIndex(exch)];
    },

    // Filtered & Sorted Transactions for Ledger
    get filteredTransactions() {
      let list = [...this.transactions];
      if (this.ledgerFilter === 'active') {
        list = list.filter(t => t.status === 'Aktif');
      } else if (this.ledgerFilter === 'closed') {
        list = list.filter(t => t.status !== 'Aktif');
      }

      if (this.searchQuery) {
        const q = this.searchQuery.toUpperCase().trim();
        list = list.filter(t => t.coin.toUpperCase().includes(q) || (t.notes && t.notes.toUpperCase().includes(q)));
      }

      list.sort((a, b) => {
        let valA = a[this.ledgerSortKey];
        let valB = b[this.ledgerSortKey];
        if (valA === undefined || valA === null) valA = 0;
        if (valB === undefined || valB === null) valB = 0;
        if (typeof valA === 'string') {
          return this.ledgerSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        return this.ledgerSortAsc ? (valA - valB) : (valB - valA);
      });

      return list;
    },

    // -------------------------------------------------------------
    // FAZ 1: HEDEF FİYAT & KÂR ALMA (TAKE-PROFIT) METHODS
    // -------------------------------------------------------------
    openTargetModal(coin) {
      this.targetCoin = coin;
      const existing = coin.target || {};
      
      let initialPrice = existing.target_price;
      if (!initialPrice || initialPrice <= 0) {
        initialPrice = (coin.live_price * 1.5).toFixed(8).replace(/\.?0+$/, "");
      }

      this.targetForm = {
        pos_key: coin.pos_key,
        target_price: initialPrice,
        target_sell_pct: existing.target_sell_pct || 100,
        notes: existing.notes || ''
      };
      this.showTargetModal = true;
      this.$nextTick(() => {
        if (window.lucide) lucide.createIcons();
      });
    },

    setTargetMultiplier(mult) {
      if (!this.targetCoin) return;
      const base = this.targetCoin.live_price || this.targetCoin.avg_cost;
      this.targetForm.target_price = (base * mult).toFixed(8).replace(/\.?0+$/, "");
    },

    setTargetPercent(pct) {
      if (!this.targetCoin) return;
      const base = this.targetCoin.live_price || this.targetCoin.avg_cost;
      this.targetForm.target_price = (base * (1 + pct)).toFixed(8).replace(/\.?0+$/, "");
    },

    setTargetSellPercent(pct) {
      this.targetForm.target_sell_pct = pct;
    },

    get calculatedTargetSellQty() {
      if (!this.targetCoin) return 0;
      return (this.targetCoin.total_qty || 0) * ((this.targetForm.target_sell_pct || 100) / 100.0);
    },

    get calculatedTargetCashReturn() {
      const tp = parseFloat(this.targetForm.target_price) || 0;
      return this.calculatedTargetSellQty * tp;
    },

    get calculatedTargetPnl() {
      if (!this.targetCoin) return 0;
      const tp = parseFloat(this.targetForm.target_price) || 0;
      const avg = this.targetCoin.avg_cost || 0;
      return (tp - avg) * this.calculatedTargetSellQty;
    },

    get calculatedTargetPnlPct() {
      if (!this.targetCoin || !this.targetCoin.avg_cost) return 0;
      const tp = parseFloat(this.targetForm.target_price) || 0;
      return ((tp - this.targetCoin.avg_cost) / this.targetCoin.avg_cost) * 100;
    },

    get calculatedTargetRisePct() {
      if (!this.targetCoin || !this.targetCoin.live_price) return 0;
      const tp = parseFloat(this.targetForm.target_price) || 0;
      return ((tp - this.targetCoin.live_price) / this.targetCoin.live_price) * 100;
    },

    get calculatedTargetProgress() {
      if (!this.targetCoin || !parseFloat(this.targetForm.target_price)) return 0;
      const tp = parseFloat(this.targetForm.target_price);
      return Math.min(100, Math.max(0, (this.targetCoin.live_price / tp) * 100));
    },

    async saveTarget() {
      if (!this.targetForm.pos_key || !this.targetForm.target_price || parseFloat(this.targetForm.target_price) <= 0) {
        this.notify('Lütfen geçerli bir hedef fiyat girin.', 'warning');
        return;
      }
      try {
        const res = await fetch('/api/targets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            pos_key: this.targetForm.pos_key,
            target_price: parseFloat(this.targetForm.target_price),
            target_sell_pct: parseFloat(this.targetForm.target_sell_pct || 100),
            notes: this.targetForm.notes || ''
          })
        });
        if (res.ok) {
          this.showTargetModal = false;
          this.notify('Kâr alma hedefi başarıyla kaydedildi!', 'success');
          this.fetchPortfolio(true);
        } else {
          this.notify('Hedef kaydedilirken hata oluştu.', 'error');
        }
      } catch (e) {
        console.error(e);
        this.notify('Bağlantı hatası.', 'error');
      }
    },

    async removeTarget() {
      if (!this.targetForm.pos_key) return;
      if (!await this.askConfirm({
        title: 'Kâr alma hedefi kaldırılsın mı?',
        message: 'Bu pozisyona tanımlı hedef fiyat silinecek.',
        detail: 'Pozisyonun kendisi ve işlem kayıtları etkilenmez.',
        confirmText: 'Hedefi Kaldır'
      })) return;
      try {
        const res = await fetch(`/api/targets/${encodeURIComponent(this.targetForm.pos_key)}`, {
          method: 'DELETE'
        });
        if (res.ok) {
          this.showTargetModal = false;
          this.fetchPortfolio(true);
        }
      } catch (e) {
        console.error(e);
      }
    },

    // -------------------------------------------------------------
    // BÖLÜM 3: GERÇEK SATIŞ KAYDI (Realize & Kasaya Ekleme)
    // -------------------------------------------------------------
    calculateFeeInUsd(amount, asset, totalVal) {
      const amt = parseFloat(amount) || 0;
      if (amt <= 0) return 0;
      const ast = (asset || 'USDT').toUpperCase().trim();
      if (ast === 'USDT' || ast === 'USD') return amt;
      if (ast === '%') return (parseFloat(totalVal) || 0) * (amt / 100);
      if (ast === 'BNB') {
        const bnbObj = this.consolidatedCoins.find(c => c.symbol === 'BNBUSDT' || c.display_name === 'BNB') || (this.livePrices && this.livePrices['BNBUSDT']);
        const bnbPrice = bnbObj ? (bnbObj.live_price || bnbObj.price || 600) : 600;
        return amt * bnbPrice;
      }
      const cObj = this.consolidatedCoins.find(c => c.symbol === `${ast}USDT` || c.display_name === ast);
      const price = cObj ? (cObj.live_price || 1) : 1;
      return amt * price;
    },

    openSellModal(tx) {
      this.sellingTx = tx;
      this.sellingCoin = null;
      const coinObj = this.consolidatedCoins.find(c => {
        const sym = (tx.coin || '').toUpperCase();
        const ex = (tx.exchange || 'BINANCE').toUpperCase();
        return (c.symbol === sym || c.display_name === sym) && (c.exchange === ex);
      });
      const avgCost = coinObj ? (coinObj.avg_cost || tx.cost) : tx.cost;

      this.sellForm = {
        title: `${tx.coin} [${tx.exchange || 'BINANCE'}] Satışını Deftere İşle`,
        coin_name: tx.coin,
        exchange: tx.exchange || 'BINANCE',
        available_qty: tx.qty,
        avg_cost: avgCost,
        cost: tx.cost,
        qty: tx.qty,
        price: tx.live_price || tx.cost,
        fee_amount: '',
        fee_asset: 'BNB',
        fee_usd: 0,
        cost_method: 'Konsolide Ortalama'
      };
      this.showSellModal = true;
      this.$nextTick(() => {
        if (window.lucide) lucide.createIcons();
      });
    },

    openRecordSaleFromTarget(coin) {
      this.sellingTx = null;
      this.sellingCoin = coin;
      const tgt = coin.target || {};
      const pct = tgt.target_sell_pct || 100;
      const suggestedQty = (coin.total_qty || 0) * (pct / 100.0);
      const suggestedPrice = tgt.target_price || coin.live_price;

      this.sellForm = {
        title: `${coin.display_name} [${coin.exchange || 'BINANCE'}] Borsadaki Satışı Deftere İşle`,
        coin_name: coin.display_name,
        exchange: coin.exchange || 'BINANCE',
        available_qty: coin.total_qty,
        avg_cost: coin.avg_cost,
        cost: coin.avg_cost,
        qty: Number(suggestedQty.toFixed(8)),
        price: suggestedPrice,
        fee_amount: '',
        fee_asset: 'BNB',
        fee_usd: 0,
        cost_method: 'Konsolide Ortalama'
      };
      this.showTargetModal = false;
      this.showSellModal = true;
      this.$nextTick(() => {
        if (window.lucide) lucide.createIcons();
      });
    },

    get activeLotsForSelling() {
      const sym = (this.sellForm.coin_name || '').toUpperCase().trim();
      const exch = (this.sellForm.exchange || 'BINANCE').toUpperCase().trim();
      return this.transactions.filter(t => {
        if (t.status !== 'Aktif') return false;
        const tc = (t.coin || '').toUpperCase().trim();
        const te = (t.exchange || 'BINANCE').toUpperCase().trim();
        const matchCoin = (tc === sym) || (tc.replace('USDT', '') === sym.replace('USDT', ''));
        const matchEx = (te === exch) || (exch.startsWith('DEX') && te.startsWith('DEX'));
        return matchCoin && matchEx;
      }).sort((a, b) => (a.id || 0) - (b.id || 0));
    },

    get fifoPlan() {
      const qty = parseFloat(this.sellForm.qty) || 0;
      const lots = this.activeLotsForSelling;
      if (qty <= 0 || !lots || lots.length === 0) return [];
      
      let remaining = qty;
      const plan = [];
      for (const lot of lots) {
        if (remaining <= 0) break;
        const lotQty = parseFloat(lot.qty) || 0;
        const takeQty = Math.min(lotQty, remaining);
        const isFull = lotQty <= remaining + 1e-8;
        plan.push({
          id: lot.id,
          date: lot.date,
          cost: parseFloat(lot.cost) || 0,
          lotQty: lotQty,
          takeQty: takeQty,
          isFull: isFull
        });
        remaining -= takeQty;
      }
      return plan;
    },

    get effectiveSellCost() {
      if (this.sellForm.cost_method === 'FIFO') {
        const plan = this.fifoPlan;
        if (!plan || plan.length === 0) return parseFloat(this.sellForm.cost) || 0;
        let totalCost = 0;
        let totalQty = 0;
        for (const p of plan) {
          totalCost += p.takeQty * p.cost;
          totalQty += p.takeQty;
        }
        return totalQty > 0 ? (totalCost / totalQty) : (parseFloat(this.sellForm.cost) || 0);
      } else {
        return parseFloat(this.sellForm.avg_cost) || parseFloat(this.sellForm.cost) || 0;
      }
    },

    setSellPercent(pct) {
      const maxQty = this.sellForm.available_qty || (this.sellingTx ? this.sellingTx.qty : (this.sellingCoin ? this.sellingCoin.total_qty : 0));
      this.sellForm.qty = (parseFloat(maxQty) * pct).toFixed(8).replace(/\.?0+$/, "");
    },

    get calculatedSellPnl() {
      const qty = parseFloat(this.sellForm.qty) || 0;
      const sellP = parseFloat(this.sellForm.price) || 0;
      const cost = this.effectiveSellCost;
      const grossPnl = (sellP - cost) * qty;
      const feeUsd = this.calculateFeeInUsd(this.sellForm.fee_amount, this.sellForm.fee_asset, qty * sellP);
      return grossPnl - feeUsd;
    },

    async confirmSellTransaction() {
      const qty = parseFloat(this.sellForm.qty);
      const price = parseFloat(this.sellForm.price);
      if (!qty || qty <= 0 || !price || price <= 0) {
        this.notify('Lütfen geçerli bir adet ve borsada gerçekleşen birim satış fiyatı girin.', 'warning');
        return;
      }

      const feeAmt = parseFloat(this.sellForm.fee_amount) || 0;
      const feeAst = this.sellForm.fee_asset || 'USDT';
      const feeUsd = this.calculateFeeInUsd(feeAmt, feeAst, qty * price);
      const costMethod = this.sellForm.cost_method || 'Konsolide Ortalama';

      try {
        let res;
        if (this.sellingTx) {
          res = await fetch(`/api/transactions/${this.sellingTx.id}/sell`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              sell_qty: qty,
              sell_price: price,
              fee_amount: feeAmt,
              fee_asset: feeAst,
              fee_usd: feeUsd,
              cost_method: costMethod
            })
          });
        } else if (this.sellingCoin) {
          res = await fetch(`/api/targets/${encodeURIComponent(this.sellingCoin.pos_key)}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              sell_qty: qty,
              sell_price: price,
              fee_amount: feeAmt,
              fee_asset: feeAst,
              fee_usd: feeUsd,
              cost_method: costMethod
            })
          });
        }

        if (res && res.ok) {
          this.showSellModal = false;
          this.notify('Satış başarıyla deftere işlendi ve kasanıza nakit eklendi!', 'success');
          this.fetchPortfolio(true);
        } else {
          this.notify('Satış kaydı sırasında bir hata oluştu.', 'error');
        }
      } catch (e) {
        console.error(e);
        this.notify('Bağlantı hatası.', 'error');
      }
    },

    // -------------------------------------------------------------
    // FAZ 2: AKILLI DCA MALİYET DÜŞÜRME HESAPLAYICISI (WHAT-IF METHODS)
    // -------------------------------------------------------------
    openDcaModal(coin) {
      this.dcaCoin = coin;
      const exch = coin.exchange || 'BINANCE';
      let exchCash = 100;
      if (this.exchangeKpis && this.exchangeKpis[exch]) {
        exchCash = this.exchangeKpis[exch].usdt_cash || 0;
      } else if (this.kpis) {
        exchCash = this.kpis.usdt_cash || 0;
      }
      
      const defaultInvest = exchCash > 0 ? Math.min(100, Math.max(25, (exchCash * 0.25))) : 50;

      this.dcaForm = {
        pos_key: coin.pos_key,
        coin_name: coin.display_name,
        exchange: exch,
        current_qty: coin.total_qty || 0,
        current_avg_cost: coin.avg_cost || 0,
        live_price: coin.live_price || 0,
        buy_price: coin.live_price || coin.avg_cost || 1,
        invest_amount: Number(defaultInvest.toFixed(2)),
        deduct_cash: true,
        notes: ''
      };
      this.showDcaModal = true;
      this.$nextTick(() => {
        if (window.lucide) lucide.createIcons();
      });
    },

    setDcaAmount(amt) {
      this.dcaForm.invest_amount = amt;
    },

    setDcaCashPercent(pct) {
      const exch = this.dcaForm.exchange || 'BINANCE';
      let avail = (this.exchangeKpis[exch] ? this.exchangeKpis[exch].usdt_cash : this.kpis.usdt_cash) || 0;
      this.dcaForm.invest_amount = Number((avail * pct).toFixed(2));
    },

    setDcaDipPercent(pct) {
      if (!this.dcaForm.live_price) return;
      this.dcaForm.buy_price = Number((this.dcaForm.live_price * (1 + pct)).toFixed(8).replace(/\.?0+$/, ""));
    },

    setDcaLivePrice() {
      if (!this.dcaForm.live_price) return;
      this.dcaForm.buy_price = this.dcaForm.live_price;
    },

    get isDcaCoinInProfit() {
      if (!this.dcaForm.live_price || !this.dcaForm.current_avg_cost) return false;
      return this.dcaForm.live_price >= this.dcaForm.current_avg_cost;
    },

    get currentProfitMarginPct() {
      if (!this.dcaForm.live_price || !this.dcaForm.current_avg_cost) return 0;
      return ((this.dcaForm.live_price - this.dcaForm.current_avg_cost) / this.dcaForm.current_avg_cost) * 100;
    },

    get currentMaxPriceDropBufferPct() {
      if (!this.dcaForm.live_price || !this.dcaForm.current_avg_cost) return 0;
      const diff = this.dcaForm.live_price - this.dcaForm.current_avg_cost;
      return diff > 0 ? (diff / this.dcaForm.live_price * 100) : 0;
    },

    get currentBreakevenRisePct() {
      if (!this.dcaForm.live_price || !this.dcaForm.current_avg_cost) return 0;
      const diff = this.dcaForm.current_avg_cost - this.dcaForm.live_price;
      return diff > 0 ? (diff / this.dcaForm.live_price * 100) : 0;
    },

    get simulatedIsNewInProfit() {
      if (!this.dcaForm.live_price || !this.simulatedNewAvgCost) return false;
      return this.dcaForm.live_price >= this.simulatedNewAvgCost;
    },

    get simulatedNewProfitMarginPct() {
      if (!this.dcaForm.live_price || !this.simulatedNewAvgCost) return 0;
      return ((this.dcaForm.live_price - this.simulatedNewAvgCost) / this.simulatedNewAvgCost) * 100;
    },

    get simulatedNewMaxPriceDropBufferPct() {
      if (!this.dcaForm.live_price || !this.simulatedNewAvgCost) return 0;
      const diff = this.dcaForm.live_price - this.simulatedNewAvgCost;
      return diff > 0 ? (diff / this.dcaForm.live_price * 100) : 0;
    },

    get simulatedDcaQty() {
      const amt = parseFloat(this.dcaForm.invest_amount) || 0;
      const p = parseFloat(this.dcaForm.buy_price) || 0;
      if (amt <= 0 || p <= 0) return 0;
      return amt / p;
    },

    get simulatedTotalQty() {
      return (this.dcaForm.current_qty || 0) + this.simulatedDcaQty;
    },

    get simulatedTotalInvested() {
      const currentInv = (this.dcaForm.current_qty || 0) * (this.dcaForm.current_avg_cost || 0);
      const addInv = parseFloat(this.dcaForm.invest_amount) || 0;
      return currentInv + addInv;
    },

    get simulatedNewAvgCost() {
      if (this.simulatedTotalQty <= 0) return 0;
      return this.simulatedTotalInvested / this.simulatedTotalQty;
    },

    get simulatedCostReductionPct() {
      const cur = this.dcaForm.current_avg_cost || 0;
      const nw = this.simulatedNewAvgCost;
      if (cur <= 0 || nw <= 0) return 0;
      return ((cur - nw) / cur) * 100;
    },

    get simulatedNewBreakevenRise() {
      const live = this.dcaForm.live_price || 0;
      const nw = this.simulatedNewAvgCost;
      if (live <= 0 || nw <= 0) return 0;
      const diff = nw - live;
      return diff > 0 ? (diff / live * 100) : 0;
    },

    get simulatedBreakevenImprovement() {
      const oldReq = this.currentBreakevenRisePct;
      const nwReq = this.simulatedNewBreakevenRise;
      return Math.max(0, oldReq - nwReq);
    },

    get simulatedRemainingCash() {
      const exch = this.dcaForm.exchange || 'BINANCE';
      let avail = (this.exchangeKpis[exch] ? this.exchangeKpis[exch].usdt_cash : this.kpis.usdt_cash) || 0;
      return Math.max(0, avail - (parseFloat(this.dcaForm.invest_amount) || 0));
    },

    async confirmDcaBuyToLedger() {
      const amt = parseFloat(this.dcaForm.invest_amount);
      const price = parseFloat(this.dcaForm.buy_price);
      if (!amt || amt <= 0 || !price || price <= 0) {
        this.notify('Lütfen geçerli bir alım tutarı ve fiyat girin.', 'warning');
        return;
      }

      if (!await this.askConfirm({
        title: `${this.dcaForm.coin_name} alımı deftere eklensin mi?`,
        message: `$${price} fiyattan $${amt} tutarında alım kaydedilecek.`,
        detail: 'Bu işlem DCA işlem defterine yazılır ve ortalama maliyetini günceller.',
        confirmText: 'Deftere Ekle',
        tone: 'primary'
      })) {
        return;
      }

      try {
        const res = await fetch('/api/dca/execute', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            pos_key: this.dcaForm.pos_key,
            coin: this.dcaForm.coin_name,
            exchange: this.dcaForm.exchange,
            buy_qty: this.simulatedDcaQty,
            buy_price: price,
            invest_amount: amt,
            deduct_cash: this.dcaForm.deduct_cash,
            category: this.dcaCoin ? this.dcaCoin.category : 'Altcoin',
            notes: this.dcaForm.notes || `Akıllı DCA Alımı ($${amt})`
          })
        });

        if (res.ok) {
          this.notify('DCA alım işlemi başarıyla deftere işlendi ve portföyünüze eklendi!', 'success');
          this.showDcaModal = false;
          this.fetchPortfolio(true);
        } else {
          this.notify('DCA alımı kaydedilirken hata oluştu.', 'error');
        }
      } catch (e) {
        console.error(e);
        this.notify('Bağlantı hatası.', 'error');
      }
    },

    // Simulation Categories & Filters
    // -------------------------------------------------------------
    // BÖLÜM 4: SİMÜLASYON EKRANI FİLTRELERİ
    // -------------------------------------------------------------
    get availableSimCategories() {
      const predefined = ['Yapay Zeka (AI)', 'RWA', 'DeFi', 'Gaming / NFT', 'Meme'];
      const set = new Set([...this.simCategories, ...predefined]);
      return Array.from(set).filter(cat => this.countSimsByCategory(cat) > 0 || this.simCategories.includes(cat));
    },

    countSimsByCategory(cat) {
      return this.simulations.filter(s => (s.category || '').toLowerCase() === cat.toLowerCase()).length;
    },

    countDeadSims() {
      return this.simulations.filter(s => s.live_price <= 0 || (s.source && s.source.includes('Ölü'))).length;
    },

    get filteredSimulations() {
      let list = [...this.simulations];
      if (this.simCategoryFilter === 'dead') {
        list = list.filter(s => s.live_price <= 0 || (s.source && s.source.includes('Ölü')));
      } else if (this.simCategoryFilter !== 'all') {
        list = list.filter(s => (s.category || '').toLowerCase() === this.simCategoryFilter.toLowerCase());
      }
      if (this.searchQuery) {
        const q = this.searchQuery.toUpperCase().trim();
        list = list.filter(s => s.coin.toUpperCase().includes(q) || (s.notes && s.notes.toUpperCase().includes(q)));
      }

      list.sort((a, b) => {
        let valA = a[this.simSortKey];
        let valB = b[this.simSortKey];
        if (valA === undefined || valA === null) valA = 0;
        if (valB === undefined || valB === null) valB = 0;
        if (typeof valA === 'string') {
          return this.simSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        return this.simSortAsc ? (valA - valB) : (valB - valA);
      });

      return list;
    },

    get filteredSimTotals() {
      const list = this.filteredSimulations;
      let invested = 0;
      let value = 0;
      for (const s of list) {
        invested += (s.old_invested || 0);
        value += (s.sim_value || 0);
      }
      const pnl_usd = value - invested;
      const pnl_pct = invested > 0 ? (pnl_usd / invested * 100) : 0;
      return { invested, value, pnl_usd, pnl_pct };
    },

    // Sort Methods
    // -------------------------------------------------------------
    // BÖLÜM 5: SIRALAMA (Konsolide / Defter / Simülasyon)
    // -------------------------------------------------------------
    sortBy(key) {
      if (this.sortKey === key) {
        this.sortAsc = !this.sortAsc;
      } else {
        this.sortKey = key;
        this.sortAsc = false;
      }
    },

    sortLedgerBy(key) {
      if (this.ledgerSortKey === key) {
        this.ledgerSortAsc = !this.ledgerSortAsc;
      } else {
        this.ledgerSortKey = key;
        this.ledgerSortAsc = false;
      }
    },

    sortSimBy(key) {
      if (this.simSortKey === key) {
        this.simSortAsc = !this.simSortAsc;
      } else {
        this.simSortKey = key;
        this.simSortAsc = false;
      }
    },

    // Autocomplete Coin Input
    // -------------------------------------------------------------
    // BÖLÜM 6: COİN ARAMA & ÖNERİLER
    // -------------------------------------------------------------
    async onCoinInput() {
      const q = this.txForm.coin.trim();
      if (q.length < 1) {
        this.searchSuggestions = [];
        return;
      }
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        if (res.ok) {
          this.searchSuggestions = await res.json();
        }
      } catch (e) {}
    },

    selectSuggestion(item) {
      this.txForm.coin = item.symbol;
      let ex = (item.exchange || '').toUpperCase();
      if (ex.includes('DEX') || ex.includes('PANCAKE') || ex.includes('UNI')) {
        this.txForm.exchange = 'DEX';
      } else if (ex.includes('MEXC')) {
        this.txForm.exchange = 'MEXC';
      } else if (ex.includes('GATE')) {
        this.txForm.exchange = 'GATE.IO';
      } else {
        this.txForm.exchange = 'BINANCE';
      }

      if (item.price && !this.txForm.cost) {
        this.txForm.cost = item.price;
      }
      this.searchSuggestions = [];
    },

    // -------------------------------------------------------------
    // BÖLÜM 7: İŞLEM EKLE / DÜZENLE / SİL (DCA DEFTERİ CRUD)
    // -------------------------------------------------------------
    openAddModal(defaultStatus = 'Aktif') {
      this.isEditMode = false;
      // Zincirden gelme bayrağı her açılışta sıfırlanır; `addFromChain` bunu
      // çağrıdan SONRA kuruyor. Aksi hâlde vazgeçilen bir formun bayrağı
      // ilgisiz bir kayıtta karşılaştırmayı tetiklerdi.
      this.chainAddPending = false;
      this.txForm = {
        id: null,
        coin: '',
        date: '',
        qty: '',
        cost: '',
        status: defaultStatus,
        exchange: this.selectedKasaExchange !== 'ALL' ? this.selectedKasaExchange : 'BINANCE',
        notes: '',
        category: defaultStatus === 'Kapandı / İzleme' ? (this.simCategoryFilter !== 'all' && this.simCategoryFilter !== 'dead' ? this.simCategoryFilter : 'Gözlem / İzleme') : '',
        fee_amount: '',
        fee_asset: 'USDT',
        fee_usd: 0
      };
      this.searchSuggestions = [];
      this.showTxModal = true;
      this.$nextTick(() => {
        if (window.lucide) lucide.createIcons();
      });
    },

    openEditModal(item) {
      this.isEditMode = true;
      this.chainAddPending = false;
      this.txForm = {
        id: item.id,
        coin: item.coin,
        date: item.date || '',
        qty: item.qty,
        cost: item.cost || item.old_cost,
        status: item.status || (this.activeTab === 'simulation' ? 'Kapandı / İzleme' : 'Aktif'),
        exchange: item.exchange || 'BINANCE',
        notes: item.notes || '',
        category: item.category || '',
        fee_amount: item.fee_amount || '',
        fee_asset: item.fee_asset || 'USDT',
        fee_usd: item.fee_usd || 0
      };
      this.searchSuggestions = [];
      this.showTxModal = true;
      this.$nextTick(() => {
        if (window.lucide) lucide.createIcons();
      });
    },

    async saveTransaction() {
      try {
        const feeAmt = parseFloat(this.txForm.fee_amount) || 0;
        const feeAst = this.txForm.fee_asset || 'USDT';
        const feeUsd = this.calculateFeeInUsd(feeAmt, feeAst, parseFloat(this.txForm.qty || 0) * parseFloat(this.txForm.cost || 0));

        const payload = {
          coin: this.txForm.coin,
          // Boş bırakılırsa sunucu bugünü kullanır — eski davranış.
          date: (this.txForm.date || '').trim() || null,
          qty: parseFloat(this.txForm.qty),
          cost: parseFloat(this.txForm.cost),
          status: this.txForm.status,
          exchange: this.txForm.exchange,
          notes: this.txForm.notes,
          category: this.txForm.category,
          fee_amount: feeAmt,
          fee_asset: feeAst,
          fee_usd: feeUsd
        };

        let res;
        if (this.isEditMode && this.txForm.id) {
          res = await fetch(`/api/transactions/${this.txForm.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
        } else {
          res = await fetch('/api/transactions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
        }

        if (res.ok) {
          this.showTxModal = false;
          this.notify('İşlem başarıyla kaydedildi!', 'success');
          this.fetchPortfolio(true);
          // Zincir tablosundan gelindiyse karşılaştırma tazelenir; aksi hâlde
          // satır "Zincirde var" olarak kalır ve kullanıcı işin olmadığını sanır.
          if (this.chainAddPending) {
            this.chainAddPending = false;
            this.runConnectionReconcile();
          }
        } else {
          this.notify('İşlem kaydedilirken hata oluştu.', 'error');
        }
      } catch (e) {
        console.error(e);
        this.notify('Bağlantı hatası.', 'error');
      }
    },

    async toggleStatus(txId) {
      try {
        const res = await fetch(`/api/transactions/${txId}/status`, { method: 'PATCH' });
        if (res.ok) {
          this.notify('İşlem durumu güncellendi.', 'info');
          this.fetchPortfolio(true);
        }
      } catch (e) {
        console.error(e);
      }
    },

    async deleteTransaction(txId) {
      if (!await this.askConfirm({
        title: 'İşlem silinsin mi?',
        message: 'Bu kayıt işlem defterinden kalıcı olarak kaldırılacak.',
        detail: 'Ortalama maliyetin ve toplam pozisyonun yeniden hesaplanır.',
        confirmText: 'İşlemi Sil'
      })) return;
      try {
        const res = await fetch(`/api/transactions/${txId}`, { method: 'DELETE' });
        if (res.ok) {
          this.notify('İşlem başarıyla silindi.', 'info');
          this.fetchPortfolio(true);
        }
      } catch (e) {
        console.error(e);
      }
    },

    // 1-Click Backup Download & Restore
    // -------------------------------------------------------------
    // BÖLÜM 8: YEDEKLEME & GERİ YÜKLEME
    // -------------------------------------------------------------
    downloadBackupFile() {
      window.location.href = '/api/backup/download';
      this.notify('Yedek dosyası indiriliyor...', 'info');
    },

    async handleRestoreFile(event) {
      const file = event.target.files[0];
      if (!file) return;

      if (!await this.askConfirm({
        title: 'Yedek dosyası geri yüklensin mi?',
        message: 'Mevcut portföyünün yerine bu dosyadaki veriler yazılacak.',
        detail: 'Geri yüklemeden önce mevcut portföyünün otomatik güvenlik kopyası alınır.',
        confirmText: 'Geri Yükle'
      })) {
        event.target.value = '';
        return;
      }

      try {
        const reader = new FileReader();
        reader.onload = async (e) => {
          try {
            const jsonContent = JSON.parse(e.target.result);
            const res = await fetch('/api/backup/restore', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(jsonContent)
            });

            if (res.ok) {
              this.notify('Yedek başarıyla yüklendi!', 'success');
              this.fetchPortfolio(true);
            } else {
              this.notify('Yedek yükleme hatası: Geçersiz dosya yapısı.', 'error');
            }
          } catch (err) {
            this.notify('Dosya okunurken JSON hatası oluştu.', 'error');
          }
        };
        reader.readAsText(file);
      } catch (err) {
        console.error('Restore error:', err);
      } finally {
        event.target.value = '';
      }
    },

    // Interactive Notes Popover / Modal
    // -------------------------------------------------------------
    // BÖLÜM 9: NOTLAR
    // -------------------------------------------------------------
    openNotePopover(item) {
      this.selectedNoteTx = item;
      this.editingNoteText = item.notes || '';
      this.showNoteModal = true;
      this.$nextTick(() => {
        if (window.lucide) lucide.createIcons();
      });
    },

    async saveNoteFromModal() {
      if (!this.selectedNoteTx) return;
      try {
        const res = await fetch(`/api/transactions/${this.selectedNoteTx.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ notes: this.editingNoteText })
        });
        if (res.ok) {
          this.selectedNoteTx.notes = this.editingNoteText;
          this.showNoteModal = false;
          this.fetchPortfolio(false);
        }
      } catch (e) {
        console.error(e);
      }
    },

    // -------------------------------------------------------------
    // BÖLÜM 10: CÜZDAN & KASA YÖNETİMİ
    // -------------------------------------------------------------
    openWalletModal() {
      // Bilinen her konumun bir nakit kutusu olmalı. Kullanıcı transferle
      // METAMASK yarattıysa cüzdan ekranında da yeri olsun; eksik anahtar
      // yüzünden konum görünmez kalmasın.
      this.knownLocations.forEach(loc => {
        if (this.walletForm.exchange_cash[loc] === undefined) {
          this.walletForm.exchange_cash[loc] = 0;
        }
      });
      this.newLocationName = '';
      this.showWalletModal = true;
      this.$nextTick(() => {
        if (window.lucide) lucide.createIcons();
      });
    },

    addLocation() {
      const ad = this.normalizeLocation(this.newLocationName);
      if (!ad || ad === 'BINANCE' && !this.newLocationName.trim()) return;
      if (this.walletForm.exchange_cash[ad] !== undefined) {
        this.notify(`${ad} zaten listede.`, 'info');
        this.newLocationName = '';
        return;
      }
      this.walletForm.exchange_cash[ad] = 0;
      if (!this.locations.includes(ad)) this.locations = [...this.locations, ad];
      this.newLocationName = '';
      this.notify(`${ad} eklendi. Kaydedince kalıcı olur.`, 'success');
    },

    removeLocation(loc) {
      // Varsayılan dördü ve varlık/nakit barındıran konumlar silinemez —
      // silinirse o konumdaki pozisyon ekranda sahipsiz kalır.
      if (['BINANCE', 'MEXC', 'GATE.IO', 'DEX'].includes(loc)) return;
      if (this.countCoinsByExchange(loc) > 0) {
        this.notify(`${loc} üzerinde açık pozisyon var, kaldırılamaz.`, 'warning', 4500);
        return;
      }
      if (parseFloat(this.walletForm.exchange_cash[loc] || 0) !== 0) {
        this.notify(`${loc} nakit bakiyesi sıfır değil, kaldırılamaz.`, 'warning', 4500);
        return;
      }
      delete this.walletForm.exchange_cash[loc];
      this.locations = this.locations.filter(l => l !== loc);
    },

    async saveWallets() {
      try {
        // Sabit dört anahtar yerine formdaki tüm konumlar gönderilir.
        const exCash = {};
        for (const [loc, val] of Object.entries(this.walletForm.exchange_cash || {})) {
          exCash[loc] = parseFloat(val || 0) || 0;
        }
        const totalVal = Object.values(exCash).reduce((a, b) => a + b, 0);

        const res = await fetch('/api/wallets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            usdt_cash: totalVal,
            exchange_cash: exCash,
            futures_balance: parseFloat(this.walletForm.futures_balance || 0),
            margin_balance: parseFloat(this.walletForm.margin_balance || 0)
          })
        });
        if (res.ok) {
          this.showWalletModal = false;
          this.fetchPortfolio(true);
        }
      } catch (e) {
        console.error(e);
      }
    },

    // -------------------------------------------------------------
    // FAZ 3: TRADINGVIEW, ISI HARİTASI & PORTFÖY SAĞLIK ANALİZİ
    // -------------------------------------------------------------
    get currentTvCoin() {
      if (this.selectedTvPosKey) {
        const found = this.consolidatedCoins.find(c => (c.pos_key === this.selectedTvPosKey || c.symbol === this.selectedTvPosKey || c.display_name === this.selectedTvPosKey));
        if (found) return found;
      }
      if (this.selectedTvCoin && typeof this.selectedTvCoin === 'object' && this.selectedTvCoin.display_name) {
        return this.selectedTvCoin;
      }
      if (this.consolidatedCoins && this.consolidatedCoins.length > 0) {
        return this.consolidatedCoins[0];
      }
      return null;
    },

    // Zincir üstü mü? Artık fiyatın GERÇEKTE nereden geldiğine bakılır.
    // Eskiden burada `sym.includes('CPL') || sym.includes('SCM')` gibi
    // sabit sembol kontrolleri vardı: içinde "SCM" geçen her coin DEX
    // sayılıyor, borsada işlem gören bir token bile DexScreener'a
    // yönlendiriliyordu. Ayrıca borsası "DEX" yazan cüzdan pozisyonları
    // (BNB, SOL, ETH) da yanlışlıkla bu dala düşüyordu.
    isDexCoin(coin) {
      if (!coin) return false;
      return Boolean(coin.is_dex);
    },

    // Sembolü borsa çifti ekinden arındırır (SCMUSDT → SCM).
    // DexScreener'da "SCMUSDT" diye bir token yoktur; eki temizlemeyen
    // arama "No results found" ekranı döndürüyordu.
    baseSymbol(coin) {
      let sym = String((coin && (coin.display_name || coin.symbol)) || '').toUpperCase().trim();
      return sym.replace(/(USDT|USDC|WBNB|BUSD)$/, '').replace(/[\/_-]/g, '') || sym;
    },

    getDexEmbedUrl(coin) {
      if (!coin) return '';
      if (coin.dex_embed_url) return coin.dex_embed_url;
      if (coin.pair_address && coin.chain_id) {
        return `https://dexscreener.com/${coin.chain_id}/${coin.pair_address}?embed=1&theme=dark&trades=0&info=0`;
      }
      const base = this.baseSymbol(coin);
      if (!base) return '';
      return `https://dexscreener.com/search?q=${encodeURIComponent(base)}&embed=1&theme=dark`;
    },

    getDextoolsUrl(coin) {
      if (!coin) return 'https://www.dextools.io';
      if (coin.dextools_url) return coin.dextools_url;
      if (coin.pair_address) {
        const chain = coin.chain_id === 'bsc' ? 'bnb' : (coin.chain_id || 'bnb');
        return `https://www.dextools.io/app/${chain}/pair-explorer/${coin.pair_address}`;
      }
      return `https://www.dextools.io`;
    },

    // TradingView sembolü, fiyatın geldiği kaynağa göre kurulur —
    // pozisyonun kayıtlı borsasına göre değil. Bir coini WhiteBIT'ten
    // fiyatlıyorsak grafiği de orada aramak gerekir.
    getTvSymbol(coin) {
      if (!coin) return 'BINANCE:BTCUSDT';
      const src = String(coin.source || coin.exchange || 'BINANCE').toUpperCase();
      let sym = (coin.symbol || coin.display_name || 'BTCUSDT').toUpperCase().trim();
      if (!sym.endsWith('USDT') && !sym.includes('/')) sym += 'USDT';

      if (src.includes('MEXC')) return `MEXC:${sym}`;
      if (src.includes('GATE')) return `GATEIO:${sym}`;
      if (src.includes('WHITEBIT')) return `WHITEBIT:${sym}`;
      return `BINANCE:${sym}`;
    },

    getTvExternalUrl(coin) {
      if (this.isDexCoin(coin)) {
        return this.getDextoolsUrl(coin);
      }
      const sym = this.getTvSymbol(coin);
      return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(sym)}`;
    },

    selectCoinForTv(coin) {
      if (!coin) return;
      this.selectedTvCoin = coin;
      this.selectedTvPosKey = coin.pos_key || coin.symbol || coin.display_name;
      this.tvSubTab = 'tv';
      this.initTradingView(coin);
    },

    initTradingView(coin = null) {
      const targetCoin = coin || this.currentTvCoin;
      if (!targetCoin) return;

      this.$nextTick(() => {
        const container = document.getElementById('tv_chart_container');
        if (!container) return;
        container.innerHTML = '';

        // Fiyat kaynağı olmayan coin için grafik de yoktur. Eskiden bu durumda
        // DexScreener'a boş bir arama gömülüyordu ve kullanıcı "No results found"
        // artı reklam katmanı görüyordu. Artık durum açıkça söylenir.
        if (targetCoin.no_source) {
          container.innerHTML = `
            <div class="w-full h-full flex flex-col items-center justify-center bg-slate-950 text-center px-6 space-y-3">
              <div class="text-4xl">🔌</div>
              <div class="text-slate-200 font-bold">${this.escapeHtml(targetCoin.display_name || '')} için fiyat kaynağı tanımlı değil</div>
              <div class="text-slate-500 text-xs max-w-md leading-relaxed">
                Bu coin hiçbir etkin kademede bulunamadı; bu yüzden canlı grafiği de yok.
                Ayarlar → Fiyat Kaynakları bölümünden bu sembol için bir kaynak tanımlayın
                (borsa + market adı, kontrat adresi veya manuel fiyat).
              </div>
            </div>
          `;
          return;
        }

        if (this.isDexCoin(targetCoin)) {
          const embedUrl = this.getDexEmbedUrl(targetCoin);
          if (!embedUrl) {
            container.innerHTML = `
              <div class="w-full h-full flex items-center justify-center bg-slate-950 text-slate-500 text-sm">
                Bu zincir üstü token için grafik adresi bulunamadı.
              </div>
            `;
            return;
          }
          container.innerHTML = `
            <div class="w-full h-full relative bg-slate-950 flex flex-col">
              <iframe src="${embedUrl}" class="w-full h-full border-0" allow="clipboard-write" allowfullscreen></iframe>
            </div>
          `;
          return;
        }

        const tvSym = this.getTvSymbol(targetCoin);
        if (window.TradingView) {
          try {
            new TradingView.widget({
              autosize: true,
              symbol: tvSym,
              interval: this.tvInterval,
              timezone: "Etc/UTC",
              theme: "dark",
              style: "1",
              locale: "tr",
              toolbar_bg: "#0f172a",
              enable_publishing: false,
              hide_top_toolbar: false,
              hide_side_toolbar: false,
              allow_symbol_change: true,
              save_image: true,
              container_id: "tv_chart_container",
              studies: [
                "MASimple@tv-basicstudies",
                "RSI@tv-basicstudies"
              ]
            });
          } catch (e) {
            console.error('TV Widget error:', e);
          }
        }
      });
    },

    // -------------------------------------------------------------
    // FAZ 4: 7 GÜNLÜK SPARKLINE VEKTÖREL MOTORU
    // -------------------------------------------------------------
    getSparklineSvg(coin) {
      const points = coin.sparkline_7d;
      if (!points || !Array.isArray(points) || points.length < 2) {
        return '<div class="text-[10px] text-slate-600 text-center">-</div>';
      }
      const w = 96;
      const h = 30;
      const pad = 3;
      const min = Math.min(...points);
      const max = Math.max(...points);
      const range = (max - min) || (min > 0 ? min * 0.01 : 1);

      const coords = points.map((p, i) => {
        const x = (i / (points.length - 1)) * (w - 6) + 3;
        const y = (h - pad * 2) - (((p - min) / range) * (h - pad * 2)) + pad;
        return { x: Number(x.toFixed(1)), y: Number(y.toFixed(1)) };
      });

      let lineD = `M ${coords[0].x} ${coords[0].y}`;
      for (let i = 1; i < coords.length; i++) {
        const prev = coords[i - 1];
        const curr = coords[i];
        const cp1x = (prev.x + (curr.x - prev.x) / 2).toFixed(1);
        const cp2x = cp1x;
        lineD += ` C ${cp1x} ${prev.y} ${cp2x} ${curr.y} ${curr.x} ${curr.y}`;
      }

      const lastX = coords[coords.length - 1].x;
      const firstX = coords[0].x;
      const areaD = `${lineD} L ${lastX} ${h} L ${firstX} ${h} Z`;

      const isUp = points[points.length - 1] >= points[0];
      const strokeColor = isUp ? '#10b981' : '#f43f5e';
      const gradId = 'sp_grad_' + (coin.pos_key || coin.symbol || Math.random().toString()).replace(/[^a-zA-Z0-9]/g, '_');

      return `
        <svg viewBox="0 0 ${w} ${h}" class="w-full h-7 overflow-visible" preserveAspectRatio="none">
          <defs>
            <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="${strokeColor}" stop-opacity="0.30" />
              <stop offset="100%" stop-color="${strokeColor}" stop-opacity="0.0" />
            </linearGradient>
          </defs>
          <path d="${areaD}" fill="url(#${gradId})" />
          <path d="${lineD}" fill="none" stroke="${strokeColor}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      `;
    },

    // Category Breakdown (including Serbest Nakit)
    // -------------------------------------------------------------
    // BÖLÜM 11: KATEGORİ DAĞILIMI & PORTFÖY SAĞLIK SKORU
    // -------------------------------------------------------------
    get categoryBreakdown() {
      const map = {};
      let totalPortfolio = (this.kpis.spot_current_value || 0) + (this.kpis.usdt_cash || 0);

      // Spot coins
      for (const c of this.consolidatedCoins) {
        const cat = c.category || 'Diğer';
        if (!map[cat]) map[cat] = { category: cat, value: 0, count: 0 };
        map[cat].value += (c.current_value || 0);
        map[cat].count += 1;
      }

      // Cash
      if (this.kpis.usdt_cash > 0) {
        map['Serbest Nakit (USDT)'] = {
          category: 'Serbest Nakit (USDT)',
          value: this.kpis.usdt_cash,
          count: 1
        };
      }

      const list = Object.values(map).map(item => {
        const share = totalPortfolio > 0 ? (item.value / totalPortfolio * 100) : 0;
        return {
          category: item.category,
          value: item.value,
          share_pct: share,
          count: item.count
        };
      });

      list.sort((a, b) => b.value - a.value);
      return list;
    },

    // Portfolio Health & Risk Analysis Engine
    get portfolioHealthScore() {
      const totalPortfolio = (this.kpis.spot_current_value || 0) + (this.kpis.usdt_cash || 0);
      if (totalPortfolio <= 0) {
        return { score: 100, label: 'Boş Portföy', color: 'text-slate-400', badgeClass: 'bg-slate-800 text-slate-300', tips: [] };
      }

      const cashRatio = (this.kpis.usdt_cash / totalPortfolio) * 100;
      
      let majorVal = 0;
      let speculativeVal = 0;

      for (const c of this.consolidatedCoins) {
        const name = c.display_name.toUpperCase();
        const cat = (c.category || '').toLowerCase();
        if (name.includes('BTC') || name.includes('ETH') || name.includes('SOL') || name.includes('XAUT')) {
          majorVal += (c.current_value || 0);
        } else if (cat.includes('meme') || cat.includes('dex') || name.includes('CPL') || name.includes('PEPE') || name.includes('DOGE') || name.includes('SHIB')) {
          speculativeVal += (c.current_value || 0);
        }
      }

      const majorRatio = (majorVal / totalPortfolio) * 100;
      const specRatio = (speculativeVal / totalPortfolio) * 100;

      let score = 0;
      const tips = [];

      // 1. Cash Buffer Score (max 30 pts)
      if (cashRatio >= 15 && cashRatio <= 35) {
        score += 30;
        tips.push(`✅ Nakit Tamponu Mükemmel: Portföyün %${cashRatio.toFixed(1)}'i serbest USDT nakitte. Olası piyasa düşüşlerinde kademeli DCA için güçlü cephaneniz var.`);
      } else if (cashRatio > 35) {
        score += 24;
        tips.push(`ℹ️ Yüksek Nakit Oranı (%${cashRatio.toFixed(1)}): Portföyünüz çok defansif. Uygun dip seviyelerde alım fırsatlarını değerlendirebilirsiniz.`);
      } else if (cashRatio >= 5) {
        score += 18;
        tips.push(`⚠️ Düşük Nakit Tamponu (%${cashRatio.toFixed(1)}): Kasanızdaki nakit oranı %15'in altında. Ani düşüşlerde DCA yapabilmek için kâr realizasyonu düşünebilirsiniz.`);
      } else {
        score += 8;
        tips.push(`🚨 Kritik Nakit Seviyesi (%${cashRatio.toFixed(1)}): Neredeyse hiç serbest nakdiniz yok (%100 malda). Portföy yüksek piyasa volatilitesine karşı savunmasız.`);
      }

      // 2. Major Asset Backbone Score (max 40 pts)
      if (majorRatio >= 45) {
        score += 40;
        tips.push(`✅ Güçlü Omurga: BTC, ETH, SOL ve Altın varlıklarınız portföyün %${majorRatio.toFixed(1)}'ini oluşturuyor. Çöküşlere karşı direnciniz yüksek.`);
      } else if (majorRatio >= 25) {
        score += 28;
        tips.push(`⚖️ Dengeli Altcoin Ağırlığı: Majör varlık oranınız %${majorRatio.toFixed(1)}. Boğa piyasalarında yüksek getiri potansiyeli sağlar.`);
      } else {
        score += 15;
        tips.push(`⚠️ Zayıf Majör Ağırlığı (%${majorRatio.toFixed(1)}): Portföyünüz büyük ölçüde altcoin ve küçük hacimli varlıklardan oluşuyor. Sert piyasa düzeltmelerinde düşüş riski artabilir.`);
      }

      // 3. Speculative / Meme Risk Score (max 30 pts)
      if (specRatio <= 10) {
        score += 30;
        tips.push(`✅ Düşük Spekülatif Risk: Meme ve yüksek riskli DEX varlıkları portföyün sadece %${specRatio.toFixed(1)}'i.`);
      } else if (specRatio <= 25) {
        score += 20;
        tips.push(`⚖️ Kontrollü Spekülasyon: Meme varlık oranınız %${specRatio.toFixed(1)} seviyesinde.`);
      } else {
        score += 5;
        tips.push(`🚨 Yüksek Spekülatif / Meme Riski (%${specRatio.toFixed(1)}): Yüksek riskli meme ve DEX tokenları sepetin %25'inden fazlasını kaplıyor. Ani likidite kayıplarına dikkat edin.`);
      }

      let label = '🛡️ Güçlü & Dengeli Portföy (Düşük Risk)';
      let badgeClass = 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40';
      if (score < 60) {
        label = '⚠️ Yüksek Volatilite & Spekülatif Risk';
        badgeClass = 'bg-rose-500/20 text-rose-300 border border-rose-500/40';
      } else if (score < 80) {
        label = '⚡ Büyüme Odaklı & Orta Risk';
        badgeClass = 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40';
      }

      return { score, label, badgeClass, cashRatio, majorRatio, specRatio, tips };
    },

    showAllGainers: false,
    showAllLosers: false,

    // Institutional Performance & Leaderboard Getters
    // -------------------------------------------------------------
    // BÖLÜM 12: KAZANAN/KAYBEDEN LİSTELERİ & ISI HARİTASI VERİSİ
    // -------------------------------------------------------------
    get topGainers() {
      return this.consolidatedCoins
        .filter(c => c.pnl_usd > 0)
        .sort((a, b) => b.pnl_usd - a.pnl_usd);
    },

    get displayedGainers() {
      if (this.showAllGainers) return this.topGainers;
      return this.topGainers.slice(0, 5);
    },

    get topLosers() {
      return this.consolidatedCoins
        .filter(c => c.pnl_usd < 0)
        .sort((a, b) => a.pnl_usd - b.pnl_usd);
    },

    get displayedLosers() {
      if (this.showAllLosers) return this.topLosers;
      return this.topLosers.slice(0, 5);
    },

    get maxGainPnl() {
      if (!this.topGainers || this.topGainers.length === 0) return 1;
      return Math.max(...this.topGainers.map(c => c.pnl_usd)) || 1;
    },

    get maxLossPnl() {
      if (!this.topLosers || this.topLosers.length === 0) return 1;
      return Math.max(...this.topLosers.map(c => Math.abs(c.pnl_usd))) || 1;
    },

    get totalPortfolioNetPnl() {
      return this.consolidatedCoins.reduce((sum, c) => sum + (c.pnl_usd || 0), 0);
    },

    get exchangeCapitalList() {
      const totalPortfolio = (this.kpis.spot_current_value || 0) + (this.kpis.usdt_cash || 0);
      // FAZ F1c — Bu liste eskiden koda gömülüydü: ['BINANCE','MEXC','GATE.IO','DEX'].
      // Transfer özelliği kullanıcının kendi konumunu (METAMASK, LEDGER…)
      // yaratmasına izin veriyor; sabit liste yüzünden varlık orada duruyor
      // ama Kasa ekranında hiç görünmüyordu. Artık veriden türetiliyor.
      const exList = this.knownLocations;
      const currentExchangeCash = (this.kpis && this.kpis.exchange_cash) ? this.kpis.exchange_cash : (this.walletForm ? this.walletForm.exchange_cash : {});

      return exList.map(ex => {
        const spotVal = this.consolidatedCoins
          .filter(c => (c.exchange || 'BINANCE').toUpperCase() === ex)
          .reduce((sum, c) => sum + (c.current_value || 0), 0);
        const cashVal = (currentExchangeCash && currentExchangeCash[ex]) ? parseFloat(currentExchangeCash[ex]) : 0;
        const totalExVal = spotVal + cashVal;
        const sharePct = totalPortfolio > 0 ? (totalExVal / totalPortfolio * 100) : 0;
        return {
          exchange: ex,
          spot_value: spotVal,
          cash_value: cashVal,
          total_value: totalExVal,
          share_pct: sharePct
        };
      }).filter(e => e.total_value > 0);
    },

    // Chart.js Rendering (Jitter-free smooth update)
    // -------------------------------------------------------------
    // BÖLÜM 13: CHART.JS GRAFİK YÖNETİMİ
    // -------------------------------------------------------------
    renderCharts() {
      // If tvSubTab is TV, init TradingView widget
      if (this.tvSubTab === 'tv') {
        this.initTradingView();
      }

      const topCoins = this.consolidatedCoins.slice(0, 8);
      const labels = topCoins.map(c => c.display_name + ' (' + c.exchange + ')');
      const values = topCoins.map(c => c.current_value);
      const pnls = topCoins.map(c => c.pnl_usd);

      // Donut Chart for Categories
      const ctxCat = document.getElementById('categoryDonutChart');
      if (ctxCat) {
        if (this.categoryChart) this.categoryChart.destroy();
        const catList = this.categoryBreakdown;
        this.categoryChart = new Chart(ctxCat, {
          type: 'doughnut',
          data: {
            labels: catList.map(c => c.category),
            datasets: [{
              data: catList.map(c => c.value),
              backgroundColor: [
                '#10b981', '#3b82f6', '#8b5cf6', '#f59e0b',
                '#ec4899', '#06b6d4', '#6366f1', '#14b8a6', '#64748b'
              ],
              borderColor: '#0f172a',
              borderWidth: 2
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 600 },
            plugins: {
              legend: { position: 'right', labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } } }
            }
          }
        });
      }

      // Allocation Chart
      const ctxAlloc = document.getElementById('allocationChart');
      if (ctxAlloc) {
        if (this.allocationChart) this.allocationChart.destroy();
        this.allocationChart = new Chart(ctxAlloc, {
          type: 'doughnut',
          data: {
            labels: labels,
            datasets: [{
              data: values,
              backgroundColor: [
                '#10b981', '#3b82f6', '#8b5cf6', '#f59e0b',
                '#ec4899', '#06b6d4', '#6366f1', '#64748b'
              ],
              borderColor: '#0f172a',
              borderWidth: 2
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 600 },
            plugins: {
              legend: { position: 'right', labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } } }
            }
          }
        });
      }

      // Bar Chart
      const ctxPnl = document.getElementById('pnlChart');
      if (ctxPnl) {
        if (this.pnlChart) this.pnlChart.destroy();
        this.pnlChart = new Chart(ctxPnl, {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [{
              label: 'Net Kâr / Zarar ($)',
              data: pnls,
              backgroundColor: pnls.map(p => p >= 0 ? '#10b981' : '#f43f5e'),
              borderRadius: 6
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 600 },
            plugins: {
              legend: { display: false }
            },
            scales: {
              x: { ticks: { color: '#94a3b8', font: { family: 'Inter', size: 10 } }, grid: { display: false } },
              y: { ticks: { color: '#94a3b8', font: { family: 'Inter', size: 10 } }, grid: { color: '#1e293b' } }
            }
          }
        });
      }
    },

    updateChartsData() {
      if (this.categoryChart) {
        const catList = this.categoryBreakdown;
        this.categoryChart.data.labels = catList.map(c => c.category);
        this.categoryChart.data.datasets[0].data = catList.map(c => c.value);
        this.categoryChart.update('none');
      }

      if (!this.allocationChart || !this.pnlChart) return;
      const topCoins = this.consolidatedCoins.slice(0, 8);
      const labels = topCoins.map(c => c.display_name + ' (' + c.exchange + ')');
      const values = topCoins.map(c => c.current_value);
      const pnls = topCoins.map(c => c.pnl_usd);

      this.allocationChart.data.labels = labels;
      this.allocationChart.data.datasets[0].data = values;
      this.allocationChart.update('none');

      this.pnlChart.data.labels = labels;
      this.pnlChart.data.datasets[0].data = pnls;
      this.pnlChart.data.datasets[0].backgroundColor = pnls.map(p => p >= 0 ? '#10b981' : '#f43f5e');
      this.pnlChart.update('none');
    },

    // -------------------------------------------------------------
    // FAZ 5: SETTINGS & HEALTH CHECK METHODS
    // -------------------------------------------------------------
    async fetchSettings() {
      try {
        const resp = await fetch('/api/settings');
        if (resp.ok) {
          const data = await resp.json();
          this.settings = {
            api_urls: { ...this.settings.api_urls, ...(data.api_urls || {}) },
            api_keys: { ...this.settings.api_keys, ...(data.api_keys || {}) },
            preferences: { ...this.settings.preferences, ...(data.preferences || {}) }
          };
          // Karşılaştırma tablosunun katlama eşiği tercihlerde saklanıyor;
          // her açılışta kullanıcının seçtiği değerle gelsin.
          const esik = parseFloat(this.settings.preferences.reconcile_dust_usd);
          if (esik >= 0) this.connDustUsd = esik;
        }
      } catch (e) {
        console.error('Error fetching settings:', e);
      }
    },

    async saveSettings() {
      try {
        const resp = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.settings)
        });
        if (resp.ok) {
          this.settingsSaveSuccess = true;
          setTimeout(() => { this.settingsSaveSuccess = false; }, 3000);
          this.restartBackgroundLoop();
        }
      } catch (e) {
        this.notify('Ayarlar kaydedilirken hata oluştu: ' + e.message, 'error');
      }
    },

    // -------------------------------------------------------------
    // UYGULAMA İÇİ ONAY PENCERESİ
    // -------------------------------------------------------------
    // Promise döndürür; çağıran taraf `await askConfirm(...)` ile bekler.
    // Girdi istenirse sayı, istenmezse true/false döner; iptalde null/false.
    askConfirm(opts = {}) {
      this.confirmDialog = {
        open: true,
        title: opts.title || 'Emin misiniz?',
        message: opts.message || '',
        detail: opts.detail || '',
        confirmText: opts.confirmText || 'Onayla',
        tone: opts.tone || 'danger',
        withInput: !!opts.withInput,
        inputLabel: opts.inputLabel || '',
        inputValue: opts.inputValue != null ? opts.inputValue : '',
        inputSuffix: opts.inputSuffix || ''
      };
      return new Promise(resolve => { this._confirmResolve = resolve; });
    },

    resolveConfirm(onaylandi) {
      const d = this.confirmDialog;
      const cevap = !onaylandi ? (d.withInput ? null : false)
                               : (d.withInput ? Number(d.inputValue) : true);
      this.confirmDialog.open = false;
      if (this._confirmResolve) {
        this._confirmResolve(cevap);
        this._confirmResolve = null;
      }
    },

    // -------------------------------------------------------------
    // FAZ F1: DEĞER KAYBI YAZIMI (MEZARLIK) VE TRANSFER
    // -------------------------------------------------------------
    // İki olay bilinçli olarak ayrı tutulur:
    //   Yazım    → coin öldü, maliyet zarar yazılır, NAKİT GELMEZ.
    //   Transfer → coin yaşıyor, yer değiştirdi, maliyet tabanı korunur.
    // Arayüzün görevi bu ayrımı kullanıcıya net göstermek.

    _applyLedgerSnapshot(body) {
      if (!body) return;
      if (body.kpis) this.kpis = body.kpis;
      if (body.consolidated_coins) this.consolidatedCoins = body.consolidated_coins;
      if (body.transfers) this.transfers = body.transfers;
      if (body.write_offs) this.writeOffs = body.write_offs;
      if (body.rebuilds) this.rebuilds = body.rebuilds;
    },

    async fetchLedgerHistory() {
      try {
        const [tr, wo, rb] = await Promise.all([
          fetch('/api/transfers').then(r => r.json()),
          fetch('/api/write-offs').then(r => r.json()),
          fetch('/api/rebuilds').then(r => r.json())
        ]);
        this.transfers = tr.transfers || [];
        this.writeOffs = wo.write_offs || [];
        this.writeOffReasons = wo.reasons || [];
        this.rebuilds = rb.rebuilds || [];
      } catch (e) {
        this.notify('Transfer/yazım geçmişi yüklenemedi.', 'error');
      }
    },

    // --- Transfer ---
    openTransferForm(coin) {
      this.transferForm = {
        pos_key: coin.pos_key,
        coin: coin.display_name || coin.symbol,
        from_exchange: coin.exchange || 'BINANCE',
        available: coin.total_qty || 0,
        to_exchange: '',
        qty: '',
        fee_qty: '',
        date: new Date().toISOString().slice(0, 10),
        note: ''
      };
      this.showTransferForm = true;
      if (!this.writeOffReasons.length) this.fetchLedgerHistory();
    },

    // Transfer hedefi olarak seçilebilecek konumlar — kaynağın kendisi hariç.
    // Yaygın cüzdan adları da öneri olarak eklenir; kullanıcı hiç transfer
    // yapmamışsa liste boş kalmasın.
    get transferTargetOptions() {
      const kaynak = this.normalizeLocation(this.transferForm.from_exchange);
      const set = new Set(this.knownLocations);
      ['METAMASK', 'TRUST WALLET', 'LEDGER', 'WHITEBIT'].forEach(x => set.add(x));
      return Array.from(set).filter(x => x !== kaynak);
    },

    get transferReceived() {
      const q = Number(this.transferForm.qty) || 0;
      const f = Number(this.transferForm.fee_qty) || 0;
      return Math.max(q - f, 0);
    },

    get transferValid() {
      const f = this.transferForm;
      const q = Number(f.qty) || 0;
      const fee = Number(f.fee_qty) || 0;
      return !!f.to_exchange.trim()
        && f.to_exchange.trim().toUpperCase() !== (f.from_exchange || '').toUpperCase()
        && q > 0 && q <= f.available + 1e-9 && fee >= 0 && fee < q;
    },

    async submitTransfer() {
      if (!this.transferValid || this.transferBusy) return;
      this.transferBusy = true;
      try {
        const resp = await fetch('/api/transfers', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            pos_key: this.transferForm.pos_key,
            to_exchange: this.transferForm.to_exchange.trim().toUpperCase(),
            qty: Number(this.transferForm.qty),
            fee_qty: Number(this.transferForm.fee_qty) || 0,
            date: this.transferForm.date,
            note: this.transferForm.note
          })
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Transfer kaydedilemedi.');

        this._applyLedgerSnapshot(body);
        this.showTransferForm = false;
        const t = body.transfer;
        this.notify(
          `${this.formatNum(t.qty, 6)} ${t.coin} taşındı: ${t.from_exchange} → ${t.to_exchange}. ` +
          `Maliyet tabanı korundu, nakit değişmedi.`, 'success', 5000
        );
        await this.fetchPortfolio();
      } catch (e) {
        this.notify(e.message || 'Transfer kaydedilemedi.', 'error', 5000);
      } finally {
        this.transferBusy = false;
      }
    },

    async undoTransferRecord(kayit) {
      const onay = await this.askConfirm({
        title: 'Transferi geri al',
        message: `${this.formatNum(kayit.qty, 6)} ${kayit.coin} transferi geri alınacak.`,
        detail: `Hedefteki (${kayit.to_exchange}) lotlar silinecek ve varlık ` +
                `${kayit.from_exchange} üzerinde eski hâline dönecek. ` +
                `Transfer sonrası bu varlığı sattıysanız işlem reddedilir.`,
        confirmText: 'Geri Al',
        tone: 'danger'
      });
      if (!onay) return;
      try {
        const resp = await fetch(`/api/transfers/${kayit.id}`, { method: 'DELETE' });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Geri alınamadı.');
        this._applyLedgerSnapshot(body);
        this.notify('Transfer geri alındı.', 'success');
        await this.fetchPortfolio();
      } catch (e) {
        this.notify(e.message || 'Geri alınamadı.', 'error', 6000);
      }
    },

    // --- Değer kaybı yazımı ---
    openWriteOffForm(coin) {
      this.writeOffForm = {
        pos_key: coin.pos_key,
        coin: coin.display_name || coin.symbol,
        exchange: coin.exchange || 'BINANCE',
        qty: coin.total_qty || 0,
        invested: coin.total_invested || 0,
        reason: 'delist',
        note: ''
      };
      this.showWriteOffForm = true;
      if (!this.writeOffReasons.length) this.fetchLedgerHistory();
    },

    async submitWriteOff() {
      if (this.writeOffBusy) return;
      const f = this.writeOffForm;
      const onay = await this.askConfirm({
        title: `${f.coin} sıfırdan kapatılacak`,
        message: `${this.formatNum(f.qty, 6)} ${f.coin} pozisyonu değersiz kabul edilip kapatılacak.`,
        detail: `$${this.formatNum(f.invested, 2)} maliyetin tamamı GERÇEKLEŞMİŞ ZARAR olarak ` +
                `yazılacak. Kasanıza nakit EKLENMEZ — bu bir satış değildir. ` +
                `Toplam varlığınız bu pozisyonun değeri kadar düşecek. İşlem geri alınabilir.`,
        confirmText: 'Zarar Yaz',
        tone: 'danger'
      });
      if (!onay) return;

      this.writeOffBusy = true;
      try {
        const resp = await fetch(
          `/api/positions/${encodeURIComponent(f.pos_key)}/write-off`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: f.reason, note: f.note })
          });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Yazım başarısız.');

        this._applyLedgerSnapshot(body);
        this.showWriteOffForm = false;
        const r = body.result;
        this.notify(
          `${r.coin} kapatıldı — $${this.formatNum(r.realized_loss_usd, 2)} zarar yazıldı ` +
          `(${r.lot_count} lot). Geri almak için Defter Geçmişi'ne bakın.`, 'warning', 6000
        );
        await this.fetchPortfolio();
      } catch (e) {
        this.notify(e.message || 'Yazım başarısız.', 'error', 5000);
      } finally {
        this.writeOffBusy = false;
      }
    },

    async undoWriteOffRecord(kayit) {
      const onay = await this.askConfirm({
        title: 'Yazımı geri al',
        message: `${kayit.coin} pozisyonu yeniden açılacak.`,
        detail: 'Yazılan zarar iptal edilecek ve lotlar aktif duruma dönecek.',
        confirmText: 'Geri Al',
        tone: 'warning'
      });
      if (!onay) return;
      try {
        const resp = await fetch(`/api/write-offs/${kayit.id}/undo`, { method: 'POST' });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail || 'Geri alınamadı.');
        this._applyLedgerSnapshot(body);
        this.notify(`${kayit.coin} yeniden açıldı.`, 'success');
        await this.fetchPortfolio();
      } catch (e) {
        this.notify(e.message || 'Geri alınamadı.', 'error', 6000);
      }
    },

    writeOffReasonLabel(key) {
      const bulunan = this.writeOffReasons.find(r => r.key === key);
      return bulunan ? bulunan.label : (key || '—');
    },

    // -------------------------------------------------------------
    // FAZ E: HEDGE / KALDIRAÇLI POZİSYON
    // -------------------------------------------------------------
    // Teminat modunda miktar türetilir: nominal = teminat × kaldıraç
    get hedgeQty() {
      const f = this.hedgeForm;
      const price = Number(f.entry_price) || 0;
      if (f.sizeMode === 'margin') {
        const lev = Number(f.leverage) || 1;
        const margin = Number(f.margin_usd) || 0;
        return price > 0 ? (margin * lev) / price : 0;
      }
      return Number(f.qty) || 0;
    },

    get hedgeNotional() {
      return this.hedgeQty * (Number(this.hedgeForm.entry_price) || 0);
    },

    // Kaldıraç K/Z'yi değil, yalnızca bağlanan teminatı değiştirir.
    get hedgeMargin() {
      const lev = Number(this.hedgeForm.leverage) || 1;
      return lev > 0 ? this.hedgeNotional / lev : this.hedgeNotional;
    },

    // Bu pozisyon spot varlığın yüzde kaçını koruyor?
    get hedgeCoverage() {
      const coin = this.consolidatedCoins.find(c => c.display_name === this.hedgeForm.coin);
      const spot = coin ? Number(coin.total_qty) || 0 : 0;
      if (spot <= 0 || this.hedgeQty <= 0) return 0;
      return (this.hedgeQty / spot) * 100;
    },

    toggleHedgeSizeMode() {
      const f = this.hedgeForm;
      if (f.sizeMode === 'margin') {
        // Teminattan hesaplanan miktarı taşı ki kullanıcı sayıyı kaybetmesin
        if (this.hedgeQty > 0) f.qty = this.hedgeQty;
        f.sizeMode = 'qty';
      } else {
        if (this.hedgeMargin > 0) f.margin_usd = Number(this.hedgeMargin.toFixed(2));
        f.sizeMode = 'margin';
      }
    },

    async fetchHedges() {
      try {
        const resp = await fetch('/api/hedges');
        if (!resp.ok) return;
        const data = await resp.json();
        this.hedges = data.hedges || [];
        this.hedgeKpis = data.hedge_kpis || {};
        this.exposures = data.exposures || [];
      } catch (e) {
        console.error('Hedge verisi okunamadı:', e);
      }
    },

    prefillHedgeForm() {
      if (!this.showHedgeForm) return;
      if (!this.hedgeForm.coin && this.consolidatedCoins.length > 0) {
        this.hedgeForm.coin = this.consolidatedCoins[0].display_name;
      }
      this.syncHedgeEntryPrice();
    },

    // Giriş fiyatını canlı fiyatla ön-doldur; kullanıcı borsadaki gerçek
    // giriş fiyatını yazarak değiştirebilir.
    syncHedgeEntryPrice() {
      const coin = this.consolidatedCoins.find(c => c.display_name === this.hedgeForm.coin);
      if (coin && coin.live_price) this.hedgeForm.entry_price = coin.live_price;
    },

    async submitHedge() {
      const f = this.hedgeForm;
      if (!f.coin || !(Number(f.entry_price) > 0) || !(this.hedgeQty > 0)) {
        this.notify('Coin, giriş fiyatı ve teminat/miktar gerekli.', 'warning');
        return;
      }
      // Sunucu da teminattan miktar türetebiliyor; hangi biçimde girildiyse
      // o gönderilir, hesap tek yerde (backend) doğrulanır.
      const gövde = {
        coin: f.coin, direction: f.direction, exchange: f.exchange,
        entry_price: Number(f.entry_price), leverage: Number(f.leverage) || 1
      };
      if (f.sizeMode === 'margin') gövde.margin_usd = Number(f.margin_usd);
      else gövde.qty = Number(f.qty);

      this.hedgeBusy = true;
      try {
        const resp = await fetch('/api/hedges', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(gövde)
        });
        const data = await resp.json();
        if (!resp.ok) {
          this.notify(data.detail || 'Hedge kaydedilemedi.', 'error');
          return;
        }
        this.hedges = data.hedges || [];
        this.hedgeKpis = data.hedge_kpis || {};
        this.exposures = data.exposures || [];
        this.showHedgeForm = false;
        this.hedgeForm.qty = '';
        this.hedgeForm.margin_usd = '';
        this.notify(`${f.direction} ${f.coin} pozisyonu kaydedildi.`, 'success');
        this.fetchPortfolio();
      } catch (e) {
        this.notify('Hedge kaydedilemedi: ' + e.message, 'error');
      } finally {
        this.hedgeBusy = false;
      }
    },

    async promptCloseHedge(h) {
      const fiyat = await this.askConfirm({
        title: `${h.direction} ${h.coin} pozisyonunu kapat`,
        message: 'Borsadaki gerçek kapanış fiyatını gir.',
        detail: 'Gerçekleşmiş kâr/zarar hesaplanıp vadeli bakiyene eklenecek.',
        confirmText: 'Pozisyonu Kapat',
        tone: 'primary',
        withInput: true,
        inputLabel: 'Kapanış fiyatı',
        inputValue: h.live_price || h.entry_price,
        inputSuffix: 'USD'
      });
      if (fiyat === null) return;
      if (!(fiyat > 0)) {
        this.notify('Geçerli bir kapanış fiyatı gerekli.', 'warning');
        return;
      }
      this.closeHedge(h.id, fiyat);
    },

    async closeHedge(id, closePrice) {
      try {
        const resp = await fetch(`/api/hedges/${id}/close`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ close_price: closePrice })
        });
        const data = await resp.json();
        if (!resp.ok) {
          this.notify(data.detail || 'Hedge kapatılamadı.', 'error');
          return;
        }
        this.hedges = data.hedges || [];
        this.hedgeKpis = data.hedge_kpis || {};
        this.exposures = data.exposures || [];
        const pnl = data.realized_pnl_usd || 0;
        this.notify(
          `Pozisyon kapatıldı. Gerçekleşmiş K/Z: ${pnl >= 0 ? '+' : '-'}$${this.formatNum(Math.abs(pnl), 2)} — vadeli bakiyene işlendi.`,
          pnl >= 0 ? 'success' : 'warning'
        );
        this.fetchPortfolio();
      } catch (e) {
        this.notify('Hedge kapatılamadı: ' + e.message, 'error');
      }
    },

    async removeHedge(h) {
      // Açık pozisyonu silmek hiçbir bakiyeye dokunmaz — kayıt hiç
      // girilmemiş gibi olur. Kapanmış pozisyonu silmek ise, kapanışta
      // vadeli bakiyeye işlenen tutarı GERİ ALMAZ; bunu ayrıca söylüyoruz.
      const acik = h.status === 'Açık';
      const onay = await this.askConfirm({
        title: `#${h.id} ${h.direction} ${h.coin} silinsin mi?`,
        message: acik
          ? 'Bu pozisyon henüz kapatılmadı.'
          : 'Bu pozisyon kapatılmıştı.',
        detail: acik
          ? 'Silmek hiçbir bakiyeni etkilemez — kayıt hiç girilmemiş gibi olur.'
          : 'Gerçekleşmiş kâr/zarar vadeli bakiyene işlenmişti. Kaydı silmek o tutarı GERİ ALMAZ; gerekirse Nakit Cüzdanlarını Yönet ekranından elle düzelt.',
        confirmText: 'Kaydı Sil',
        tone: 'danger'
      });
      if (!onay) return;
      try {
        const resp = await fetch(`/api/hedges/${h.id}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok) {
          // 404 = kayıt sunucuda yok, ekrandaki liste bayat. Sessizce
          // tazeleyip kullanıcıya ne olduğunu söyle.
          if (resp.status === 404) {
            await this.fetchHedges();
            this.notify('Bu kayıt zaten silinmiş. Liste tazelendi.', 'warning');
            return;
          }
          this.notify(data.detail || 'Kayıt silinemedi.', 'error');
          return;
        }
        this.hedges = data.hedges || [];
        this.hedgeKpis = data.hedge_kpis || {};
        this.exposures = data.exposures || [];
        this.notify('Hedge kaydı silindi.', 'success');
        this.fetchPortfolio();
      } catch (e) {
        this.notify('Kayıt silinemedi: ' + e.message, 'error');
      }
    },

    async runScenario(movePct) {
      try {
        const resp = await fetch(`/api/hedges/scenario?move_pct=${movePct}`);
        if (!resp.ok) return;
        this.scenario = await resp.json();
      } catch (e) {
        console.error('Senaryo hesaplanamadı:', e);
      }
    },

    // -------------------------------------------------------------
    // FAZ B++: FİYAT KAYNAĞI YÖNETİMİ
    // -------------------------------------------------------------
    async fetchPriceSources() {
      try {
        const resp = await fetch('/api/price-sources');
        if (!resp.ok) return;
        const data = await resp.json();
        this.sourceRegistry = data.registry || [];
        this.symbolSources = data.symbol_sources || {};
      } catch (e) {
        console.error('Fiyat kaynakları okunamadı:', e);
      }
    },

    async savePriceSourceRegistry() {
      const registry = {};
      this.sourceRegistry.forEach((row, i) => {
        registry[row.id] = { enabled: !!row.enabled, order: i + 1 };
      });
      try {
        const resp = await fetch('/api/price-sources', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ registry })
        });
        const data = await resp.json();
        if (!resp.ok) {
          this.notify(data.detail || 'Kaynaklar kaydedilemedi.', 'error');
          return;
        }
        this.sourceRegistry = data.registry || this.sourceRegistry;
        this.notify('Fiyat kaynakları güncellendi.', 'success');
        this.fetchPortfolio();
        // FAZ F1d — Yeni açılan bir kaynak henüz denenmemiştir; sağlık rozeti
        // "denenmedi" olarak kalır. Motor 4 sn'de bir dönüyor, bir tur sonra
        // rozetleri tazeleyip kaynağın gerçekten çalışıp çalışmadığını gösteriyoruz.
        setTimeout(() => this.refreshSourceHealth(), 6000);
      } catch (e) {
        this.notify('Kaynaklar kaydedilemedi: ' + e.message, 'error');
      }
    },

    // Yalnızca sağlık alanlarını tazeler. `enabled` ve sıralamaya DOKUNMAZ:
    // kullanıcı o sırada listeyi düzenliyor olabilir ve yaptığı değişiklik
    // sunucudaki eski değerle ezilmemeli.
    async refreshSourceHealth() {
      try {
        const resp = await fetch('/api/price-sources');
        if (!resp.ok) return;
        const data = await resp.json();
        const saglik = {};
        (data.registry || []).forEach(r => { saglik[r.id] = r; });
        this.sourceRegistry = this.sourceRegistry.map(row => {
          const s = saglik[row.id];
          if (!s) return row;
          return { ...row, healthy: s.healthy, fail_count: s.fail_count,
                   last_error: s.last_error, last_ok_ts: s.last_ok_ts };
        });
      } catch (e) {
        /* sağlık rozeti tazelenemedi — sessiz geçilir, kritik değil */
      }
    },

    moveSource(index, delta) {
      const target = index + delta;
      if (target < 0 || target >= this.sourceRegistry.length) return;
      const list = [...this.sourceRegistry];
      [list[index], list[target]] = [list[target], list[index]];
      this.sourceRegistry = list;
    },

    // Bir pozisyondan "Fiyat kaynağı tanımla" ile açılır.
    openSourceForm(coin) {
      const base = this.baseSymbol(coin);
      const existing = this.symbolSources[base];
      this.sourceForm = {
        symbol: base,
        type: existing?.type || 'cex',
        source: existing?.source || 'whitebit',
        market: existing?.market || `${base}_USDT`,
        query: existing?.query || base,
        price: existing?.price || ''
      };
      this.sourcePreview = null;
      this.sourceFormOpenedFromCoin = true;
      this.settingsTab = 'sources';
      this.showSettingsModal = true;
      this.fetchPriceSources();
    },

    buildSourceSpec() {
      const f = this.sourceForm;
      if (f.type === 'cex') return { type: 'cex', source: f.source, market: f.market };
      if (f.type === 'dex') return { type: 'dex', query: f.query };
      return { type: 'manual', price: Number(f.price) };
    },

    // Kaydetmeden önce dener. Yanlış bir market adı yüzünden pozisyonun
    // sessizce fiyatsız kalmasını engeller.
    async previewSymbolSource() {
      this.sourceBusy = true;
      this.sourcePreview = null;
      try {
        const resp = await fetch('/api/symbol-sources/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol: this.sourceForm.symbol, source: this.buildSourceSpec() })
        });
        const data = await resp.json();
        this.sourcePreview = resp.ok ? data : { success: false, message: data.detail || 'Geçersiz tanım.' };
      } catch (e) {
        this.sourcePreview = { success: false, message: e.message };
      } finally {
        this.sourceBusy = false;
      }
    },

    async saveSymbolSource() {
      if (!this.sourceForm.symbol) {
        this.notify('Sembol gerekli.', 'warning');
        return;
      }
      this.sourceBusy = true;
      try {
        const resp = await fetch('/api/symbol-sources', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol: this.sourceForm.symbol, source: this.buildSourceSpec() })
        });
        const data = await resp.json();
        if (!resp.ok) {
          this.notify(data.detail || 'Kaynak kaydedilemedi.', 'error');
          return;
        }
        this.symbolSources = data.symbol_sources || {};
        this.notify(`${this.sourceForm.symbol} için fiyat kaynağı tanımlandı.`, 'success');
        this.fetchPortfolio();
      } catch (e) {
        this.notify('Kaynak kaydedilemedi: ' + e.message, 'error');
      } finally {
        this.sourceBusy = false;
      }
    },

    async deleteSymbolSource(symbol) {
      if (!await this.askConfirm({
        title: `${symbol} kaynak tanımı kaldırılsın mı?`,
        message: 'Bu sembol bundan sonra normal kademe sırasından fiyatlanacak.',
        detail: 'Kademe sırası bu coini bulamazsa "Kaynak Yok" olarak işaretlenir.',
        confirmText: 'Tanımı Kaldır'
      })) return;
      try {
        const resp = await fetch(`/api/symbol-sources/${encodeURIComponent(symbol)}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok) {
          this.notify(data.detail || 'Kaynak kaldırılamadı.', 'error');
          return;
        }
        this.symbolSources = data.symbol_sources || {};
        this.notify(`${symbol} tanımı kaldırıldı.`, 'success');
        this.fetchPortfolio();
      } catch (e) {
        this.notify('Kaynak kaldırılamadı: ' + e.message, 'error');
      }
    },

    describeSymbolSource(spec) {
      if (!spec) return '';
      if (spec.type === 'cex') return `${(spec.source || '').toUpperCase()} · ${spec.market}`;
      if (spec.type === 'dex') return `Zincir üstü · ${spec.query}`;
      if (spec.type === 'manual') return `Manuel · $${spec.price}`;
      return spec.type || '';
    },

    async runHealthPing() {
      this.pingLoading = true;
      try {
        const resp = await fetch('/api/health/ping');
        if (resp.ok) {
          this.pingResults = await resp.json();
        }
      } catch (e) {
        console.error('Ping test error:', e);
      } finally {
        this.pingLoading = false;
        this.$nextTick(() => { if (window.lucide) lucide.createIcons(); });
      }
    },

    async testTelegramConnection() {
      if (!this.settings.api_keys.telegram_bot_token || !this.settings.api_keys.telegram_chat_id) {
        this.notify('Lütfen önce Telegram Bot Token ve Chat ID giriniz.', 'warning');
        return;
      }
      this.telegramTestLoading = true;
      this.telegramTestResult = null;
      try {
        const resp = await fetch('/api/health/test-telegram', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            bot_token: this.settings.api_keys.telegram_bot_token,
            chat_id: this.settings.api_keys.telegram_chat_id
          })
        });
        const res = await resp.json();
        this.telegramTestResult = res;
      } catch (e) {
        this.telegramTestResult = { success: false, message: 'İstek hatası: ' + e };
      } finally {
        this.telegramTestLoading = false;
      }
    },

    restoreDefaultUrls() {
      this.settings.api_urls = {
        binance_ticker: 'https://api.binance.com/api/v3/ticker/24hr',
        binance_ping: 'https://api.binance.com/api/v3/ping',
        mexc_ticker: 'https://api.mexc.com/api/v3/ticker/24hr',
        mexc_ping: 'https://api.mexc.com/api/v3/ping',
        whitebit_ticker: 'https://whitebit.com/api/v4/public/ticker',
        gateio_ticker: 'https://api.gateio.ws/api/v4/spot/tickers',
        dex_screener: 'https://api.dexscreener.com/latest/dex/search'
      };
    },

    startBackgroundLoop() {
      if (this.bgIntervalTimer) clearInterval(this.bgIntervalTimer);
      const intervalSec = parseFloat(this.settings.preferences.refresh_interval_sec) || 3.5;
      this.bgIntervalTimer = setInterval(() => {
        this.fetchPortfolio(false);
      }, intervalSec * 1000);
    },

    restartBackgroundLoop() {
      this.startBackgroundLoop();
    },

    openSettingsModal(tab = 'health') {
      this.settingsTab = tab;
      this.showSettingsModal = true;
      this.fetchSettings();
      if (tab === 'health') {
        this.runHealthPing();
      }
      this.$nextTick(() => { if (window.lucide) lucide.createIcons(); });
    },

    // -------------------------------------------------------------
    // FAZ 6: YAPAY ZEKA DANIŞMAN METODLARI (SIFIR İSRAF & KOTA KORUMA)
    // -------------------------------------------------------------
    setAiMode(mode) {
      this.aiMode = mode;
      this.$nextTick(() => { if (window.lucide) lucide.createIcons(); });
    },

    async runAiAnalysis(mode = null, forceRefresh = false) {
      const targetMode = mode || this.aiMode || 'full_audit';
      this.aiMode = targetMode;

      this.aiLoading = true;
      try {
        const resp = await fetch('/api/ai/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mode: targetMode,
            custom_question: this.aiCustomQuestion
          })
        });
        if (resp.ok) {
          const data = await resp.json();
          this.aiReports[targetMode] = data.report_markdown;
          this.aiReportSources[targetMode] = data.model_name || (data.source === 'GEMINI_AI' ? 'Google Gemini AI' : 'Yerel Finansal Motor');
          this.aiReportTimes[targetMode] = data.generated_at;
        } else {
          this.aiReports[targetMode] = '# ❌ Hata\nAnaliz oluşturulurken sunucu hatası meydana geldi.';
        }
      } catch (err) {
        this.aiReports[targetMode] = '# ❌ Bağlantı Hatası\n' + err.message;
      } finally {
        this.aiLoading = false;
        this.$nextTick(() => { if (window.lucide) lucide.createIcons(); });
      }
    },

    copyAiReport() {
      const currentRep = this.aiReports[this.aiMode];
      if (!currentRep) return;
      navigator.clipboard.writeText(currentRep);
      this.copiedReportSuccess = true;
      setTimeout(() => { this.copiedReportSuccess = false; }, 2500);
    },

    formatAiMarkdownForWord(md) {
      if (!md) return '';
      const lines = md.split('\n');
      let out = [];
      let inTable = false;
      let tableHeader = null;
      let tableRows = [];
      let inList = false;
      let listType = 'ul';

      const flushTable = () => {
        if (inTable && tableRows.length > 0) {
          let html = '<table style="width: 100%; border-collapse: collapse; margin: 14px 0; font-family: \'Segoe UI\', Calibri, Arial, sans-serif; font-size: 10pt; border: 1px solid #94a3b8;">';
          if (tableHeader) {
            html += '<thead><tr style="background-color: #1e293b; color: #ffffff;">';
            tableHeader.forEach(cell => {
              html += `<th style="border: 1px solid #475569; padding: 8px 10px; font-weight: bold; text-align: left; background-color: #1e293b; color: #ffffff;">${cell}</th>`;
            });
            html += '</tr></thead>';
          }
          html += '<tbody>';
          tableRows.forEach((row, idx) => {
            const bg = idx % 2 === 1 ? '#f8fafc' : '#ffffff';
            html += `<tr style="background-color: ${bg};">`;
            row.forEach(cell => {
              html += `<td style="border: 1px solid #cbd5e1; padding: 7px 10px; color: #1e293b;">${cell}</td>`;
            });
            html += '</tr>';
          });
          html += '</tbody></table>';
          out.push(html);
        }
        inTable = false;
        tableHeader = null;
        tableRows = [];
      };

      const flushList = () => {
        if (inList) {
          out.push(`</${listType}>`);
          inList = false;
        }
      };

      const formatInlineWord = (text) => {
        if (!text) return '';
        return text
          .replace(/\*\*(.*?)\*\*/g, '<b style="color: #0f172a; font-weight: bold;">$1</b>')
          .replace(/\*(.*?)\*/g, '<i style="color: #475569;">$1</i>')
          .replace(/`([^`]+)`/g, '<code style="background-color: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; padding: 2px 5px; border-radius: 3px; font-family: Consolas, monospace; font-size: 9.5pt; font-weight: bold;">$1</code>');
      };

      for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();

        if (line.startsWith('|') && line.endsWith('|')) {
          flushList();
          if (line.includes('---')) continue;
          const cells = line.split('|').map(c => formatInlineWord(c.trim())).slice(1, -1);
          if (!inTable) {
            inTable = true;
            tableHeader = cells;
          } else {
            tableRows.push(cells);
          }
          continue;
        } else if (inTable) {
          flushTable();
        }

        if (!line) {
          flushList();
          continue;
        }

        if (line.startsWith('# ')) {
          flushList();
          out.push(`<h1 style="color: #0f172a; font-family: 'Segoe UI', Calibri, Arial, sans-serif; font-size: 16pt; font-weight: bold; border-bottom: 2px solid #0284c7; padding-bottom: 6px; margin-top: 18px; margin-bottom: 8px;">${formatInlineWord(line.substring(2))}</h1>`);
          continue;
        }
        if (line.startsWith('## ')) {
          flushList();
          out.push(`<h2 style="color: #0369a1; font-family: 'Segoe UI', Calibri, Arial, sans-serif; font-size: 13pt; font-weight: bold; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; margin-top: 16px; margin-bottom: 6px;">${formatInlineWord(line.substring(3))}</h2>`);
          continue;
        }
        if (line.startsWith('### ')) {
          flushList();
          out.push(`<h3 style="color: #0f172a; font-family: 'Segoe UI', Calibri, Arial, sans-serif; font-size: 11.5pt; font-weight: bold; margin-top: 12px; margin-bottom: 4px;">${formatInlineWord(line.substring(4))}</h3>`);
          continue;
        }

        if (line.startsWith('> ')) {
          flushList();
          out.push(`<div style="background-color: #f0fdf4; border-left: 4px solid #16a34a; padding: 10px 14px; margin: 10px 0; color: #166534; font-size: 10pt; font-family: 'Segoe UI', Arial, sans-serif;">${formatInlineWord(line.substring(2))}</div>`);
          continue;
        }

        if (line.startsWith('- ') || line.startsWith('* ')) {
          if (!inList || listType !== 'ul') {
            flushList();
            out.push('<ul style="margin: 6px 0 6px 20px; padding: 0; color: #334155; font-family: \'Segoe UI\', Arial, sans-serif; font-size: 10pt; line-height: 1.6;">');
            inList = true;
            listType = 'ul';
          }
          out.push(`<li style="margin-bottom: 4px;">${formatInlineWord(line.substring(2))}</li>`);
          continue;
        }

        if (/^\d+\.\s/.test(line)) {
          if (!inList || listType !== 'ol') {
            flushList();
            out.push('<ol style="margin: 6px 0 6px 20px; padding: 0; color: #334155; font-family: \'Segoe UI\', Arial, sans-serif; font-size: 10pt; line-height: 1.6;">');
            inList = true;
            listType = 'ol';
          }
          const content = line.replace(/^\d+\.\s/, '');
          out.push(`<li style="margin-bottom: 4px;">${formatInlineWord(content)}</li>`);
          continue;
        }

        flushList();
        out.push(`<p style="color: #334155; font-family: 'Segoe UI', Calibri, Arial, sans-serif; font-size: 10pt; line-height: 1.6; margin: 6px 0;">${formatInlineWord(line)}</p>`);
      }

      flushList();
      flushTable();
      return out.join('\n');
    },

    formatAiMarkdown(md) {
      if (!md) return '';
      
      const lines = md.split('\n');
      let out = [];
      let inTable = false;
      let tableHeader = null;
      let tableRows = [];
      let inList = false;
      let listType = 'ul';

      const flushTable = () => {
        if (tableRows.length > 0 || tableHeader) {
          let html = '<div class="overflow-x-auto my-3 rounded-xl border border-slate-700/80 shadow-md bg-slate-950/60"><table class="w-full text-xs text-left border-collapse">';
          if (tableHeader) {
            html += '<thead class="bg-slate-800 text-cyan-300 font-bold border-b border-slate-700"><tr>';
            tableHeader.forEach(cell => {
              html += `<th class="py-2.5 px-3 uppercase tracking-wider">${cell}</th>`;
            });
            html += '</tr></thead>';
          }
          html += '<tbody class="divide-y divide-slate-800/80">';
          tableRows.forEach(row => {
            html += '<tr class="hover:bg-slate-800/40 transition">';
            row.forEach(cell => {
              html += `<td class="py-2 px-3">${cell}</td>`;
            });
            html += '</tr>';
          });
          html += '</tbody></table></div>';
          out.push(html);
        }
        inTable = false;
        tableHeader = null;
        tableRows = [];
      };

      const flushList = () => {
        if (inList) {
          out.push(`</${listType}>`);
          inList = false;
        }
      };

      const formatInline = (text) => {
        if (!text) return '';
        return text
          .replace(/\*\*(.*?)\*\*/g, '<b class="text-white font-bold">$1</b>')
          .replace(/\*(.*?)\*/g, '<i class="text-slate-300">$1</i>')
          .replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300 font-mono text-[11px] border border-slate-700">$1</code>');
      };

      for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();

        // Check if line is part of a markdown table
        if (line.startsWith('|') && line.endsWith('|')) {
          flushList();
          if (line.includes('---')) {
            // separator line, ignore
            continue;
          }
          const cells = line.split('|').map(c => formatInline(c.trim())).slice(1, -1);
          if (!inTable) {
            inTable = true;
            tableHeader = cells;
          } else {
            tableRows.push(cells);
          }
          continue;
        } else if (inTable) {
          flushTable();
        }

        if (!line) {
          flushList();
          continue;
        }

        // Headers
        if (line.startsWith('# ')) {
          flushList();
          out.push(`<h1 class="text-lg font-bold text-white border-b border-slate-800 pb-2 mb-3 mt-4 flex items-center space-x-2">${formatInline(line.substring(2))}</h1>`);
          continue;
        }
        if (line.startsWith('## ')) {
          flushList();
          out.push(`<h2 class="text-base font-bold text-cyan-300 border-b border-slate-800/80 pb-1.5 mb-2 mt-4">${formatInline(line.substring(3))}</h2>`);
          continue;
        }
        if (line.startsWith('### ')) {
          flushList();
          out.push(`<h3 class="text-xs font-bold text-indigo-300 uppercase tracking-wider mb-2 mt-3">${formatInline(line.substring(4))}</h3>`);
          continue;
        }
        if (line.startsWith('#### ')) {
          flushList();
          out.push(`<h4 class="text-xs font-bold text-white mb-1.5 mt-2">${formatInline(line.substring(5))}</h4>`);
          continue;
        }

        // Horizontal Rule
        if (line === '---' || line === '***') {
          flushList();
          out.push('<hr class="border-slate-800 my-4">');
          continue;
        }

        // Alerts & Blockquotes
        if (line.startsWith('> [!WARNING]')) {
          flushList();
          const nextL = lines[i + 1] ? lines[i + 1].replace(/^>\s*/, '').trim() : '';
          i++;
          out.push(`<div class="p-3.5 my-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start space-x-2.5"><span>⚠️</span><div>${formatInline(nextL)}</div></div>`);
          continue;
        }
        if (line.startsWith('> [!NOTE]') || line.startsWith('> [!INFO]')) {
          flushList();
          const nextL = lines[i + 1] ? lines[i + 1].replace(/^>\s*/, '').trim() : '';
          i++;
          out.push(`<div class="p-3.5 my-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs flex items-start space-x-2.5"><span>ℹ️</span><div>${formatInline(nextL)}</div></div>`);
          continue;
        }
        if (line.startsWith('> ')) {
          flushList();
          out.push(`<blockquote class="border-l-2 border-indigo-500 pl-3 my-2 text-slate-300 italic text-xs">${formatInline(line.substring(2))}</blockquote>`);
          continue;
        }

        // Lists
        if (line.startsWith('* ') || line.startsWith('- ')) {
          if (!inList || listType !== 'ul') {
            flushList();
            out.push('<ul class="space-y-1.5 my-2">');
            inList = true;
            listType = 'ul';
          }
          out.push(`<li class="flex items-start space-x-2 text-slate-200 text-xs"><span class="text-indigo-400 mt-0.5">•</span><span>${formatInline(line.substring(2))}</span></li>`);
          continue;
        }
        const numMatch = line.match(/^(\d+)\.\s*(.*)$/);
        if (numMatch) {
          if (!inList || listType !== 'ol') {
            flushList();
            out.push('<ol class="space-y-1.5 my-2">');
            inList = true;
            listType = 'ol';
          }
          out.push(`<li class="flex items-start space-x-2 text-slate-200 text-xs"><span class="font-bold text-cyan-400 min-w-[16px]">${numMatch[1]}.</span><span>${formatInline(numMatch[2])}</span></li>`);
          continue;
        }

        flushList();
        // Regular Paragraph
        out.push(`<p class="my-2 text-slate-200 text-xs leading-relaxed">${formatInline(line)}</p>`);
      }

      flushTable();
      flushList();
      return out.join('\n');
    },

    // Category Styling Helper
    // -------------------------------------------------------------
    // BÖLÜM 14: BİÇİMLENDİRİCİLER & YARDIMCILAR
    // -------------------------------------------------------------
    getCategoryStyle(cat) {
      const c = (cat || '').toLowerCase();
      if (c.includes('majör') || c.includes('l1')) return 'bg-blue-500/10 text-blue-400 border border-blue-500/20';
      if (c.includes('emtia') || c.includes('altın')) return 'bg-amber-500/10 text-amber-400 border border-amber-500/20';
      if (c.includes('defi') || c.includes('dex')) return 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
      if (c.includes('layer 2') || c.includes('l2')) return 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20';
      if (c.includes('gaming') || c.includes('nft')) return 'bg-purple-500/10 text-purple-400 border border-purple-500/20';
      if (c.includes('meme')) return 'bg-pink-500/10 text-pink-400 border border-pink-500/20';
      if (c.includes('yapay zeka') || c.includes('ai')) return 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20';
      if (c.includes('rwa')) return 'bg-teal-500/10 text-teal-400 border border-teal-500/20';
      return 'bg-slate-700/50 text-slate-300 border border-slate-600/30';
    },

    // Alpine'ın x-text bağlamaları kaçışı kendisi yapar, ancak grafik
    // kabındaki içerik innerHTML ile yazılıyor. Coin adları kullanıcı
    // girdisidir; ham gömmek istenmeyen biçimlendirmeye yol açabilir.
    escapeHtml(str) {
      return String(str == null ? '' : str).replace(/[&<>"']/g, ch => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[ch]));
    },

    // Formatters (Supports sub-penny & nano prices)
    formatPrice(val) {
      if (val === undefined || val === null || isNaN(val)) return '0.00';
      const num = Number(val);
      if (num >= 1000) {
        return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      } else if (num >= 1) {
        return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
      } else if (num >= 0.0001) {
        return num.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 });
      } else {
        // Nano / Micro price for meme and DEX tokens (e.g. 0.000000002366)
        let s = num.toFixed(12).replace(/0+$/, "");
        if (s.endsWith(".")) s += "00";
        return s;
      }
    },

    // -------------------------------------------------------------
    // FAZ 7: GERÇEKLEŞMİŞ KÂR/ZARAR & DIŞA AKTARMA METODLARI
    // -------------------------------------------------------------
    async fetchRealizedMetrics() {
      try {
        const resp = await fetch('/api/realized-pnl');
        if (resp.ok) {
          this.realizedMetrics = await resp.json();
        }
      } catch (err) {
        console.error('Error fetching realized metrics:', err);
      }
    },

    downloadExcelReport() {
      this.exportLoading = true;
      try {
        const link = document.createElement('a');
        link.href = '/api/export/excel';
        link.download = `CoinTakip_Portfoy_Raporu_${new Date().toISOString().slice(0, 10)}.xlsx`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      } catch (err) {
        this.notify('Excel indirilirken hata oluştu: ' + err.message, 'error');
      } finally {
        setTimeout(() => { this.exportLoading = false; }, 1500);
      }
    },

    printPortfolioReport() {
      window.print();
    },

    // ---------------------------------------------------------------
    // VERGİ-HAZIR DIŞA AKTARIM
    //
    // Panel indirmeden ÖNCE dosyanın içinde ne olacağını söyler. Sebep:
    // eksik veri sayısını dosyayı açtıktan sonra fark etmek, mali müşavire
    // yanlış dosyayı göndermiş olmak demektir.
    // ---------------------------------------------------------------
    async fetchTaxSummary() {
      try {
        const res = await fetch('/api/export/tax/summary');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.taxSummary = await res.json();
        const yillar = this.taxSummary.available_years || [];
        if (this.taxYear && !yillar.includes(this.taxYear)) this.taxYear = '';
      } catch (err) {
        console.error('Vergi özeti alınamadı:', err);
        this.taxSummary = null;
      }
    },

    // Seçili dönemde dosyaya girecek olay sayısı. "Tüm yıllar" seçiliyken
    // toplam, bir yıl seçiliyken o yılın sayısı.
    get taxYearEventCount() {
      if (!this.taxSummary) return 0;
      if (!this.taxYear) return this.taxSummary.total_events || 0;
      return (this.taxSummary.year_counts || {})[this.taxYear] || 0;
    },

    downloadTaxExport(format) {
      this.taxLoading = true;
      try {
        const donem = this.taxYear ? `year=${encodeURIComponent(this.taxYear)}&` : '';
        const link = document.createElement('a');
        link.href = `/api/export/tax?${donem}format=${format}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      } catch (err) {
        this.notify('Vergi dosyası indirilemedi: ' + err.message, 'error');
      } finally {
        setTimeout(() => { this.taxLoading = false; }, 1500);
      }
    },

    async copyAiReportRich() {
      const currentRep = this.aiReports[this.aiMode];
      if (!currentRep) return;

      const renderedHtml = this.formatAiMarkdownForWord(currentRep);
      // Clean HTML wrapper with full inline styling for Word / Google Docs
      const fullRichHtml = `
        <div style="font-family: 'Segoe UI', Calibri, Arial, sans-serif; font-size: 11pt; color: #1e293b; line-height: 1.6;">
          ${renderedHtml}
        </div>
      `;

      try {
        if (navigator.clipboard && window.ClipboardItem) {
          const htmlBlob = new Blob([fullRichHtml], { type: 'text/html' });
          const textBlob = new Blob([currentRep], { type: 'text/plain' });
          await navigator.clipboard.write([
            new ClipboardItem({
              'text/html': htmlBlob,
              'text/plain': textBlob
            })
          ]);
        } else {
          await navigator.clipboard.writeText(currentRep);
        }
        this.copiedRichSuccess = true;
        setTimeout(() => { this.copiedRichSuccess = false; }, 2500);
      } catch (err) {
        console.warn('Rich copy fallback to text copy:', err);
        navigator.clipboard.writeText(currentRep);
        this.copiedReportSuccess = true;
        setTimeout(() => { this.copiedReportSuccess = false; }, 2500);
      }
    },

    formatNum(val, decimals = 2) {
      if (val === undefined || val === null || isNaN(val)) return '0.00';
      if (this.privacyMode && decimals >= 2) return '••••';
      const num = Number(val);
      if (num > 0 && num < 0.0001) {
        return num.toFixed(8).replace(/0+$/, "");
      }
      return num.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: Math.max(decimals, 4) });
    },

    // Gizlilik modu + kuruş altı (nano) hassasiyeti tek fonksiyonda birleştirildi
    formatUSD(val) {
      if (this.privacyMode) return '$••••••';
      if (val === undefined || val === null || isNaN(val)) return '$0.00';
      const num = Number(val);
      const absVal = Math.abs(num);
      const sign = num < 0 ? '-$' : '$';
      if (absVal > 0 && absVal < 0.01) {
        return sign + absVal.toFixed(6);
      }
      return sign + absVal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },

    // -------------------------------------------------------------
    // FAZ 8: GÜVENLİK & KİLİT METODLARI
    // -------------------------------------------------------------
    async checkAuthStatus() {
      try {
        const resp = await fetch('/api/auth/status');
        if (resp.ok) {
          const data = await resp.json();
          this.pinEnabled = data.pin_enabled || false;
          this.autoLockMinutes = data.auto_lock_minutes !== undefined ? data.auto_lock_minutes : 15;
          this.privacyMode = data.privacy_mode || false;

          if (this.pinEnabled) {
            const isUnlocked = sessionStorage.getItem('cointakip_unlocked');
            if (!isUnlocked) {
              this.isLocked = true;
            }
          }
        }
      } catch (err) {
        console.error('Error checking auth status:', err);
      }
    },

    enterPinDigit(digit) {
      if (this.pinInput.length < 8) {
        this.pinInput += digit;
        this.pinError = '';
      }
    },

    deletePinDigit() {
      if (this.pinInput.length > 0) {
        this.pinInput = this.pinInput.slice(0, -1);
        this.pinError = '';
      }
    },

    clearPin() {
      this.pinInput = '';
      this.pinError = '';
    },

    async submitPin() {
      if (!this.pinInput) {
        this.pinError = 'Lütfen PIN kodunuzu giriniz.';
        return;
      }
      this.isVerifyingPin = true;
      this.pinError = '';
      try {
        const resp = await fetch('/api/auth/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin: this.pinInput })
        });
        if (resp.ok) {
          const data = await resp.json();
          this.isLocked = false;
          this.pinInput = '';
          this.pinError = '';
          sessionStorage.setItem('cointakip_unlocked', data.session_token || '1');
          this.lastActivityTime = Date.now();
          this.fetchPortfolio(true);
        } else {
          this.pinError = 'Hatalı PIN kodu! Lütfen tekrar deneyin.';
          this.pinInput = '';
        }
      } catch (err) {
        this.pinError = 'Bağlantı hatası: ' + err.message;
      } finally {
        this.isVerifyingPin = false;
        this.$nextTick(() => { if (window.lucide) lucide.createIcons(); });
      }
    },

    lockApp() {
      sessionStorage.removeItem('cointakip_unlocked');
      this.isLocked = true;
      this.pinInput = '';
      this.pinError = '';
      this.showRecoveryMode = false;
      this.recoveryError = '';
      this.$nextTick(() => { if (window.lucide) lucide.createIcons(); });
    },

    async submitRecoveryKey() {
      const key = (this.recoveryForm.key || '').trim().toUpperCase();
      const newPin = (this.recoveryForm.new_pin || '').trim();
      if (!key || key.length < 12) {
        this.recoveryError = 'Kurtarma anahtarı 12 karakter olmalıdır.';
        return;
      }
      if (!newPin || newPin.length < 4) {
        this.recoveryError = 'Yeni PIN en az 4 haneli olmalıdır.';
        return;
      }
      this.recoveryError = '';
      try {
        const resp = await fetch('/api/auth/recover', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ recovery_key: key, new_pin: newPin })
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
          this.isLocked = false;
          this.showRecoveryMode = false;
          this.recoveryForm = { key: '', new_pin: '' };
          sessionStorage.setItem('cointakip_unlocked', '1');
          this.lastActivityTime = Date.now();
          // Show new recovery key
          if (data.recovery_key) {
            this.newRecoveryKey = data.recovery_key;
            this.showNewRecoveryKey = true;
          }
          this.notify('PIN başarıyla sıfırlandı!', 'success');
          this.fetchPortfolio(true);
        } else {
          this.recoveryError = data.detail || 'Geçersiz kurtarma anahtarı.';
        }
      } catch (err) {
        this.recoveryError = 'Bağlantı hatası: ' + err.message;
      }
      this.$nextTick(() => { if (window.lucide) lucide.createIcons(); });
    },

    togglePrivacyMode() {
      this.privacyMode = !this.privacyMode;
      fetch('/api/auth/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ privacy_mode: this.privacyMode })
      }).catch(e => console.error(e));
    },

    initInactivityListener() {
      const resetActivity = () => {
        this.lastActivityTime = Date.now();
      };
      window.addEventListener('mousemove', resetActivity, { passive: true });
      window.addEventListener('keydown', (e) => {
        resetActivity();
        if (this.isLocked) {
          if (e.key >= '0' && e.key <= '9') {
            this.enterPinDigit(e.key);
          } else if (e.key === 'Backspace') {
            this.deletePinDigit();
          } else if (e.key === 'Enter') {
            this.submitPin();
          } else if (e.key === 'Escape') {
            this.clearPin();
          }
        }
      });
      window.addEventListener('touchstart', resetActivity, { passive: true });
      window.addEventListener('scroll', resetActivity, { passive: true });

      // Auto-lock interval check
      setInterval(() => {
        if (!this.isLocked && this.pinEnabled && this.autoLockMinutes > 0) {
          const idleMs = Date.now() - this.lastActivityTime;
          if (idleMs >= this.autoLockMinutes * 60 * 1000) {
            this.lockApp();
          }
        }
      }, 10000); // Check every 10 seconds
    },

    openPinSetup(mode = 'enable') {
      this.pinSetupMode = mode;
      this.pinSetupError = '';
      this.pinSetupSuccess = '';
      this.pinSetupForm = {
        current_pin: '',
        new_pin: '',
        confirm_pin: '',
        auto_lock_minutes: this.autoLockMinutes || 15
      };
      this.showPinSetupModal = true;
      this.$nextTick(() => { if (window.lucide) lucide.createIcons(); });
    },

    async savePinSetup() {
      this.pinSetupError = '';
      this.pinSetupSuccess = '';

      if (this.pinSetupMode === 'disable') {
        if (!this.pinSetupForm.current_pin) {
          this.pinSetupError = 'Lütfen mevcut PIN kodunuzu girin.';
          return;
        }
        try {
          const resp = await fetch('/api/auth/disable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_pin: this.pinSetupForm.current_pin })
          });
          const res = await resp.json();
          if (resp.ok) {
            this.pinEnabled = false;
            this.showPinSetupModal = false;
            sessionStorage.removeItem('cointakip_unlocked');
            this.notify('PIN koruması başarıyla kaldırıldı.', 'info');
          } else {
            this.pinSetupError = res.detail || 'Mevcut PIN hatalı.';
          }
        } catch (e) {
          this.pinSetupError = 'Bağlantı hatası: ' + e.message;
        }
        return;
      }

      // Mode is 'enable' or 'change'
      const newPin = (this.pinSetupForm.new_pin || '').trim();
      const confPin = (this.pinSetupForm.confirm_pin || '').trim();

      if (!newPin || newPin.length < 4) {
        this.pinSetupError = 'Yeni PIN en az 4 haneli olmalıdır.';
        return;
      }
      if (newPin !== confPin) {
        this.pinSetupError = 'Girdiğiniz PIN kodları birbiriyle eşleşmiyor.';
        return;
      }
      if (this.pinSetupMode === 'change' && !this.pinSetupForm.current_pin) {
        this.pinSetupError = 'Lütfen mevcut PIN kodunuzu girin.';
        return;
      }

      try {
        const resp = await fetch('/api/auth/setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            current_pin: this.pinSetupForm.current_pin,
            new_pin: newPin,
            auto_lock_minutes: parseInt(this.pinSetupForm.auto_lock_minutes) || 15
          })
        });
        const res = await resp.json();
        if (resp.ok) {
          this.pinEnabled = true;
          this.autoLockMinutes = parseInt(this.pinSetupForm.auto_lock_minutes) || 15;
          sessionStorage.setItem('cointakip_unlocked', '1');
          this.showPinSetupModal = false;
          // Show recovery key if returned (first-time setup)
          if (res.recovery_key) {
            this.newRecoveryKey = res.recovery_key;
            this.showNewRecoveryKey = true;
          }
          this.notify(this.pinSetupMode === 'change' ? 'PIN kodu başarıyla güncellendi!' : 'PIN koruması başarıyla aktif edildi!', 'success');
        } else {
          this.pinSetupError = res.detail || 'PIN kaydedilemedi.';
        }
      } catch (e) {
        this.pinSetupError = 'Bağlantı hatası: ' + e.message;
      }
    },

    async updateAutoLockSetting(mins) {
      this.autoLockMinutes = parseInt(mins);
      try {
        await fetch('/api/auth/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ auto_lock_minutes: this.autoLockMinutes })
        });
        this.notify('Otomatik kilit süresi güncellendi.', 'info');
      } catch (e) {
        console.error(e);
      }
    },

    // -------------------------------------------------------------
    // BÖLÜM 15: TOAST BİLDİRİM SİSTEMİ
    // -------------------------------------------------------------
    notify(message, type = 'success', duration = 3500) {
      const id = Date.now() + Math.random();
      let icon = 'check-circle-2';
      if (type === 'error') icon = 'alert-circle';
      if (type === 'warning') icon = 'alert-triangle';
      if (type === 'info') icon = 'info';

      this.toasts.push({ id, message, type, icon });
      this.$nextTick(() => {
        if (window.lucide) lucide.createIcons();
      });

      setTimeout(() => {
        this.removeToast(id);
      }, duration);
    },

    removeToast(id) {
      this.toasts = this.toasts.filter(t => t.id !== id);
    }

  };
}
