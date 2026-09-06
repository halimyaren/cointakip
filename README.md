# CoinTakip

**A local-first, privacy-focused crypto portfolio tracker.**

🇹🇷 [Türkçe README](README.tr.md) · 📖 [Kullanım Kılavuzu (Türkçe)](KILAVUZ.md)

Your data never leaves your machine. No cloud sync, no account, no requirement to
hand over exchange API keys. The app runs on `127.0.0.1` on your own computer and
stores your portfolio in plain JSON files.

> **Note on language:** The user interface is in **Turkish**. This README is in
> English so the project is readable to a wider audience, but the app itself has
> not been internationalised yet. If there is interest, i18n is on the roadmap.

---

## Why another portfolio tracker?

There are plenty of alternatives and most are more comprehensive. CoinTakip differs
in two ways:

**1. When it cannot find a price, it says so.**
Most trackers fail silently on delisted, unlisted, or thinly-traded coins — showing
nothing, or quietly returning the price of a *different* token that happens to share
the same ticker. CoinTakip shows `—` instead of a price and lets you pin the source
yourself: exchange + market name, an on-chain contract address, or a fixed price.

**2. The same coin on different exchanges is tracked as separate positions.**
Your BTC on Binance and your BTC on MEXC keep independent cost bases.

---

## Features

- **Multi-tier price discovery** — Binance, MEXC, WhiteBIT, Gate.io and on-chain
  (DexScreener). You decide which sources are enabled and in what order.
- **Per-symbol source pinning** — if a coin is found by none of the tiers, you define
  its source from the UI. No code changes required.
- **Ambiguity warning** — an on-chain match made by ticker alone is flagged, because
  ticker symbols are not unique across chains.
- **DCA / cost averaging** — consolidated average or FIFO for partial sales.
- **Net break-even** — average cost tells you what the lots *you still hold* cost;
  it says nothing about coins you already sold. A separate figure folds the realised
  result back in and shows the price at which everything you ever did in that coin
  nets to zero. On real data the two differed by more than 2x. Both are shown, never
  substituted for one another; coins with no recorded sales are labelled as such,
  because "same as average cost" means "we don't know your history", not "you never lost".
- **Transfers are not sales** — moving a coin from an exchange to your own wallet
  keeps its cost basis, produces no cash movement and no realised P&L. Each lot
  travels with its own cost, so FIFO stays correct afterwards.
- **Your own locations** — add any wallet or exchange alongside the four built-in
  ones (MetaMask, Ledger, another exchange). Locations are derived from your data:
  anything you add gets its own tab, cash field and colour in the holdings view.
- **Write-offs for dead positions** — delisted, rugged or lost coins can be closed
  at zero. The full cost becomes a realised loss and **no cash is credited**, so your
  total stops being inflated by holdings that are actually worth nothing. Write-offs
  are reported separately from trading results, and both they and transfers can be undone.
- **Hedge tracking** — record leveraged positions you opened on an exchange, see your
  net exposure and hedge ratio, and model "what if the price drops 20%".
- **Take-profit targets** — define a target price and book the sale in one click.
- **AI advisor** — supply a Gemini API key for portfolio analysis; falls back to a
  local rule engine without one. Every report is archived, and each new analysis is
  given the previous one plus your closed trades, so the model can see whether you
  acted on its last recommendation. It is told your cash ratio and the dollar value
  of the trade it is about to propose — without those it kept recommending the same
  $55 sale of a $220 position, day after day, to someone already half in cash.
  Repeating advice is correct when nothing changed; hiding the repetition is not.
- **Market context for the AI** — BTC trend (price, 7/30/90-day change, distance from
  the 50- and 200-day averages, drawdown, volatility), ETH/BTC, market breadth,
  the Fear & Greed index, and BTC dominance. No API key required; a free CoinGecko
  Demo key is preferred and lifts the shared 5-15 requests/minute limit to 100.
  Breadth costs zero extra requests — it is derived from the Binance ticker the app
  already downloads. The app deliberately produces **no verdicts**: no "bull market",
  no "death cross", just the measurements, each carrying its own age. Stale values are
  labelled with their age; very old ones are dropped rather than passed off as current.
  Analysis never waits on market data — one source measured 7-22 seconds on a real
  connection, so everything is fetched in the background and read from cache.
- **Settings backups** — every distinct settings state is saved, both before and after
  each write, and restorable from the UI. This exists because on 5 September 2026 the
  settings file was overwritten with defaults and a user's API keys, wallet
  connections and PIN were lost unrecoverably: until then only the ledger was backed
  up. A ledger can be rebuilt from exchange records; an exchange API secret is shown
  once and never again.
- **PIN protection** — SHA-256 with a per-install salt, recovery key for reset.
- **Net-worth archive** — exchanges do not keep history forever and their windows
  slide (Binance ~2 years, MEXC 1 month). Every time the app runs it records the
  day's portfolio state into a local SQLite archive, so the history the exchange
  deletes stays with you and a real net-worth curve builds up over time. Days with
  no record are reported, not hidden.
- **Trades you make on the exchange are captured** — the app reads your exchange
  trade history and puts new fills in an inbox on the ledger tab. **Nothing is
  written to your ledger automatically**: in a partial sale the cost method
  (consolidated average vs FIFO) changes the result, and that choice is yours.
  Each row carries the exchange's own trade id, so the same fill can never be
  booked twice, and a row that resembles an existing closed entry (same day,
  similar quantity) is flagged as a *possible* manual duplicate — entries you
  typed yourself carry no trade id, so a certain match is impossible and the
  warning says so.
- **Dust conversion is not a trade** — Binance's "Convert Small Balances" never
  appears in the trade history; it lives on a separate endpoint. Measured on real
  data: a **17.03 USDT** conversion would have erased **434.54 USD** of cost basis
  — a ~418 USD realised loss, invisible to the ledger, with seven positions left
  open and still being priced. "Small balance" is small in market value, not in
  cost basis. MEXC exposes no such endpoint, and the app says so rather than
  pretending to cover it.
- **Unexplained balance changes are reported, not hidden** — deposits, withdrawals,
  Earn subscriptions and futures transfers are out of scope for now. When a balance
  moves and no trade explains it, you are told which asset moved and by how much,
  instead of silence. The first scan of a symbol only sets a starting point: this
  captures what happens from now on and does not backfill history.
- **Exchange reconciliation** — compares the export files you download from your
  exchange (Binance CSV, MEXC XLSX) against your ledger and shows the differences.
  The comparison **writes nothing to the ledger**. The report distinguishes a
  genuine discrepancy from "the export does not reach back that far". Binance's
  full account ledger is read too, not just spot trades: airdrops, Launchpool,
  Convert, dust-to-BNB conversions and wallet transfers never appear in a trade
  history, and a balance rebuilt without them is wrong.
- **Reconciliation repair** — replays those events through FIFO and rebuilds the
  lots you should be holding today, **with their real purchase dates and real
  prices**. You do not have to remember which trade you forgot to record; the file
  already knows. Repairs are applied **one position at a time**, require explicit
  approval and can be undone — there is no bulk import. The realised P&L of past
  round-trips — invisible until now if your ledger has no sale records — is booked
  as a single summary entry; without it a repair would cheapen the position and
  make your results look better than they are.
- **No repair without corroboration** — files alone cannot say which side is
  right. A coin bought before the export window and never sold leaves no trace at
  all, so the rebuild reads it as "recorded in error" and offers to delete it.
  Every repair therefore asks for your **current balance on the exchange** before
  it will write anything: if that number matches the rebuild, your ledger is
  corrected; if it matches your ledger, the export is the incomplete one and
  **your ledger is left untouched**. There is no green "ready to apply" badge,
  because nothing earns one from a file.
- **Wallet connections (read-only)** — paste a wallet's **public address** and the
  app reads the chain directly: no file downloads, no exchange keys. It reads the
  *chain*, not the wallet, so MetaMask, Phantom, Ledger and Trust are all covered
  by two adapters — EVM (Ethereum, BNB Chain, Polygon, Arbitrum, Optimism, Base,
  Avalanche) and Solana. Connections are configuration, not code: adding a wallet
  is filling a form. An unreadable connection is reported as *unknown*, never as
  an empty wallet. **The app never asks for a seed phrase or private key**, and
  refuses one if pasted into the address field.
- **Manual token definition** — Etherscan's free plan covers automatic token
  discovery on some chains but not others (BNB Chain, Base, Optimism and
  Avalanche need a paid plan). No payment is required to work around that:
  reading a balance is free, only *knowing which tokens you hold* is not. Paste
  the token's contract address and the app asks the chain for its symbol and
  decimals. On free chains manual tokens are **added to** automatic discovery,
  not substituted for it.
- **One-click ledger entry from the chain** — for an asset sitting in your
  wallet but missing from your ledger, the form opens pre-filled with coin,
  quantity and location; **you supply the date and the cost.** Writing it
  automatically is deliberately not offered: the chain knows the quantity but
  not the cost, and booking it at zero would fabricate a profit that never
  happened. Done once per asset, after which it behaves like any other position.
- **Exchange API connections (read-only)** — your spot balance is read straight
  from the exchange, so there is no monthly file download. Adapters are written
  per **signing family**, not per exchange, and an exchange lives in
  `settings.json` as a profile: adding one is filling a form. One family ships
  today (Binance-style HMAC-SHA256) and it covers Binance and MEXC together; an
  exchange with a different signing scheme still needs code, and that is
  **stated plainly** rather than promised away. Unlike a wallet address, an API
  key is a genuine secret: it is held in the encrypted vault, never written to
  `settings.json` in plaintext, and a **write-capable key is refused** —
  permissions are checked *before* anything is stored. Where they cannot be
  checked (MEXC's API does not report a key's permissions) that is not hidden:
  rather than passing off the account's permissions as the key's and giving you
  a guarantee we cannot make, your explicit acknowledgement is required.
- **What the difference is worth** — every quantity in the comparison table
  carries its USD value underneath, and rows are ordered by the **size of the
  difference**: the question is not "where is there a difference?" but "which
  difference matters?". Differences below a threshold you set are folded away
  (their count and total stay visible, one click expands them), because after
  an exchange connection the table fills with fee dust. A row whose price
  cannot be found shows `—` and is **never folded**: an unknown value is not a
  zero value.
- **Misfiled-location detection** — when the same asset shows as "in the ledger,
  not on chain" at one location and "on chain, not in the ledger" at another,
  with similar quantities, that is not two separate gaps but **one asset filed
  on the wrong shelf**. The add button is deliberately withheld on those rows —
  adding would count the asset twice — and a button that corrects the record's
  location (and symbol) appears instead. It is not a transfer: the asset never
  moved, it was simply recorded in the wrong place.
- **Unrecognised-token filter** — tokens sent to you unsolicited never enter the
  ledger on their own. "I don't know" is kept distinct from "fake": when a
  curated list rejects a token the row is folded away, but when there is no
  verdict at all the row **stays visible** and only the add button is withheld.
  Conflating the two would hide assets you genuinely hold but haven't recorded
  yet. The final say is yours: a "this is real" / "spam" mark is permanent and
  binds to the **contract address**, not the symbol, which can be imitated.
- **Location-correct symbols** — an exchange holding is a trading pair
  (`BNBUSDT`); the same coin in your wallet is just `BNB`, because a wallet
  has no pairs. Transfers now rewrite the symbol for the destination, and a
  one-time migration repairs records created by earlier transfers. Only the
  name changes — never quantity, cost, date or status.
- **Graded read notes** — a reading is *complete*, *incomplete* or *failed*, and
  each note carries its own level. An informational note (Solana's unverified-token
  notice, say) no longer raises the same alarm as data that genuinely did not
  arrive; inflating the alarm buries the real problem.
- **Key vault** — provider and (later) exchange API keys are **encrypted** with a
  key derived from your PIN via PBKDF2; the decryption key is never written to
  disk and lives only in memory for the session you unlock. Nothing connects
  anywhere until you unlock it. Changing your PIN re-seals the vault; resetting it
  via the recovery key clears the vault instead of keeping undecryptable data
  around and pretending your keys survived.
- **Tax-ready export — an export, not a report.** One file per year for your
  accountant: every realised event as a row, with acquisition and disposal
  dates, quantities, unit prices, fees and realised P&L. It deliberately
  computes **no tax** — no taxable base, no rate, no offset — because producing
  a calculated liability creates responsibility, and crypto taxation in Turkey
  is not settled. Amounts stay in **USD**: applying a TRY rate would mean
  deciding *which* institution's rate, *which* rate (buying, selling,
  effective) and which day's rate on a holiday — decisions the app cannot make
  for you, and a wrong rate turns correct data into a wrong filing.
  What makes it auditable is that **nothing is silently dropped**: every ledger
  record lands in exactly one of four buckets — realised, missing-data,
  out-of-scope, still open — and they sum to the ledger. Positions closed
  without an exit price (probably sold but never recorded) get their own sheet
  and a warning *before* you download, rather than quietly vanishing and
  understating both your gains and your losses. Transfers and reconciliation
  closures are listed too, each with the reason it is not a disposal.
- **Excel export**, daily automatic backups, privacy mode.

---

## Installation

Requires **Python 3.10+** (Windows).

```bat
setup.bat
```

The wizard checks your Python version, installs dependencies, verifies the install
and prepares the data directory. It never touches existing data.

Manual installation:

```bat
python -m pip install -r requirements.txt
```

## Running

```bat
Baslat.bat
```

Opens `http://localhost:8000` in your browser. `Durdur.bat` stops it.

---

## Does it need internet?

**Yes, for prices.** Prices are fetched live from exchanges; charts come from
TradingView and DexScreener.

Frontend libraries (Tailwind, Alpine.js, Chart.js, Lucide, web fonts) are bundled
under `app/static/vendor/`, so the interface loads even when CDNs are unreachable.
That is not the same as full offline operation — it removes the CDN dependency.

---

## Where is your data?

```
data/
├── portfolio.json      Your transactions, targets and hedge records
├── settings.json       PIN hash, API keys, preferences
├── archive.db          Daily net-worth and price archive (SQLite)
├── backups/            Daily automatic backups
└── logs/               Application logs
```

This directory is excluded via `.gitignore`. **Never share it.**

> **About API keys — two different mechanisms, on purpose:**
>
> - **Vault keys** (provider and exchange keys, under `vault`) are **encrypted**
>   with a key derived from your PIN. The decryption key is never stored; it lives
>   in memory only while the vault is unlocked.
> - **Gemini / Telegram keys** (under `api_keys`) are only **Base64-obfuscated**,
>   which is **not encryption** — anyone with the file can read them. That is an
>   accepted trade-off for keys that merely spend your own quota; it would not be
>   acceptable for a key that can touch money, which is why those go in the vault.

---

## Tests

```bat
python -m pip install -r requirements-dev.txt
python -m pytest
```

801 tests, about 55 seconds. The suite **never touches your real data and never hits
the network**: data paths are redirected to a temporary directory, all external calls
are mocked, and no test calls the AI API.

---

## Architecture

```
app/
├── main.py           FastAPI server and REST endpoints
├── data_manager.py   Financial engine: cost basis, FIFO, hedging, PIN, Excel
├── price_service.py  Multi-tier price discovery and source registry
├── archive.py        SQLite net-worth / price archive (never on the critical path)
├── reconcile.py      Exchange export ↔ ledger reconciliation and repair
│                     proposals (read-only; writes go through data_manager)
├── connections.py    Connection registry + on-chain readers (EVM, Solana)
├── exchanges.py      Exchange API profiles + read-only balance, trade and
│                     dust-log readers, written per signing family
│                     (GET only, never trades)
├── trade_sync.py     Captures fills and dust conversions into an approval
│                     inbox; never writes to the ledger on its own
├── tax_export.py     Tax-ready export (read-only; calculates no tax, USD only)
├── keyvault.py       PIN-derived encryption for API keys (session-only)
├── ai_service.py     Gemini integration + local fallback engine
├── market_service.py Market context for the AI (background, cached, age-aware)
└── static/           Alpine.js single-page UI + bundled libraries
```

No build step. No Node.js, npm or bundler required.

---

## Disclaimer

This is a personal tracking tool, not investment advice. Prices come from third-party
sources and may be wrong or delayed. Verify the numbers against your own records
before using them for tax or accounting purposes.

## License

MIT — see [LICENSE](LICENSE).
