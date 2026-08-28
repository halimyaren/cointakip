# CoinTakip

**Yerel çalışan, gizlilik öncelikli kripto portföy takip terminali.**

🇬🇧 [English README](README.md) · 📖 [Kullanım Kılavuzu](KILAVUZ.md)

Verileriniz bilgisayarınızdan çıkmaz. Buluta yükleme yok, hesap açma yok,
borsa API anahtarı verme zorunluluğu yok. Uygulama `127.0.0.1` üzerinde
kendi makinenizde çalışır ve portföyünüzü düz JSON dosyalarında tutar.

---

## Neden bir tane daha portföy takipçisi?

Piyasada çok sayıda alternatif var ve çoğu bundan daha kapsamlı. CoinTakip iki
konuda farklılaşıyor:

**1. Fiyatı bulamadığında bunu söyler.**
Çoğu takipçi listelenmemiş, delist edilmiş veya küçük borsalarda işlem gören bir
coinde sessizce çuvallar: ya boş gösterir ya da aynı sembolü taşıyan başka bir
tokenın fiyatını getirir. CoinTakip fiyat kaynağını bulamazsa fiyat yerine `—`
gösterir ve size kaynağı kendiniz tanımlama imkânı verir — borsa + market adı,
zincir üstü kontrat adresi veya sabit bir fiyat.

**2. Aynı coini farklı borsalarda ayrı pozisyon sayar.**
Binance'teki BTC'nizle MEXC'teki BTC'nizin maliyet tabanı ayrı tutulur.

---

## Özellikler

- **Çok kademeli fiyat keşfi** — Binance, MEXC, WhiteBIT, Gate.io ve zincir üstü
  (DexScreener). Hangi kaynağın hangi sırada deneneceğini siz belirlersiniz.
- **Sembole özel kaynak tanımı** — bir coin hiçbir kademede bulunamazsa kaynağı
  arayüzden sabitlersiniz. Kod değiştirmeye gerek yok.
- **DCA / maliyet ortalaması** — konsolide ortalama veya FIFO ile kısmi satış.
- **Transfer satış değildir** — bir coini borsadan kendi cüzdanınıza taşımak maliyet
  tabanınızı korur; nakit hareketi ve gerçekleşmiş kâr/zarar oluşturmaz. Her lot kendi
  maliyetiyle taşındığı için sonrasında FIFO doğru çalışmaya devam eder.
- **Kendi konumlarınız** — dört hazır borsanın yanına istediğiniz cüzdanı
  ekleyebilirsiniz (MetaMask, Ledger, başka bir borsa). Konumlar veriden türetilir:
  eklediğiniz her yer Kasa ekranında kendi sekmesini, nakit kutusunu ve rengini alır.
- **Ölü pozisyonlar için zarar yazımı** — delist edilmiş, çökmüş veya erişimi kaybolmuş
  coinler sıfırdan kapatılabilir. Maliyetin tamamı gerçekleşmiş zarara geçer ve
  **kasaya nakit eklenmez**; böylece toplam varlığınız gerçekte değersiz olan
  pozisyonlarla şişmeyi bırakır. Yazımlar ticaret sonucundan ayrı raporlanır;
  hem yazımlar hem transferler geri alınabilir.
- **Hedge takibi** — borsada açtığınız kaldıraçlı pozisyonu kaydeder, net
  maruziyetinizi ve korunma oranınızı gösterir, "fiyat %20 düşerse" senaryosunu
  hesaplar.
- **Kâr alma hedefleri** — hedef fiyat tanımlayıp tek tıkla satışı deftere işleme.
- **Yapay zekâ danışmanı** — Gemini API anahtarınızı girerseniz portföy analizi
  üretir. Anahtar girmezseniz yerel kural motoruna düşer.
- **PIN koruması** — SHA-256 + kuruluma özel salt, kurtarma anahtarı ile sıfırlama.
- **Net varlık arşivi** — borsalar geçmişi süresiz saklamaz ve pencereleri kayar
  (Binance ~2 yıl, MEXC 1 ay). Uygulama her çalıştığında portföyünüzün o günkü
  hâlini yerel bir SQLite arşivine yazar; böylece borsanın sildiği geçmiş sizde
  kalır ve zamanla gerçek bir net varlık eğrisi oluşur. Kayıt bulunmayan günler
  gizlenmez, açıkça bildirilir.
- **Borsa mutabakatı** — borsanızın web arayüzünden indirdiğiniz işlem geçmişi
  dosyalarını (Binance CSV, MEXC XLSX) defterinizle karşılaştırır ve farkları
  gösterir. Karşılaştırma **deftere hiçbir şey yazmaz**. Rapor, gerçek bir
  tutarsızlığı "dosya o kadar geriye gitmiyor" durumundan ayırt eder.
- **Mutabakat düzeltmesi** — dosyalardaki işlemler FIFO ile yürütülerek bugün
  elinizde kalması gereken lotlar **gerçek alım tarihleri ve gerçek fiyatlarıyla**
  yeniden kurulur. Hangi işlemi kaydetmeyi unuttuğunuzu hatırlamanız gerekmez;
  dosya zaten biliyor. Düzeltme **pozisyon başınadır**, açık onay ister ve geri
  alınabilir — toplu içe aktarma yoktur. Kapsamı kanıtlanamayan bir pozisyon için
  öneri verilmez. Geçmiş satışların o ana kadar hiçbir yerde görünmeyen
  gerçekleşmiş kâr/zararı da tek bir özet kayıt olarak deftere geçer; yoksa
  düzeltme pozisyonu ucuzlatır ve tabloyu olduğundan iyi gösterirdi.
- **Excel dışa aktarım**, günlük otomatik yedekleme, gizlilik modu.

---

## Kurulum

Gereken: **Python 3.10+** (Windows).

```bat
setup.bat
```

Sihirbaz Python sürümünü kontrol eder, bağımlılıkları kurar, doğrular ve veri
klasörünü hazırlar. Mevcut verilerinize dokunmaz.

Elle kurmayı tercih ederseniz:

```bat
python -m pip install -r requirements.txt
```

## Çalıştırma

```bat
Baslat.bat
```

Tarayıcınızda `http://localhost:8000` açılır. Kapatmak için `Durdur.bat`.

---

## İnternet gerekir mi?

**Evet, fiyatlar için.** Uygulama fiyatları borsalardan canlı çeker; grafikler
TradingView ve DexScreener üzerinden gelir.

Arayüz kütüphaneleri (Tailwind, Alpine.js, Chart.js, Lucide, yazı tipleri)
`app/static/vendor/` altında paketlenmiştir; yani CDN erişimi olmasa da arayüz
yüklenir. Bu, tam çevrimdışı çalışma anlamına gelmez — CDN bağımlılığını kaldırır.

---

## Verileriniz nerede?

```
data/
├── portfolio.json      İşlemleriniz, hedefleriniz, hedge kayıtlarınız
├── settings.json       PIN hash'i, API anahtarları, tercihler
├── archive.db          Günlük net varlık ve fiyat arşivi (SQLite)
├── backups/            Günlük otomatik yedekler
└── logs/               Uygulama günlükleri
```

Bu klasör `.gitignore` ile depo dışında tutulur. **Asla paylaşmayın.**

> **API anahtarları hakkında:** `settings.json` içindeki anahtarlar Base64 ile
> okunaksızlaştırılır — bu **şifreleme değildir**. Dosyaya erişebilen biri
> anahtarınızı okuyabilir. Anahtar yalnızca kendi makinenizde tutulacaksa
> yeterlidir; değilse anahtar kullanmayın.

---

## Testler

```bat
python -m pip install -r requirements-dev.txt
python -m pytest
```

407 test, yaklaşık 16 saniye. Testler **gerçek verinize ve ağa dokunmaz**:
veri yolları geçici bir klasöre yönlendirilir, tüm dış çağrılar taklit edilir ve
hiçbir test yapay zekâ API'sine istek atmaz.

---

## Mimari

```
app/
├── main.py           FastAPI sunucusu ve REST uçları
├── data_manager.py   Finansal motor: maliyet hesabı, FIFO, hedge, PIN, Excel
├── price_service.py  Çok kademeli fiyat keşfi ve kaynak kayıt defteri
├── archive.py        SQLite net varlık / fiyat arşivi (kritik yolda değildir)
├── reconcile.py      Borsa dışa aktarımı ↔ defter mutabakatı ve düzeltme
│                     önerileri (salt okunur; yazma data_manager'dan geçer)
├── ai_service.py     Gemini entegrasyonu + yerel yedek motor
└── static/           Alpine.js tek sayfa arayüz + paketlenmiş kütüphaneler
```

Derleme adımı yoktur. Node.js, npm veya bundler gerekmez.

---

## Sorumluluk reddi

Bu bir kişisel takip aracıdır, yatırım tavsiyesi değildir. Gösterilen fiyatlar
üçüncü taraf kaynaklardan gelir ve hatalı veya gecikmeli olabilir. Vergi veya
muhasebe amacıyla kullanmadan önce rakamları kendi kayıtlarınızla doğrulayın.

## Lisans

MIT — bkz. [LICENSE](LICENSE).
