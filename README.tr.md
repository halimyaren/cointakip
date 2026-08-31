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
- **Borsa mutabakatı** — borsanızın web arayüzünden indirdiğiniz dosyaları
  (Binance CSV, MEXC XLSX) defterinizle karşılaştırır ve farkları gösterir.
  Karşılaştırma **deftere hiçbir şey yazmaz**. Rapor, gerçek bir tutarsızlığı
  "dosya o kadar geriye gitmiyor" durumundan ayırt eder. Binance'in yalnızca
  alım-satımı değil **hesabın tam defteri** de okunur: airdrop, Launchpool,
  Convert, toz bakiyelerin BNB'ye eritilmesi ve cüzdanlar arası taşımalar işlem
  geçmişinde hiç görünmez, ve onlarsız kurulan bakiye yanlış çıkar.
- **Mutabakat düzeltmesi** — bu hareketler FIFO ile yürütülerek bugün elinizde
  kalması gereken lotlar **gerçek alım tarihleri ve gerçek fiyatlarıyla** yeniden
  kurulur. Hangi işlemi kaydetmeyi unuttuğunuzu hatırlamanız gerekmez; dosya
  zaten biliyor. Düzeltme **pozisyon başınadır**, açık onay ister ve geri
  alınabilir — toplu içe aktarma yoktur. Geçmiş satışların o ana kadar hiçbir
  yerde görünmeyen gerçekleşmiş kâr/zararı da tek bir özet kayıt olarak deftere
  geçer; yoksa düzeltme pozisyonu ucuzlatır ve tabloyu olduğundan iyi gösterirdi.
- **Kanıtsız düzeltme yok** — dosyalar hangi tarafın haklı olduğunu tek başına
  söyleyemez. Dışa aktarım penceresinden önce alınıp hiç satılmamış bir coin
  hiçbir iz bırakmaz; yeniden kurulum onu "yanlışlıkla girilmiş" sanıp silmeyi
  önerir. Bu yüzden her düzeltme, deftere bir şey yazmadan önce **borsadaki
  güncel bakiyenizi** sorar: rakam hesaplananla uyuşuyorsa defteriniz düzeltilir,
  defterinizle uyuşuyorsa eksik olan dosyadır ve **defterinize dokunulmaz**.
  Yeşil "uygulanabilir" rozeti yoktur; bir dosya onu hak edemez.
- **Cüzdan bağlantıları (salt okunur)** — cüzdanınızın **herkese açık adresini**
  girin, uygulama zinciri doğrudan okusun: dosya indirmek yok, borsa anahtarı yok.
  Cüzdan değil **zincir** okunduğu için MetaMask, Phantom, Ledger ve Trust iki
  adaptörle kapsanır: EVM (Ethereum, BNB Chain, Polygon, Arbitrum, Optimism, Base,
  Avalanche) ve Solana. Bağlantılar kod değil **yapılandırmadır**; yeni cüzdan
  eklemek bir form doldurmaktır. Okunamayan bağlantı "boş cüzdan" değil
  *bilinmiyor* diye raporlanır. **Uygulama asla kurtarma ifadesi veya özel anahtar
  istemez**, adres kutusuna yapıştırılırsa reddeder ve uyarır.
- **Elle token tanımlama** — Etherscan'ın ücretsiz planı otomatik token keşfini
  bazı zincirlerde açıyor, bazılarında açmıyor (BNB Chain, Base, Optimism ve
  Avalanche ücretli plan istiyor). Bunun için ödeme yapmak gerekmiyor: bakiye
  okumak zaten ücretsiz, ücretli olan yalnızca *hangi tokenlara sahip
  olduğunuzu bulmak*. Tokenın kontrat adresini yapıştırırsınız, sembolünü ve
  ondalık hanesini uygulama zincire sorar. Ücretsiz zincirlerde elle tanım
  otomatik keşfin **yerine geçmez, üstüne eklenir**.
- **Zincirdeki varlığı tek tıkla deftere ekleme** — cüzdanınızda durup
  defterinize girmemiş bir varlık için form coin, miktar ve konumla dolu açılır;
  **alım tarihini ve maliyeti siz girersiniz.** Otomatik yazma bilinçli olarak
  yok: zincir miktarı bilir, maliyeti bilmez ve sıfır maliyetle yazmak olmayan
  bir kâr uydurmak olurdu. Varlık başına bir kez yapılır, sonrasında normal bir
  pozisyon gibi Kasa toplamınızda durur.
- **Yanlış konum tespiti** — aynı varlık bir konumda "defterde var, zincirde
  yok", başka bir konumda "zincirde var, defterde yok" ve miktarlar yakınsa,
  bu iki ayrı eksiklik değil **yanlış rafa yazılmış tek bir varlıktır**. O
  satırlarda ekleme düğmesi bilerek gösterilmez — eklemek varlığı iki kez
  saydırırdı; yerine kaydın konumunu (ve sembolünü) düzelten bir düğme çıkar.
  Bu bir transfer değildir: varlık hiç taşınmadı, yalnızca yanlış yazılmıştı.
- **Tanınmayan token süzgeci** — istenmeden gönderilen tokenlar deftere
  kendiliğinden girmez. "Bilmiyorum" ile "sahte" ayrı tutulur: doğrulanmış
  liste tanımıyorsa satır katlanır, elde hiç hüküm yoksa satır **görünür kalır**
  ama ekleme önerilmez. İkisini birleştirmek, gerçekten sahip olduğunuz ama
  henüz deftere yazmadığınız varlıkları sizden saklardı. Son söz sizde:
  "Bu gerçek" / "spam" işareti kalıcıdır ve sembole değil **kontrat adresine**
  bağlanır.
- **Konuma göre sembol** — borsadaki varlık bir işlem çiftidir (`BNBUSDT`);
  aynı coin cüzdanınızda yalnızca `BNB`'dir, çünkü cüzdanda çift yoktur.
  Transfer artık sembolü hedefe göre yazıyor ve bir kez çalışan bir düzeltme
  eski transferlerin ürettiği kayıtları onarıyor. Yalnızca **ad** değişir;
  miktar, maliyet, tarih ve durum değişmez.
- **Seviyeli okuma notları** — bir okuma *tam*, *eksik* veya *başarısız*dır ve
  her not kendi seviyesini taşır. Bilgi notu (örneğin Solana'nın doğrulanmamış
  token bildirimi) artık gerçekten gelmemiş veriyle aynı alarmı üretmiyor;
  alarmı şişirmek gerçek sorunu gürültüde kaybettiriyordu.
- **Anahtar kasası** — sağlayıcı ve (ileride) borsa API anahtarları, PIN'inizden
  PBKDF2 ile türetilen bir anahtarla **şifrelenir**; çözme anahtarı diske hiç
  yazılmaz, yalnızca kasayı açtığınız oturum boyunca bellekte kalır. Siz açmadan
  uygulama hiçbir yere bağlanmaz. PIN'i değiştirmek kasayı yeniden mühürler;
  kurtarma anahtarıyla sıfırlamak ise kasayı temizler — çözülemeyen veriyi tutup
  "anahtarlarınız duruyor" izlenimi vermektense.
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

> **API anahtarları hakkında — bilinçli olarak iki ayrı mekanizma var:**
>
> - **Kasa anahtarları** (`vault` altındaki sağlayıcı ve borsa anahtarları)
>   PIN'inizden türetilen bir anahtarla **şifrelenir**. Çözme anahtarı hiçbir yere
>   yazılmaz; yalnızca kasa açıkken bellekte durur.
> - **Gemini / Telegram anahtarları** (`api_keys` altında) yalnızca Base64 ile
>   **okunaksızlaştırılır** — bu şifreleme değildir, dosyaya erişen okuyabilir.
>   Yalnızca kendi kotanızı harcayan bir anahtar için bu kabul edilebilir bir
>   takas; paraya dokunabilen bir anahtar için değildir, o yüzden onlar kasaya girer.

---

## Testler

```bat
python -m pip install -r requirements-dev.txt
python -m pytest
```

570 test, yaklaşık 25 saniye. Testler **gerçek verinize ve ağa dokunmaz**:
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
├── connections.py    Bağlantı kayıt defteri + zincir okuyucuları (EVM, Solana)
├── keyvault.py       API anahtarları için PIN'den türetilmiş şifreleme
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
