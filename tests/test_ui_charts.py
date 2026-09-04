"""
Arayüz grafiklerinin kurulum mantığı.

NEDEN VAR
---------
Net varlık eğrisi aylarca boş göründü ve kimse fark etmedi, çünkü `app.js`
hiç test edilmiyordu. Arka uç kusursuzdu: arşiv veritabanında 7 kayıt vardı,
uç 200 dönüyordu, hatta `fetchArchive()` doğru veriyi alıp `Chart`'ı doğru
argümanlarla kuruyordu. Kırık olan tek şey grafiğin ekrana çizilmesiydi —
ve bu, sunucu testleriyle görülemeyecek tek katmandı.

İki ayrı kusur vardı:

1. **Chart nesnesi Alpine'ın reaktif proxy'sinde saklanıyordu.**
   `this.netWorthChart = new Chart(...)` yazınca nesne Alpine'ın reaktif
   grafiğine giriyor; geri okunduğunda ham nesne değil bir Proxy dönüyor.
   `destroy()` o proxy üzerinden çağrılınca Chart.js'in canvas kaydından
   silinme işlemi kimliğe dayandığı için tutmuyor. Sonraki kurulum
   "Canvas is already in use" fırlatıyor, istisna `$nextTick` içinde
   yutuluyor ve ekranda eski grafik kalıyor.

2. **Grafik, kutusu gizliyken kuruluyordu.** `initApp()` açılışta
   `fetchArchive()` çağırıyor, o sırada sekme `display:none`. Canvas 0×0
   doğuyor. Diğer üç grafik yalnızca sekmeleri görünürken kurulduğu için
   bu kusuru taşımıyordu.

Birinci kusur DÖRT grafikte de vardı; diğer üçü ilk çizimleri görünür hâlde
olduğu için şansla ayaktaydı. Bu yüzden düzeltme ortak yardımcıda.

NASIL TEST EDİLİYOR
-------------------
`portfolioApp()` düz bir fonksiyon, tarayıcıya bağımlı değil. Node'da
`document`, `window.Chart` ve `fetch` sahteleriyle çalıştırılabiliyor.
Alpine'ın reaktif proxy'si de burada taklit ediliyor — asıl hatayı üreten
mekanizma buydu, o yüzden testin onu içermesi şart.
"""

import json
import os
import shutil
import subprocess

import pytest

PROJE_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(PROJE_KOK, "app", "static", "app.js")
INDEX_HTML = os.path.join(PROJE_KOK, "app", "static", "index.html")

NODE = shutil.which("node")
node_gerekli = pytest.mark.skipif(NODE is None, reason="node bulunamadı")


# ===========================================================================
# NODE KOŞUMU — gerçek app.js, sahte tarayıcı
# ===========================================================================

HARNESS = r"""
const fs = require('node:fs');
const appJsYolu = process.argv[2];
const seri = JSON.parse(process.argv[3]);
const gorunur = process.argv[4] === 'gorunur';
const proxyliDepo = process.argv[5] === 'proxyli';

// --- Sahte Chart.js: gerçeğinin canvas kaydını ve kimlik kontrolünü taklit eder
const kayit = new Map();      // el -> ham örnek
const olay = [];
class SahteChart {
  constructor(el, cfg) {
    if (kayit.has(el)) {
      // Chart.js v4'ün gerçek davranışı.
      throw new Error('Canvas is already in use. Chart must be destroyed first.');
    }
    this.el = el; this.cfg = cfg;
    kayit.set(el, this);
    olay.push({tip: 'olustur', labels: cfg.data.labels.length});
  }
  destroy() {
    // Gerçek Chart.js de kaydı KİMLİĞE göre siler. `this` bir Proxy ise
    // kayıttaki ham örnekle eşleşmez ve silme sessizce başarısız olur.
    let silindi = false;
    for (const [el, ornek] of kayit) {
      if (ornek === this) { kayit.delete(el); silindi = true; }
    }
    olay.push({tip: 'yoket', silindi});
  }
  static getChart(el) { return kayit.get(el) || null; }
}

// --- Sahte DOM
const canvas = {
  id: 'netWorthChart',
  isConnected: true,
  offsetParent: gorunur ? {} : null,   // display:none ise null olur
  getContext: () => ({}),
};
globalThis.window = {};
globalThis.window.Chart = SahteChart;
globalThis.Chart = SahteChart;
globalThis.document = {
  getElementById: (id) => (id === 'netWorthChart' ? canvas : null),
  addEventListener: () => {},
  querySelectorAll: () => [],
};
globalThis.localStorage = {getItem: () => null, setItem: () => {}, removeItem: () => {}};
globalThis.fetch = async () => ({
  ok: true,
  json: async () => ({series: seri, status: {snapshot_count: seri.length}}),
});

const src = fs.readFileSync(appJsYolu, 'utf8');
let app = new Function(src + '\n;return portfolioApp;')()();
app.$nextTick = (cb) => cb();
app.notify = () => {};

// --- Alpine'ın reaktif proxy'sini taklit et
// Alpine 3 bileşen verisini @vue/reactivity ile sarar; saklanan nesneler geri
// okunurken proxy'ye dönüşür. Hatanın kaynağı tam olarak buydu.
if (proxyliDepo) {
  const kap = new WeakMap();
  app = new Proxy(app, {
    get(h, k, r) {
      const v = Reflect.get(h, k, r);
      if (v && typeof v === 'object' && !(v instanceof Function)) {
        if (!kap.has(v)) kap.set(v, new Proxy(v, {}));
        return kap.get(v);
      }
      return v;
    },
  });
}

const hatalar = [];
(async () => {
  for (let i = 0; i < 3; i++) {
    try { await app.fetchArchive(); }
    catch (e) { hatalar.push(String(e.message || e)); }
  }
  console.log(JSON.stringify({
    olay,
    hatalar,
    canliGrafik: kayit.size,
    seriUzunlugu: app.archiveSeries.length,
  }));
})();
"""


def _kosum(seri, gorunur=True, proxyli=True, tmp_path=None):
    yol = os.path.join(str(tmp_path), "harness.js")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(HARNESS)
    p = subprocess.run(
        [NODE, yol, APP_JS, json.dumps(seri),
         "gorunur" if gorunur else "gizli",
         "proxyli" if proxyli else "duz"],
        capture_output=True, text=True, timeout=60,
    )
    assert p.returncode == 0, f"node hatası:\n{p.stderr}"
    return json.loads(p.stdout.strip().splitlines()[-1])


def _seri(n=7):
    return [
        {"taken_date": f"2026-08-{20 + i:02d}", "total_equity_usd": 2400.0 + i,
         "spot_value_usd": 1200.0 + i, "spot_invested_usd": 4500.0 - i}
        for i in range(n)
    ]


@node_gerekli
class TestNetVarlikGrafigi:

    def test_gorunurken_kurulur(self, tmp_path):
        s = _kosum(_seri(), tmp_path=tmp_path)
        olusan = [o for o in s["olay"] if o["tip"] == "olustur"]
        assert olusan, "Grafik hiç kurulmadı"
        assert olusan[0]["labels"] == 7
        assert s["seriUzunlugu"] == 7

    def test_tekrar_tekrar_cagrilmasi_bozmaz(self, tmp_path):
        """ASIL REGRESYON.

        Aralık düğmelerine basmak `fetchArchive()`'i yeniden çalıştırır.
        Eski kodda ikinci çağrı "Canvas is already in use" fırlatıyordu ve
        ekranda ilk (0×0) grafik kalıyordu. Burada üç kez çağrılıyor.
        """
        s = _kosum(_seri(), proxyli=True, tmp_path=tmp_path)

        assert s["hatalar"] == [], f"Yeniden kurulum patladı: {s['hatalar']}"
        assert len(([o for o in s["olay"] if o["tip"] == "olustur"])) == 3
        assert s["canliGrafik"] == 1, "Her seferinde tek canlı grafik kalmalı"

        # Yok etme gerçekten TUTMALI. Proxy üzerinden yapılsaydı `silindi`
        # false dönerdi ve bir sonraki kurulum patlardı.
        yoketmeler = [o for o in s["olay"] if o["tip"] == "yoket"]
        assert len(yoketmeler) == 2
        assert all(o["silindi"] for o in yoketmeler), (
            "Eski grafik kayıttan silinemedi — Chart.getChart yerine "
            "proxy'lenmiş referans kullanılıyor olabilir"
        )

    def test_gizliyken_kurulmaz(self, tmp_path):
        """0×0 canvas'a çizmek boş grafik üretir; hiç kurmamak doğrusu.

        Açılışta `initApp()` bu yoldan geçiyor ve sekme o sırada kapalı.
        """
        s = _kosum(_seri(), gorunur=False, tmp_path=tmp_path)
        assert [o for o in s["olay"] if o["tip"] == "olustur"] == []
        assert s["canliGrafik"] == 0
        assert s["hatalar"] == []
        # Veri yine de çekilmeli — kartlar ve kayıt tablosu ona bağlı.
        assert s["seriUzunlugu"] == 7

    def test_tek_kayitla_grafik_kurulmaz(self, tmp_path):
        """Tek noktalı çizgi anlamsız; arayüz onun yerine mesaj gösteriyor."""
        s = _kosum(_seri(1), tmp_path=tmp_path)
        assert [o for o in s["olay"] if o["tip"] == "olustur"] == []
        assert s["hatalar"] == []

    def test_bos_arsivde_patlamaz(self, tmp_path):
        s = _kosum([], tmp_path=tmp_path)
        assert s["hatalar"] == []
        assert s["canliGrafik"] == 0


# ===========================================================================
# YAPISAL DENETİMLER — node gerekmez
# ===========================================================================

class TestGrafikKurulumKurallari:

    def _app_js(self):
        with open(APP_JS, encoding="utf-8") as f:
            return f.read()

    def _index(self):
        with open(INDEX_HTML, encoding="utf-8") as f:
            return f.read()

    def test_hicbir_grafik_kendi_referansini_yoketmiyor(self):
        """`this.xxxChart.destroy()` kalıbı geri gelmemeli.

        Alpine bu referansı proxy'ler; yok etme kimlik karşılaştırmasına
        dayandığı için sessizce başarısız olur. Doğrusu `Chart.getChart(el)`.
        """
        import re
        kotu = re.findall(r"this\.\w*[Cc]hart\.destroy\(\)", self._app_js())
        assert kotu == [], (
            f"Proxy'lenmiş referans üzerinden yok etme geri gelmiş: {kotu}. "
            "Bunun yerine _chartHedefi() kullanın."
        )

    def test_tum_grafikler_ortak_yardimciyi_kullaniyor(self):
        import re
        js = self._app_js()
        kurulumlar = re.findall(r"new Chart\((\w+)", js)
        assert kurulumlar, "Hiç grafik kurulumu bulunamadı — test bayatlamış"
        for degisken in kurulumlar:
            kalip = rf"(?:const|let)\s+{degisken}\s*=\s*this\._chartHedefi\("
            assert re.search(kalip, js), (
                f"'{degisken}' _chartHedefi() üzerinden alınmıyor; "
                "gizli kutuya çizme ve proxy tuzağı geri gelir"
            )

    def test_kurulan_her_canvas_html_de_gercekten_var(self):
        """Ölü grafik kodu bırakmayalım.

        Bu denetim yazıldığında `allocationChart` ve `pnlChart` blokları
        vardı ama HTML'de o id'li canvas YOKTU — kod sessizce hiçbir şey
        yapmıyordu. Bir daha olmasın.
        """
        import re
        idler = set(re.findall(r"this\._chartHedefi\('([^']+)'\)", self._app_js()))
        assert idler, "Yardımcıya hiç id verilmiyor — test bayatlamış"
        html = self._index()
        eksik = [i for i in sorted(idler) if f'id="{i}"' not in html]
        assert eksik == [], f"HTML'de karşılığı olmayan canvas id'leri: {eksik}"

    def test_alt_sekme_degisince_yeniden_cizim_yolu_var(self):
        """Hatanın ikinci yarısı: kutu görünür olunca kimse yeniden çizmiyordu.

        Diğer grafiklerin `activeTab` üzerinden bu yolu vardı, net varlık
        eğrisinin hiç yoktu.
        """
        js = self._app_js()
        assert "$watch('tvSubTab'" in js, "tvSubTab izleyicisi kaldırılmış"
        parca = js.split("$watch('tvSubTab'", 1)[1][:600]
        assert "renderNetWorthChart" in parca, (
            "Arşiv sekmesi açılınca net varlık eğrisi yeniden çizilmiyor"
        )

    def test_app_js_surumu_index_ile_uyumlu(self):
        """`app.js?v=` sürümü bump edilmezse kullanıcı bayat dosya alır.

        Bu düzeltme tamamen istemci tarafında; sürüm artmazsa tarayıcı
        önbellekten eski app.js'i sunar ve hata düzelmiş görünmez.
        """
        import re
        m = re.search(r'app\.js\?v=([\d.]+)', self._index())
        assert m, "index.html app.js'i sürümsüz yüklüyor"
        assert float(m.group(1)) >= 2.3


# ===========================================================================
# YAZDIRMA / PDF DOSYA ADI
#
# Kullanıcı her analizi "Yazdır" ile PDF olarak kaydediyordu ve dört ayrı
# analiz de aynı adla iniyordu: "Kripto Portföy Takip & Canlı Terminal".
# Sebep: tarayıcı PDF adını `document.title`'dan alır ve başlık sabitti.
# Sorun YZ sekmesine özgü değildi — her sekmede vardı.
# ===========================================================================

PRINT_HARNESS = r"""
const fs = require('node:fs');
const durum = JSON.parse(process.argv[3]);

// Gerçek index.html'deki sabit başlığın yerine geçen değer. Test bunu metin
// olarak GÖMMEZ; harness geri bildirir ve karşılaştırma ona göre yapılır.
// Başlık ileride meşru bir sebeple değişirse test yanlış yere kırılmasın.
const ILK_BASLIK = 'CoinTakip Test Basligi';
let baslik = ILK_BASLIK;
const olaylar = [];
let afterprintCb = null;

globalThis.window = {
  addEventListener: (ad, cb) => { if (ad === 'afterprint') afterprintCb = cb; },
  removeEventListener: () => { afterprintCb = null; },
  print: () => { olaylar.push({tip: 'print', baslik: baslik}); },
};
globalThis.document = {
  get title() { return baslik; },
  set title(v) { baslik = v; olaylar.push({tip: 'baslik', deger: v}); },
  getElementById: () => null,
  addEventListener: () => {},
  querySelectorAll: () => [],
};
globalThis.localStorage = {getItem: () => null, setItem: () => {}, removeItem: () => {}};
globalThis.fetch = async () => ({ok: false});
globalThis.setTimeout = () => 0;   // emniyet supabini bu testte tetikleme

const src = fs.readFileSync(process.argv[2], 'utf8');
const app = new Function(src + '\n;return portfolioApp;')()();
app.$nextTick = (cb) => cb();
app.notify = () => {};
Object.assign(app, durum);

const ad = app.printDocumentName();
app.printPortfolioReport();
const yazdirmaAninda = olaylar.filter(o => o.tip === 'print').map(o => o.baslik);

// Tarayici yazdirmayi bitirdiginde afterprint tetiklenir.
const tetiklendi = Boolean(afterprintCb);
if (afterprintCb) afterprintCb();

console.log(JSON.stringify({
  hesaplananAd: ad,
  yazdirmaAninda,
  ilkBaslik: ILK_BASLIK,
  sonBaslik: baslik,
  afterprintBagliMi: tetiklendi,
}));
"""


def _print_kosum(durum, tmp_path):
    yol = os.path.join(str(tmp_path), "print_harness.js")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(PRINT_HARNESS)
    p = subprocess.run([NODE, yol, APP_JS, json.dumps(durum)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"node hatası:\n{p.stderr}"
    return json.loads(p.stdout.strip().splitlines()[-1])


@node_gerekli
class TestYazdirmaDosyaAdi:

    def test_yz_modlari_ayri_ad_uretir(self, tmp_path):
        """Asıl şikâyet: dört analiz de aynı adla kaydediliyordu."""
        adlar = {}
        for mod in ("full_audit", "recovery", "brutal", "take_profit"):
            s = _print_kosum({"activeTab": "ai", "aiMode": mod,
                              "aiViewingArchived": None}, tmp_path)
            adlar[mod] = s["hesaplananAd"]

        assert len(set(adlar.values())) == 4, f"Adlar çakışıyor: {adlar}"
        assert "Kar_Realizasyonu" in adlar["take_profit"]
        assert "Zarardan_Kurtarma" in adlar["recovery"]
        assert "Aci_Gercek" in adlar["brutal"]
        assert "Butunsel_Denetim" in adlar["full_audit"]

    def test_diger_sekmeler_de_kendi_adini_alir(self, tmp_path):
        """Sorun YZ'ye özgü değildi; her sekme aynı adla kaydediliyordu."""
        adlar = set()
        for sekme in ("dashboard", "ledger", "hedge", "simulation"):
            s = _print_kosum({"activeTab": sekme}, tmp_path)
            adlar.add(s["hesaplananAd"])
        assert len(adlar) == 4, f"Sekme adları çakışıyor: {adlar}"

    def test_grafik_alt_sekmeleri_ayrisir(self, tmp_path):
        a = _print_kosum({"activeTab": "charts", "tvSubTab": "archive"}, tmp_path)
        b = _print_kosum({"activeTab": "charts", "tvSubTab": "reconcile"}, tmp_path)
        assert "Net_Varlik_Arsivi" in a["hesaplananAd"]
        assert "Borsa_Mutabakati" in b["hesaplananAd"]

    def test_ad_ascii_ve_dosya_adi_icin_guvenli(self, tmp_path):
        """Türkçe karakterli dosya adları bazı sistemlerde bozuluyor."""
        import re
        for durum in ({"activeTab": "ai", "aiMode": "take_profit", "aiViewingArchived": None},
                      {"activeTab": "dashboard"},
                      {"activeTab": "charts", "tvSubTab": "health"}):
            ad = _print_kosum(durum, tmp_path)["hesaplananAd"]
            assert ad.isascii(), f"ASCII değil: {ad}"
            assert re.fullmatch(r"[A-Za-z0-9_\-]+", ad), f"Riskli karakter: {ad}"
            assert ad.startswith("CoinTakip_")
            assert re.search(r"\d{4}-\d{2}-\d{2}$", ad), f"Tarih yok: {ad}"

    def test_arsivden_acilan_rapor_kendi_tarihini_tasir(self, tmp_path):
        """30 Ağustos raporu 4 Eylül dosyası gibi kaydedilmemeli.

        Aksi hâlde düzeltmeye çalıştığımız karışıklığın aynısı üretilir.
        """
        s = _print_kosum({
            "activeTab": "ai", "aiMode": "full_audit",
            "aiViewingArchived": {"mode": "recovery",
                                  "created_at": "2026-08-30T21:14:05"},
        }, tmp_path)
        assert s["hesaplananAd"] == "CoinTakip_Zarardan_Kurtarma_2026-08-30"

    def test_bozuk_tarihte_bugune_duser(self, tmp_path):
        import datetime
        s = _print_kosum({
            "activeTab": "ai", "aiMode": "full_audit",
            "aiViewingArchived": {"mode": "brutal", "created_at": "bozuk"},
        }, tmp_path)
        bugun = datetime.date.today().isoformat()
        assert s["hesaplananAd"] == f"CoinTakip_Aci_Gercek_{bugun}"

    def test_baslik_yazdirma_aninda_degismis_olur(self, tmp_path):
        """Başlık print() çağrılmadan ÖNCE kurulmalı; sonra kurulursa
        tarayıcı eski adı kullanır."""
        s = _print_kosum({"activeTab": "ai", "aiMode": "take_profit",
                          "aiViewingArchived": None}, tmp_path)
        assert len(s["yazdirmaAninda"]) == 1
        assert s["yazdirmaAninda"][0] == s["hesaplananAd"]

    def test_baslik_yazdirmadan_sonra_geri_alinir(self, tmp_path):
        """Geri alınmazsa tarayıcı sekmesi kalıcı olarak yanlış adda kalır."""
        s = _print_kosum({"activeTab": "ai", "aiMode": "take_profit",
                          "aiViewingArchived": None}, tmp_path)
        assert s["afterprintBagliMi"] is True, "afterprint dinleyicisi bağlanmamış"
        assert s["sonBaslik"] == s["ilkBaslik"], (
            "Başlık geri alınmadı — sekme kalıcı olarak yanlış adda kalır")

    def test_bilinmeyen_sekme_de_ad_uretir(self, tmp_path):
        s = _print_kosum({"activeTab": "boyle_bir_sekme_yok"}, tmp_path)
        assert s["hesaplananAd"].startswith("CoinTakip_Portfoy_Raporu_")
