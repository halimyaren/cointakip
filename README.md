# CoinTakip

**A local-first, privacy-focused crypto portfolio tracker.**

🇹🇷 [Türkçe README](README.tr.md)

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
  local rule engine without one.
- **PIN protection** — SHA-256 with a per-install salt, recovery key for reset.
- **Net-worth archive** — exchanges do not keep history forever and their windows
  slide (Binance ~2 years, MEXC 1 month). Every time the app runs it records the
  day's portfolio state into a local SQLite archive, so the history the exchange
  deletes stays with you and a real net-worth curve builds up over time. Days with
  no record are reported, not hidden.
- **Exchange reconciliation** — compares the trade-history files you download from
  your exchange (Binance CSV, MEXC XLSX) against your ledger and shows the
  differences. It **writes nothing to the ledger**; your cost basis stays exactly as
  you entered it. The report distinguishes a genuine discrepancy from "the export
  does not reach back that far".
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

> **About API keys:** keys in `settings.json` are Base64-obfuscated — this is
> **not encryption**. Anyone with access to the file can read your key. That is
> acceptable if the key stays on your own machine; otherwise, do not configure one.

---

## Tests

```bat
python -m pip install -r requirements-dev.txt
python -m pytest
```

360 tests, about 14 seconds. The suite **never touches your real data and never hits
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
├── reconcile.py      Exchange export ↔ ledger reconciliation (read-only)
├── ai_service.py     Gemini integration + local fallback engine
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
