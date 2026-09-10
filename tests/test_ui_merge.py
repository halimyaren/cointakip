"""
CoinTakip — Konsolide Tablo Birleştirme ve Gelen Kutusu Katlaması

Bu takımın çıkış noktası kullanıcının 7 Eylül 2026'daki üç gözlemi:

  1. "Konsolide portföyde 2 tane TIA var. Defter değil ki orası."
     Hata değildi: TIA hem BINANCE'te (5 lot, 109.59 adet, ort $2.9087) hem
     MEXC'te (1 lot, 10.82 adet, ort $4.0590) duruyor ve tablo SEMBOL@BORSA
     ile gruplar. Ama itiraz haklıydı — "Konsolide" başlığı coin başına tek
     satır beklentisi yaratıyor ve net başa baş ZATEN sembol bazlı
     hesaplandığı için iki satır aynı "Net B.B" değerini gösteriyor, yani
     tam olarak kopya gibi duruyor. Çözüm: birleştirme bir SEÇENEK oldu.

  2. "Transfer ve Zarar Yaz butonları görünmüyor, üstüne gelince görünüyor."
     28 Ağustos'tan beri `opacity-0` idi. Gizli bir düğme keşfedilemeyen bir
     düğmedir; dokunmatik ekranda ise hiç görünmüyordu.

  3. Borsa İşlemleri kutusu bekleyen hiçbir şey yokken de yer kaplıyordu.

Node varsa gerçek mantık koşturulur; yoksa yapısal denetimler yine çalışır.
"""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(PROJECT_ROOT, "app", "static", "app.js")
INDEX_HTML = os.path.join(PROJECT_ROOT, "app", "static", "index.html")

NODE = shutil.which("node")
node_gerekli = pytest.mark.skipif(NODE is None, reason="node bulunamadı")


HARNESS = r"""
const fs = require('node:fs');
const durum = JSON.parse(process.argv[3]);

globalThis.window = { addEventListener: () => {}, removeEventListener: () => {} };
globalThis.document = {
  title: '', getElementById: () => null, addEventListener: () => {},
  querySelectorAll: () => [],
};
globalThis.localStorage = {getItem: () => null, setItem: () => {}, removeItem: () => {}};
globalThis.fetch = async () => ({ok: false});
globalThis.setTimeout = () => 0;

const src = fs.readFileSync(process.argv[2], 'utf8');
const app = new Function(src + '\n;return portfolioApp;')()();
app.$nextTick = (cb) => cb();
app.notify = () => {};
Object.assign(app, durum);

console.log(JSON.stringify({
  rows: app.displayedCoins,
  variety: app.displayedVarietyCount,
  inboxVisible: app.exchangeInboxVisible,
}));
"""


def _kosum(durum, tmp_path):
    yol = os.path.join(str(tmp_path), "merge_harness.js")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(HARNESS)
    p = subprocess.run([NODE, yol, APP_JS, json.dumps(durum)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"node hatası:\n{p.stderr}"
    return json.loads(p.stdout.strip().splitlines()[-1])


# Kullanıcının gerçek verisinden alınan TIA vakası.
TIA_BINANCE = {
    "pos_key": "TIAUSDT@BINANCE", "symbol": "TIAUSDT", "display_name": "TIAUSDT",
    "exchange": "BINANCE", "category": "Altcoin", "dca_count": 5,
    "total_qty": 109.59, "total_invested": 318.76, "current_value": 250.0,
    "avg_cost": 2.9087, "live_price": 2.2812, "pnl_usd": -68.76, "pnl_pct": -21.57,
    "portfolio_share_pct": 3.0, "daily_diff_usd": -1.0, "change_24h_pct": -0.4,
    "no_source": False, "target": {"target_price": 5.0}, "change_7d_pct": 1.2,
}
TIA_MEXC = {
    "pos_key": "TIAUSDT@MEXC", "symbol": "TIAUSDT", "display_name": "TIAUSDT",
    "exchange": "MEXC", "category": "Altcoin", "dca_count": 1,
    "total_qty": 10.82, "total_invested": 43.92, "current_value": 24.68,
    "avg_cost": 4.059, "live_price": 2.2812, "pnl_usd": -19.24, "pnl_pct": -43.8,
    "portfolio_share_pct": 0.3, "daily_diff_usd": -0.1, "change_24h_pct": -0.4,
    "no_source": False, "target": None, "change_7d_pct": 1.2,
}
BTC = {
    "pos_key": "BTCUSDT@BINANCE", "symbol": "BTCUSDT", "display_name": "BTCUSDT",
    "exchange": "BINANCE", "category": "Majör / L1", "dca_count": 2,
    "total_qty": 0.02, "total_invested": 1700.0, "current_value": 2000.0,
    "avg_cost": 85000.0, "live_price": 100000.0, "pnl_usd": 300.0, "pnl_pct": 17.6,
    "portfolio_share_pct": 24.0, "daily_diff_usd": 5.0, "change_24h_pct": 2.0,
    "no_source": False, "target": None, "change_7d_pct": 3.0,
}

TEMEL = {
    "consolidatedCoins": [TIA_BINANCE, TIA_MEXC, BTC],
    "dashboardExchangeFilter": "all",
    "searchQuery": "",
    "sortKey": "pnl_usd",
    "sortAsc": False,
    "mergeByCoin": False,
    "expandedMergedCoins": {},
    "exchangeTrades": {"events": [], "counts": {}, "last_report": {}},
    "exchangeInboxOpen": None,
}


@node_gerekli
class TestBirlestirmeKapali:
    """Varsayılan davranış korunmalı: konum bazlı görünüm matematiksel olarak
    doğru olandır ve hiçbir şeyi bozmamalıyız."""

    def test_iki_tia_satiri_ayri_kalir(self, tmp_path):
        s = _kosum(TEMEL, tmp_path)
        tia = [r for r in s["rows"] if r["symbol"] == "TIAUSDT"]
        assert len(tia) == 2
        assert sorted(r["exchange"] for r in tia) == ["BINANCE", "MEXC"]
        assert all(not r.get("_merged") for r in tia)

    def test_satirlar_numaralanir(self, tmp_path):
        s = _kosum(TEMEL, tmp_path)
        assert [r["_no"] for r in s["rows"]] == [1, 2, 3]

    def test_cesit_sayisi_satir_sayisiyla_ayni(self, tmp_path):
        s = _kosum(TEMEL, tmp_path)
        assert s["variety"] == 3


@node_gerekli
class TestBirlestirmeAcik:

    def _acik(self, **ek):
        return {**TEMEL, "mergeByCoin": True, **ek}

    def test_tia_tek_satira_iner(self, tmp_path):
        s = _kosum(self._acik(), tmp_path)
        tia = [r for r in s["rows"] if r["symbol"] == "TIAUSDT"]
        assert len(tia) == 1
        assert tia[0]["_merged"] is True
        assert tia[0]["_locationCount"] == 2

    def test_toplamlar_dogru(self, tmp_path):
        s = _kosum(self._acik(), tmp_path)
        tia = next(r for r in s["rows"] if r["symbol"] == "TIAUSDT")
        adet = TIA_BINANCE["total_qty"] + TIA_MEXC["total_qty"]
        yatirilan = TIA_BINANCE["total_invested"] + TIA_MEXC["total_invested"]
        deger = TIA_BINANCE["current_value"] + TIA_MEXC["current_value"]
        assert tia["total_qty"] == pytest.approx(adet)
        assert tia["total_invested"] == pytest.approx(yatirilan)
        assert tia["current_value"] == pytest.approx(deger)
        assert tia["dca_count"] == 6
        assert tia["avg_cost"] == pytest.approx(yatirilan / adet)
        assert tia["pnl_usd"] == pytest.approx(deger - yatirilan)

    def test_ortalama_maliyet_iki_konumun_arasinda(self, tmp_path):
        """Birleşik ortalama, iki konumun ortalamaları arasında olmalı —
        yoksa toplama hatası var demektir."""
        s = _kosum(self._acik(), tmp_path)
        tia = next(r for r in s["rows"] if r["symbol"] == "TIAUSDT")
        assert TIA_BINANCE["avg_cost"] < tia["avg_cost"] < TIA_MEXC["avg_cost"]

    def test_tek_konumlu_coin_birlesik_olmaz(self, tmp_path):
        s = _kosum(self._acik(), tmp_path)
        btc = next(r for r in s["rows"] if r["symbol"] == "BTCUSDT")
        assert not btc.get("_merged")
        assert btc["exchange"] == "BINANCE"

    def test_birlesik_satirda_hedef_gosterilmez(self, tmp_path):
        """Hedef konum bazlıdır. Birleşik satırda BINANCE'in hedefini
        göstermek, yanlış yerden satış tetiklemeye davet olurdu."""
        s = _kosum(self._acik(), tmp_path)
        tia = next(r for r in s["rows"] if r["symbol"] == "TIAUSDT")
        assert tia["target"] is None
        assert tia["exchange"] is None

    def test_genisletilince_konum_satirlari_gelir(self, tmp_path):
        s = _kosum(self._acik(expandedMergedCoins={"TIAUSDT": True}), tmp_path)
        tia = [r for r in s["rows"] if r["symbol"] == "TIAUSDT"]
        assert len(tia) == 3                       # özet + 2 konum
        cocuklar = [r for r in tia if r.get("_child")]
        assert sorted(r["exchange"] for r in cocuklar) == ["BINANCE", "MEXC"]
        # Alt satırlar kendi hedefini ve kendi pos_key'ini korur: işlem
        # yapılacak yer orasıdır.
        assert any(r["target"] for r in cocuklar)
        assert {r["pos_key"] for r in cocuklar} == {"TIAUSDT@BINANCE",
                                                    "TIAUSDT@MEXC"}

    def test_alt_satirlar_numara_almaz(self, tmp_path):
        s = _kosum(self._acik(expandedMergedCoins={"TIAUSDT": True}), tmp_path)
        for r in s["rows"]:
            if r.get("_child"):
                assert "_no" not in r or r.get("_no") is None

    def test_cesit_sayisi_alt_satirlari_saymaz(self, tmp_path):
        s = _kosum(self._acik(expandedMergedCoins={"TIAUSDT": True}), tmp_path)
        assert s["variety"] == 2                   # TIA + BTC

    def test_anahtarlar_benzersiz(self, tmp_path):
        """Alpine `:key` olarak pos_key kullanıyor; çakışma satır karıştırır."""
        s = _kosum(self._acik(expandedMergedCoins={"TIAUSDT": True}), tmp_path)
        anahtarlar = [r["pos_key"] for r in s["rows"]]
        assert len(anahtarlar) == len(set(anahtarlar))

    def test_siralama_birlesik_satira_gore_yapilir(self, tmp_path):
        """TIA'nın iki satırı ayrıyken K/Z'leri -68.76 ve -19.24; birleşince
        -88.0 olur ve sıralamadaki yeri değişmelidir."""
        s = _kosum(self._acik(sortKey="pnl_usd", sortAsc=True), tmp_path)
        ust = [r for r in s["rows"] if not r.get("_child")]
        assert ust[0]["symbol"] == "TIAUSDT"       # en kötü K/Z başta
        assert ust[0]["pnl_usd"] == pytest.approx(-88.0)

    def test_borsa_suzgeci_birlestirmeyi_ezmez(self, tmp_path):
        """MEXC süzgeci açıkken TIA'nın yalnızca MEXC bacağı kalır; tek
        üye birleşik satır üretmemeli."""
        s = _kosum(self._acik(dashboardExchangeFilter="MEXC"), tmp_path)
        tia = [r for r in s["rows"] if r["symbol"] == "TIAUSDT"]
        assert len(tia) == 1
        assert not tia[0].get("_merged")
        assert tia[0]["exchange"] == "MEXC"

    def test_kaynagi_olan_uye_fiyati_belirler(self, tmp_path):
        kayipsiz = {**TIA_BINANCE, "no_source": True, "live_price": 0.0}
        s = _kosum({**TEMEL, "mergeByCoin": True,
                    "consolidatedCoins": [kayipsiz, TIA_MEXC, BTC]}, tmp_path)
        tia = next(r for r in s["rows"] if r["symbol"] == "TIAUSDT")
        assert tia["no_source"] is False
        assert tia["live_price"] == pytest.approx(TIA_MEXC["live_price"])

    def test_hicbir_uyede_kaynak_yoksa_satir_kaynaksizdir(self, tmp_path):
        a = {**TIA_BINANCE, "no_source": True}
        b = {**TIA_MEXC, "no_source": True}
        s = _kosum({**TEMEL, "mergeByCoin": True,
                    "consolidatedCoins": [a, b]}, tmp_path)
        assert next(r for r in s["rows"])["no_source"] is True


@node_gerekli
class TestGelenKutusuKatlamasi:

    def test_bekleyen_yokken_kapali(self, tmp_path):
        s = _kosum(TEMEL, tmp_path)
        assert s["inboxVisible"] is False

    def test_bekleyen_varken_kendiliginden_acilir(self, tmp_path):
        s = _kosum({**TEMEL,
                    "exchangeTrades": {"events": [], "counts": {"pending": 3},
                                       "last_report": {}}}, tmp_path)
        assert s["inboxVisible"] is True

    def test_kullanicinin_karari_otomatigi_ezer(self, tmp_path):
        s = _kosum({**TEMEL, "exchangeInboxOpen": True}, tmp_path)
        assert s["inboxVisible"] is True
        s = _kosum({**TEMEL, "exchangeInboxOpen": False,
                    "exchangeTrades": {"events": [], "counts": {"pending": 3},
                                       "last_report": {}}}, tmp_path)
        assert s["inboxVisible"] is False


# ===========================================================================
# YAPISAL DENETİMLER — node gerekmez
# ===========================================================================
class TestYapi:

    def _html(self):
        with open(INDEX_HTML, encoding="utf-8") as f:
            return f.read()

    def _js(self):
        with open(APP_JS, encoding="utf-8") as f:
            return f.read()

    def test_defter_eylemleri_gizli_degil(self):
        """Gizli bir düğme keşfedilemeyen bir düğmedir. Kullanıcı Transfer ve
        Zarar Yaz'ı on gün boyunca fark etmedi; dokunmatik ekranda ise
        "üstüne gelme" diye bir şey yok."""
        html = self._html()
        i = html.index("openTransferForm(coin)")
        blok = html[max(0, i - 900):i]
        assert "opacity-0 group-hover" not in blok, \
            "Transfer/Zarar Yaz yeniden fare üstüne gelmeye bağlanmış"
        assert "opacity-60 group-hover:opacity-100" in blok

    def test_birlestirme_anahtari_var(self):
        html = self._html()
        assert "mergeByCoin = !mergeByCoin" in html
        assert "Coin bazında birleştir" in html

    def test_tablo_displayed_coins_kullaniyor(self):
        html = self._html()
        assert 'x-for="(coin, index) in displayedCoins"' in html
        assert "in filteredConsolidatedCoins" not in html

    def test_birlesik_satirda_konum_eylemleri_gizli(self):
        """Birleşik satırda Transfer/Zarar Yaz/DCA/Hedef gösterilmemeli:
        hepsi tek bir konuma ait işlemler."""
        html = self._html()
        assert 'x-show="!coin._merged"' in html
        assert 'x-if="!coin.target && !coin._merged"' in html

    def test_gelen_kutusu_katlanabilir(self):
        html = self._html()
        assert "toggleExchangeInbox()" in html
        assert 'x-show="exchangeInboxVisible"' in html

    def test_collapse_eklentisi_kullanilmiyor(self):
        """`x-collapse` vendor'daki Alpine'da YOK; sessizce çalışmaz."""
        assert "x-collapse" not in self._html()

    def test_alt_bilgi_gorunen_satiri_sayar(self):
        assert "displayedVarietyCount" in self._html()

    def test_birlestirme_varsayilan_kapali(self):
        """Konum bazlı görünüm matematiksel olarak doğru olandır."""
        js = self._js()
        assert re.search(r"mergeByCoin:\s*false", js)

    def test_app_js_surumu_yukseltildi(self):
        m = re.search(r"app\.js\?v=([\d.]+)", self._html())
        assert m and float(m.group(1)) >= 2.9


class TestDefterGecmisiTekGiris:
    """FAZ F1 şeridi ile F1c üst çubuk düğmesi aynı pencereyi açıyordu ve
    Konsolide Portföy'de ikisi yan yana duruyordu. F1c'nin gerekçesi şeridin
    yerini almaktı; şerit kaldırılmayı unutmuş."""

    def _html(self):
        import os
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(kok, "app", "static", "index.html"),
                  encoding="utf-8") as f:
            return f.read()

    def test_tek_bir_giris_var(self):
        assert self._html().count("showLedgerHistory = true") == 1

    def test_giris_ust_cubukta(self):
        """Üst çubuktaki düğme HER sekmede görünür; şerit yalnızca Konsolide
        Portföy'deydi ve başka sekmedeyken geri alma yolu bulunamıyordu."""
        html = self._html()
        nerede = html.index("showLedgerHistory = true")
        # Üst çubuk arama kutusundan önce geliyor.
        assert nerede < html.index('placeholder="Coin ara')

    def test_sayac_rozeti_korundu(self):
        """Kaldırılan şerit transfer/yazım sayısını gösteriyordu; o bilgi
        kaybolmamalı."""
        html = self._html()
        nerede = html.index("showLedgerHistory = true")
        blok = html[nerede:nerede + 700]
        assert "transfers.length + writeOffs.length" in blok
