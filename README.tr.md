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
- **Net başa baş** — ortalama maliyet yalnızca *elinizde duran* lotların maliyetidir;
  daha önce alıp sattığınız coinlerden haberi yoktur. Ayrı bir sayı gerçekleşmiş
  sonucu da katarak o coinde yaptığınız her şeyin toplamının sıfıra geldiği fiyatı
  gösterir. Gerçek veride ikisi arasındaki fark iki katından fazlaydı. İkisi de
  gösterilir, biri diğerinin yerine geçmez; kayıtlı satışı olmayan coinler ayrıca
  etiketlenir — çünkü "ortalama maliyetle aynı" demek "geçmişinizi bilmiyoruz"
  demektir, "zarar etmediniz" değil.
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
  üretir. Anahtar girmezseniz yerel kural motoruna düşer. Her rapor arşivlenir ve
  yeni analiz, bir önceki raporu ve kapanmış işlemlerinizi görerek üretilir; böylece
  model önceki tavsiyesini uygulayıp uygulamadığınızı bilir. Nakit oranınız ve
  önereceği işlemin kaç dolar edeceği de kendisine verilir — bunlar olmadan,
  kasasının yarısı zaten nakit olan birine 220 dolarlık pozisyonun 55 dolarlık
  %25'ini satmayı günlerce tekrar önerebiliyordu. Koşullar değişmediyse aynı
  tavsiyeyi tekrarlamak doğrudur; tekrarı gizlemek değil.
- **Yapay zekâya piyasa çerçevesi** — BTC trendi (fiyat, 7/30/90 gün değişim, 50 ve
  200 günlük ortalamalara uzaklık, zirveden geri çekilme, oynaklık), ETH/BTC, piyasa
  genişliği, Korku & Açgözlülük endeksi ve BTC dominansı. Anahtar zorunlu değil;
  ücretsiz CoinGecko Demo anahtarı tercih edilen yoldur ve paylaşımlı dakikada 5-15
  çağrı sınırını 100'e çıkarır. Genişlik sıfır ek çağrıya mal olur — uygulamanın
  zaten indirdiği Binance ticker verisinden türetilir. Uygulama bilerek **hüküm
  üretmez**: "boğa piyasası" ya da "ölüm kesişimi" yazmaz, yalnızca ölçümleri ve her
  birinin yaşını verir. Bayat değerler yaşıyla etiketlenir, çok eskiler güncelmiş
  gibi sunulmak yerine hiç gönderilmez. Analiz piyasa verisini asla beklemez —
  kaynaklardan biri gerçek bir bağlantıda 7-22 saniye sürdü, o yüzden her şey arka
  planda toplanır ve önbellekten okunur.
- **Ayar yedekleri** — her farklı ayar hâli, kaydetmeden hem önce hem sonra
  saklanır ve arayüzden geri yüklenebilir. Bunun sebebi somut: 5 Eylül 2026'da ayar
  dosyası varsayılanlarla üzerine yazıldı ve bir kullanıcının API anahtarları, cüzdan
  bağlantıları ve PIN'i kalıcı olarak kayboldu; o tarihe kadar yalnızca defter
  yedekleniyordu. Defter borsa kayıtlarından yeniden kurulabilir, ama borsa API gizli
  anahtarı bir kez gösterilir ve bir daha gösterilmez.
- **PIN koruması** — SHA-256 + kuruluma özel salt, kurtarma anahtarı ile sıfırlama.
- **Net varlık arşivi** — borsalar geçmişi süresiz saklamaz ve pencereleri kayar
  (Binance ~2 yıl, MEXC 1 ay). Uygulama her çalıştığında portföyünüzün o günkü
  hâlini yerel bir SQLite arşivine yazar; böylece borsanın sildiği geçmiş sizde
  kalır ve zamanla gerçek bir net varlık eğrisi oluşur. Kayıt bulunmayan günler
  gizlenmez, açıkça bildirilir.
- **Borsada yaptığınız işlemler yakalanır** — uygulama borsanın işlem geçmişini
  kendisi okur ve yeni işlemleri İşlem Defteri'ndeki bir gelen kutusuna koyar.
  **Deftere kendiliğinden hiçbir şey yazılmaz**: kısmi satışta maliyet yöntemi
  (Konsolide Ortalama / FIFO) sonucu değiştirir ve o karar kullanıcınındır. Her
  satır borsanın kendi işlem numarasını taşır, yani aynı işlem iki kez
  işlenemez. Defterde benzeyen kapanmış bir kayıt varsa (aynı gün, benzer
  miktar) "elle işlenmiş **olabilir**" uyarısı çıkar — elle girilen kayıtlar
  işlem numarası taşımadığı için kesin eşleştirme mümkün değildir ve uyarı bunu
  saklamaz.
- **Toz dönüşümü bir alım-satım değildir** — Binance'in "Küçük Bakiyeleri
  Dönüştür" özelliği işlem geçmişinde hiç görünmez, ayrı bir uçta durur. Gerçek
  veride ölçüldü: **17.03 USDT**'lik bir dönüşüm **434.54 USD** maliyet tabanını
  silecekti — deftere hiç girmeyen ~418 USD'lik gerçekleşmiş zarar ve canlı
  fiyatla değerlenmeye devam eden 7 açık pozisyon. "Küçük bakiye" piyasa değeri
  için küçüktür, maliyet tabanı için değil. MEXC böyle bir uç sunmuyor ve
  uygulama bunu kapatıyormuş gibi yapmak yerine açıkça söylüyor.
- **Earn geliri ve para hareketleri de okunur** — bakiyeyi değiştiren tek şey
  alım-satım değil. Simple Earn faizi (esnek ve vadeli), para yatırma ve para
  çekme ayrı uçlardan okunur. Earn geliri deftere **alındığı günün piyasa
  fiyatıyla** yeni bir açık lot olarak eklenir; böylece gelir elde edildiği
  andaki değeriyle maliyet tabanına girer ve sonraki satışta yalnızca aradaki
  fark kâr sayılır. Para giriş/çıkışı ise deftere **yazılamaz**: gelen coin çoğu
  zaman başka bir konumdan gelen transferdir ve maliyeti zaten defterde durur —
  onu "alım" saymak, maliyeti bilinmeyen bir lot uydurmak olurdu.
- **Açıklanamayan bakiye değişimi gizlenmez** — bakiye değişip de bunu açıklayan
  bir olay bulunamadığında hangi varlığın ne kadar değiştiği söylenir, susulmaz.
  Bir uyarının değeri ne kadar sık **haklı** olduğuyla ölçülür: Earn her gün
  faiz ödediği için o akış okunmasaydı bu uyarı birkaç günde gürültüye boğulur
  ve okunmaz hâle gelirdi. Geriye kalan başlıca boşluk vadeli/marj hesap
  transferleridir. Bir sembolün ilk taraması yalnızca başlangıç noktası kurar:
  bu özellik bundan sonrasını yakalar, geçmişi geriye dönük getirmez.
- **Borsa mutabakatı** — borsanızın web arayüzünden indirdiğiniz dosyaları
  (Binance CSV, MEXC XLSX) defterinizle karşılaştırır ve farkları gösterir.
  Karşılaştırma **deftere hiçbir şey yazmaz**. Rapor, gerçek bir tutarsızlığı
  "dosya o kadar geriye gitmiyor" durumundan ayırt eder. Binance'in yalnızca
  alım-satımı değil **hesabın tam defteri** de okunur: airdrop, Launchpool,
  Convert, toz bakiyelerin BNB'ye eritilmesi ve cüzdanlar arası taşımalar işlem
  geçmişinde hiç görünmez, ve onlarsız kurulan bakiye yanlış çıkar.
- **Geçmişin API'den doldurulması** — indirilen dosyalar hiçbir API'nin ulaşamadığı
  derinliğe iner (Binance'inkiler 2023'e kadar), ama **eskirler**: ağustosta
  indirilen dosya eylülü bilmez ve mutabakat o boşluğu "defteriniz yanlış" gibi
  gösterir. Tek bir düğme borsanın API'sinden işlemleri, Earn ödüllerini ve para
  hareketlerini okuyup **yalnızca dosyaların bittiği yerden sonrasını** doldurur;
  böylece aynı işlem iki kez sayılmaz. Çakışan dönemde dosya esas kalır çünkü daha
  zengindir — Convert, airdrop ve cüzdan taşımalarının API'de karşılığı yoktur.
  Sonuç: dosyaları her ay değil, bir kez indirirsiniz. Bu işlem de deftere hiçbir
  şey yazmaz ve okunamayan bir pencere sessizce atlanmaz, uyarı olarak bildirilir.
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
- **Borsa API bağlantıları (salt okunur)** — borsadaki spot bakiyeniz doğrudan
  okunur; her ay dosya indirmeniz gerekmez. Adaptör borsa başına değil
  **imzalama ailesi** başına yazılıyor, borsa `settings.json` içinde bir profil
  olarak duruyor: yeni bir borsa eklemek form doldurmak. Şu an bir aile var
  (Binance tipi HMAC-SHA256) ve Binance ile MEXC'i birlikte kapsıyor; farklı
  imzalama şeması olan bir borsa yine kod ister ve bu **açıkça söyleniyor**.
  API anahtarı cüzdan adresinden farklı olarak gerçek bir sırdır: şifreli
  kasada saklanır, `settings.json`'a düz metin yazılmaz ve **yazma yetkisi
  taşıyan anahtar kabul edilmez** — izinler saklanmadan ÖNCE denetlenir.
  Denetlenemiyorsa (MEXC'in API'si anahtar yetkilerini bildirmiyor) bu
  gizlenmez; hesabın yetkisini anahtarın yetkisi sayıp size veremeyeceğimiz
  bir güvenceyi vermek yerine açık onayınız istenir.
- **Farkın parasal karşılığı** — karşılaştırma tablosunda her miktarın altında
  USD tutarı yazar ve satırlar **farkın büyüklüğüne göre** sıralanır: soru
  "hangi fark var?" değil "hangi fark önemli?". Belirlediğiniz eşiğin altındaki
  farklar katlanır (sayısı ve toplamı görünür, tek tıkla açılır), çünkü borsa
  bağlantısından sonra tablo ücret kırıntılarıyla dolar. Fiyatı bulunamayan
  satırda `—` yazar ve o satır **asla katlanmaz**: bilinmeyen değer sıfır değer
  değildir.
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
- **Vergi-hazır dışa aktarım — rapor değil, dışa aktarım.** Mali müşavirinize
  vereceğiniz yıllık dosya: her gerçekleşmiş olay bir satır; alış ve çıkış
  tarihi, miktar, birim fiyatlar, komisyon ve gerçekleşmiş K/Z ile. **Vergi
  hesaplamaz** — matrah, oran, mahsup yoktur; hesaplanmış bir yükümlülük
  üretmek sorumluluk doğurur ve Türkiye'de kripto vergilendirmesi oturmuş
  değildir. Tutarlar **USD** kalır: TRY kuru uygulamak "hangi kurum, hangi kur,
  tatilde hangi gün" kararlarını vermek demektir; bunlar uygulamanın sizin
  adınıza veremeyeceği kararlardır ve yanlış kur doğru veriden yanlış beyan
  üretir. Dosyayı denetlenebilir yapan şey **hiçbir satırın sessizce
  düşmemesi**: defterdeki her kayıt tam olarak dört kümeden birine girer —
  gerçekleşmiş, eksik veri, kapsam dışı, hâlâ açık — ve toplamları defteri
  verir. Çıkış fiyatı girilmeden kapatılmış pozisyonlar (büyük ihtimalle
  satılmış ama kaydedilmemiş) kendi sayfasına düşer ve **indirmeden önce**
  uyarı olarak görünür; sessizce kaybolsalardı hem kazancınızı hem zararınızı
  eksik gösterirlerdi. Transferler ve mutabakat kapanışları da, neden bir elden
  çıkarma sayılmadıkları yazılarak listelenir.
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

801 test, yaklaşık 55 saniye. Testler **gerçek verinize ve ağa dokunmaz**:
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
├── api_history.py    Mutabakatın boşluğunu borsa API'sinden doldurur; yalnızca
│                     indirilen dosyaların kapsamadığı dönem için
│                     önerileri (salt okunur; yazma data_manager'dan geçer)
├── connections.py    Bağlantı kayıt defteri + zincir okuyucuları (EVM, Solana)
├── exchanges.py      Borsa API profilleri + salt-okunur bakiye, işlem, toz
│                     dönüşümü, Earn ödülü ve para hareketi okuyucuları;
│                     imza ailesi başına yazılır (yalnızca GET, emir vermez)
├── trade_sync.py     Borsa işlemlerini, toz dönüşümlerini, Earn gelirini ve
│                     para hareketlerini onay kutusuna düşürür; deftere
│                     kendiliğinden asla yazmaz
├── tax_export.py     Vergi-hazır dışa aktarım (salt okunur; vergi hesaplamaz)
├── keyvault.py       API anahtarları için PIN'den türetilmiş şifreleme
├── ai_service.py     Gemini entegrasyonu + yerel yedek motor
├── market_service.py Yapay zekâ için piyasa çerçevesi (arka planda, yaş bilgisiyle)
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
