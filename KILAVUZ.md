# CoinTakip — Kullanım Kılavuzu

Bu belge uygulamanın **nasıl kullanılacağını** anlatır. Ne olduğunu ve neden
yapıldığını öğrenmek için [README.tr.md](README.tr.md) dosyasına bakın.

---

## İçindekiler

1. [Kurulum ve ilk açılış](#1-kurulum-ve-ilk-açılış)
2. [Temel kavramlar](#2-temel-kavramlar) — lot, pozisyon, konum, maliyet tabanı
3. [Alım ve satış girmek](#3-alım-ve-satış-girmek)
4. [Fiyat bulunamayınca](#4-fiyat-bulunamayınca)
5. [Kasa ve konumlar](#5-kasa-ve-konumlar)
6. [Transfer — coini başka yere taşımak](#6-transfer--coini-başka-yere-taşımak)
7. [Zarar yazımı — ölmüş pozisyonu kapatmak](#7-zarar-yazımı--ölmüş-pozisyonu-kapatmak)
8. [Kâr alma hedefleri](#8-kâr-alma-hedefleri)
9. [Hedge takibi](#9-hedge-takibi)
10. [Borsa mutabakatı ve düzeltme](#10-borsa-mutabakatı-ve-düzeltme)
11. [Cüzdan bağlantıları](#11-cüzdan-bağlantıları) — MetaMask, Phantom ve diğerleri
12. [Arşiv ve net varlık eğrisi](#12-arşiv-ve-net-varlık-eğrisi)
13. [Vergi-hazır dışa aktarım](#13-vergi-hazır-dışa-aktarım) — mali müşavirinize vereceğiniz dosya
14. [Güvenlik: PIN ve gizlilik modu](#14-güvenlik-pin-ve-gizlilik-modu)
15. [Yedekleme ve geri yükleme](#15-yedekleme-ve-geri-yükleme)
16. [Sık sorulanlar](#16-sık-sorulanlar)

---

## 1. Kurulum ve ilk açılış

```bat
setup.bat        :: bağımlılıkları kurar, veri klasörünü hazırlar
Baslat.bat       :: uygulamayı başlatır
Durdur.bat       :: uygulamayı kapatır
```

Tarayıcınızda `http://localhost:8000` açılır. Uygulama **yalnızca sizin
bilgisayarınızda** çalışır; verileriniz `data/` klasöründeki düz dosyalarda durur
ve hiçbir yere gönderilmez.

İlk açılışta portföy boştur. İki yoldan doldurabilirsiniz:

- **Elle**, işlem işlem girerek (bölüm 3),
- ya da elinizde borsa dışa aktarım dosyaları varsa **mutabakat düzeltmesiyle**
  (bölüm 10) — bu yol gerçek tarihleri ve fiyatları getirdiği için daha doğrudur.

---

## 2. Temel kavramlar

Bu dört kavramı anlarsanız uygulamanın geri kalanı kendiliğinden anlaşılır.

### Lot (alım)

**Bir lot = tek bir satın alma işlemi**, kendi tarihi ve kendi fiyatıyla.

3 kere ARB aldıysanız 3 lotunuz vardır:

```
2025-02-25    209.58 adet @ $0.3920
2025-03-04    264.00 adet @ $0.3825
2026-02-05    800.90 adet @ $0.1261
```

Uygulama bunları **tek bir ortalamaya indirmez.** Sebebi: kısmi satış yaptığınızda
hangi coini sattığınız kârınızı değiştirir. FIFO ("ilk giren ilk çıkar") yöntemi
en eski lottan başlar. Hepsi tek ortalamaya inseydi bu hesap yapılamazdı.

Arayüzde "4 alım" yazan yerler bunu kasteder.

### Pozisyon

**Pozisyon = bir varlığın belirli bir konumdaki tüm lotları.** Örneğin
`ARB @ BINANCE` bir pozisyondur.

Aynı coin farklı yerlerdeyse **ayrı pozisyonlardır**: Binance'teki BTC'niz ile
MEXC'teki BTC'niz ayrı maliyet tabanı taşır. Bu bilinçli bir tercih — çoğu takipçi
hepsini toplayıp tek ortalama gösterir ve borsa bazlı kârınızı göremezsiniz.

### Konum

**Konum = coinin fiilen durduğu yer.** Kutudan çıkan dördü: `BINANCE`, `MEXC`,
`GATE.IO`, `DEX`.

Ama liste bunlarla sınırlı değil. Bir transferde hedef olarak `METAMASK` yazarsanız
o konum sistemde doğar: Kasa ekranında kendi sekmesini, kendi nakit kutusunu ve
kendi rengini alır. Konumlar sabit bir listeden değil, **verinizden** türetilir.

### Maliyet tabanı

**Bir coine ödediğiniz ortalama fiyat.** Kâr/zarar hesabının temeli budur, bu
yüzden uygulama onu korumaya öncelik verir:

- Transfer maliyet tabanını **korur** (satış değildir).
- Zarar yazımı maliyeti **zarara çevirir** (nakit üretmez).
- Mutabakat düzeltmesi maliyeti **borsa kaydıyla değiştirir** (yalnızca siz onaylarsanız).

---

## 3. Alım ve satış girmek

Üst çubuktaki **+ İşlem Ekle** düğmesi.

| Alan | Ne yazılır |
|:---|:---|
| Coin | Sembol (`BTC`, `ARB`). `USDT` eki gerekmez, kendisi ekler. |
| Konum | Borsa veya cüzdan. Listede yoksa yazabilirsiniz. |
| Miktar | Elinize **geçen** miktar. Komisyon coinden alındıysa düşülmüş hâli. |
| Fiyat | Birim alış fiyatı (USD). |
| Tarih | Gerçek alım tarihi. Maliyet hesabını değil ama FIFO sırasını etkiler. |
| Kategori | Raporlarda gruplamak için. |

**Satış için** coin satırındaki 💰 düğmesini kullanın; ayrı bir "satış işlemi"
girmeyin. Satış, mevcut lotları FIFO ya da konsolide ortalamayla tüketir ve
gerçekleşmiş K/Z üretir.

---

## 4. Fiyat bulunamayınca

Uygulama fiyatı sırayla Binance → MEXC → WhiteBIT → Gate.io → zincir üstü
(DexScreener) kaynaklarında arar. Hiçbirinde bulamazsa fiyat yerine **`—`**
gösterir.

> Bu bilinçlidir. Çoğu takipçi bulamadığında ya boş gösterir ya da aynı sembolü
> taşıyan **başka** bir tokenın fiyatını getirir. İkincisi sessiz ve tehlikelidir.

`—` gördüğünüzde coin satırından **kaynak tanımlayın**. Üç seçenek:

1. **Borsa + market adı** — coin küçük bir borsada işlem görüyorsa.
2. **Zincir üstü kontrat adresi** — en güvenilir yöntem. Sembol adları zincirler
   arasında benzersiz değildir; kontrat adresi benzersizdir.
3. **Sabit fiyat** — delist olmuş ve artık işlem görmeyen coinler için.

> **Uyarı:** Sembol adına bakarak yapılan zincir üstü eşleşme işaretlenir. O
> işareti görürseniz kontrat adresini elle girin.

---

## 5. Kasa ve konumlar

**Kasa** sekmesi varlıklarınızı konuma göre ayırır. Her konumun kendi sekmesi ve
kendi nakit kutusu vardır.

**Nakit cüzdanları yönet** düğmesiyle her konumdaki serbest USDT'nizi girersiniz.
Toplam varlığınız = pozisyonların güncel değeri + tüm konumlardaki nakit.

Yeni konum eklemenin iki yolu var: cüzdan modalından doğrudan eklemek, ya da bir
transferde hedef olarak yazmak. İkisi de aynı listeyi besler.

---

## 6. Transfer — coini başka yere taşımak

Coin satırındaki **🔀 Transfer** düğmesi.

**Transfer satış değildir.** Sistem şunu yapmaz: nakit eklemez, gerçekleşmiş
kâr/zarar üretmez, maliyet tabanınızı bozmaz.

Ne yapar: kaynak lotları FIFO sırasıyla tüketir ve her birini hedefte **kendi
maliyetiyle** yeniden açar. Böylece transferden sonra FIFO doğru çalışmaya
devam eder.

**Ağ ücreti** alanı isteğe bağlıdır. Yazarsanız o kadar coin gerçekten kaybolmuş
sayılır ve taşıdığı maliyet ayrı bir zarar kaydına geçer.

**Sembol hedefe göre yazılır.** Borsada tuttuğunuz şey bir işlem çiftidir
(`BNBUSDT`), cüzdanınızda duran şey ise yalın coindir (`BNB`) — cüzdanda USDT
çifti diye bir şey yoktur. Bu yüzden Binance'ten MetaMask'a taşıdığınızda ad
`BNB` olur, tersinde `BNBUSDT`'ye döner. Miktar, maliyet ve tarih değişmez;
değişen yalnızca addır.

Transferler **İşlem Defteri**nden geri alınabilir. Ancak transfer ettiğiniz varlığı
hedefte sattıysanız geri alma reddedilir — önce satışı geri almanız gerekir.

---

## 7. Zarar yazımı — ölmüş pozisyonu kapatmak

Coin satırındaki **🪦 Zarar Yaz** düğmesi.

Delist edilmiş, projesi çökmüş veya cüzdanına erişemediğiniz coinler için. Pozisyon
sıfırdan kapatılır: **maliyetin tamamı gerçekleşmiş zarara geçer ve kasaya nakit
EKLENMEZ.**

Bu ayrım önemli. Böyle bir pozisyonu "sattım" diye kapatırsanız sistem size olmayan
bir nakit gösterir. Zarar yazımı bunu yapmaz — sadece toplam varlığınızın gerçekte
değersiz olan şeylerle şişmesini durdurur.

Beş gerekçeden birini seçersiniz: delist, proje çöktü, erişim kaybı, değersizleşti,
diğer. Gerekçe raporlarda saklanır ve yazımlar **alım-satım sonucundan ayrı**
gösterilir — çünkü kötü bir alım-satım kararı ile ölmüş bir coini silmek aynı şey
değildir.

Yazımlar da geri alınabilir.

---

## 8. Kâr alma hedefleri

Coin satırından hedef fiyat tanımlarsınız. Fiyat hedefe ulaşınca satır işaretlenir
ve tek tıkla satışı deftere işleyebilirsiniz.

Satışın ne kadarının yapılacağını yüzde olarak belirleyebilirsiniz (varsayılan %100).
Kısmi satışta hangi lotların tükeneceğini **maliyet yöntemi** belirler:
konsolide ortalama veya FIFO.

> Sistem sizin adınıza borsaya emir göndermez. Emri borsada siz verirsiniz;
> buradaki düğme yalnızca defteri günceller.

---

## 9. Hedge takibi

Borsada açtığınız kaldıraçlı pozisyonu kaydeder. Spot alımdan ayrı bir veri
modelidir (yön, kaldıraç, marj, giriş fiyatı) ve maliyet tabanı hesabına karışmaz.

Gösterdikleri:

- **Net maruziyet** — spot varlığınız eksi short pozisyonunuz.
- **Korunma oranı** — varlığınızın yüzde kaçı korunuyor.
- **Senaryo** — "fiyat %20 düşerse ne olur?"

Pozisyonu iki giriş biçiminden biriyle tanımlarsınız: "100$ teminatla 2X" ya da
doğrudan coin miktarı.

---

## 10. Borsa mutabakatı ve düzeltme

**Grafikler → 🔍 Borsa Mutabakatı**

Bu ekranın var olma sebebi: borsalar geçmişi süresiz saklamaz, sizin elle girdiğiniz
rakamlar ise hafızaya dayanır. Bir işlemi kaydetmeyi unutmak olağandır.

### Adım 1 — Dosyaları indirin

| Borsa | Nereden | Biçim | Ne kadar geriye |
|:---|:---|:---|:---|
| Binance | Order History → Export | CSV | ~2023'e kadar |
| MEXC | Export History | XLSX | 540 gün |

Binance için **Spot Trade History**, ayrıca varsa **Deposit History**,
**Withdraw History** ve — aşağıdaki uyarıyı okuyun — **Transaction History**.
MEXC için **Trade History** ve **Statement**.

> "Order History" ile "Trade History" farklıdır: ilki verdiğiniz emirleri, ikincisi
> gerçekleşen dolumları içerir. Sistem doğru olanı seçer, ikisini de koyabilirsiniz.

> ### ⚠️ Binance'te hesap defterini de indirin
>
> **Wallet → Transaction History → Export.** Alım-satım dosyası hesabınızın
> **tamamı değildir.** Coin hesabınıza yalnızca satın alarak girmez:
>
> - **Earn / Launchpool airdrop'ları** — her gün damla damla gelir
> - **Convert** — "0.005 BTC'yi USDT'ye çevir" bir spot emri değildir
> - **Small Assets Exchange BNB** — toz bakiyelerin BNB'ye eritilmesi
> - **Cüzdanlar arası taşımalar** — vadeli hesap, Funding, üçüncü taraf cüzdan
>
> Bunların **hiçbiri** Spot Trade History'de görünmez. Hesap defteri olmadan
> hesaplanan bakiye yanlış çıkar. Gerçek veriyle ölçüldü: bu dosya okunmadığında
> 21 önerinin 10'u hatalıydı.
>
> Bu dosyayı koyduğunuzda alımlarınız **iki kez sayılmaz** — sistem hangi
> hareketin hangi dosyadan geleceğini bilir.

### Adım 2 — Klasöre koyun

Dosyaları proje kökündeki **`borsa_exports/`** klasörüne atın. Alt klasör
açabilirsiniz; **dosya adlarını değiştirmeyin** (sistem adlarından tanıyor).

Bu klasör `.gitignore` kapsamındadır — işlem geçmişiniz asla yayınlanmaz.

### Adım 3 — Karşılaştırmayı okuyun

Üstteki tablo borsanın kaydı ile defterinizi yan yana koyar. **Bu tablo deftere
hiçbir şey yazmaz.**

Durum etiketleri:

| Etiket | Anlamı |
|:---|:---|
| **Fark var** | Gerçek bir tutarsızlık. Bakılması gereken satır budur. |
| **Sadece borsada** | Borsada var, defterinizde yok. |
| **Sadece defterde** | Defterinizde var, dosyalarda hiç yok. |
| **Kapsam dışı** | Dosya o kadar geriye gitmiyor. **Bu bir hata değildir.** |
| **Borsadan çekilmiş** | Coin cüzdanınıza taşınmış olabilir; fark gerçek olmayabilir. |
| **Konum kapsanmıyor** | O konum için dosya yok (örn. MetaMask). Mutabakat yapılamaz. |
| **Eşleşiyor** | Tutuyor. |
| **Nakit birimi** | USDT gibi stabilcoinler pozisyon değil nakit sayılır. |

> Rapor, gerçek bir tutarsızlığı "dosya o kadar geriye gitmiyor" durumundan
> **ayırt eder.** Kapsam dışı bir satırı hata sanıp kovalamayın.

### Adım 4 — Düzeltme önerileri

Aşağıdaki **🛠️ Düzeltme Önerileri** bölümünde **Önerileri Hesapla**'ya basın.

Sistem dosyadaki işlemleri FIFO ile yürütüp bugün elinizde kalması gereken lotları
**gerçek alım tarihleri ve gerçek fiyatlarıyla** yeniden kurar. Hangi işlemi
kaydetmeyi unuttuğunuzu hatırlamanız gerekmez — dosya zaten biliyor.

Öneri durumları:

| Etiket | Ne yapmalısınız |
|:---|:---|
| **Bakiye sorulacak** | Öneri hesaplandı. Uygulamadan önce borsadaki gerçek bakiyeniz sorulacak. |
| **Önce uyarıyı oku** | Öneri hesaplandı ama bilmeniz gereken bir şey var — coin çekmiş olmanız ya da önerinin pozisyonu küçültmesi gibi. Satırdaki ⚠ cümlesini okuyun. |
| **Kapsam yetersiz** | Öneri **verilmiyor**. Uydurmaktansa susmayı tercih ediyor. |
| **Zaten uyumlu** | Yapılacak bir şey yok. |

**İncele ve Düzelt** düğmesi bir onay penceresi açar: defterdekiyle borsanın
dediği yan yana, ne olacağı ve neye dikkat etmeniz gerektiği ayrı ayrı, deftere
yazılacak alımların tam dökümü — ve son adımda borsadaki gerçek bakiyeniz.

### Adım 5 — Borsadaki gerçek bakiyeyi girin

Onay penceresinin son bölümü sizden **borsanızın cüzdan ekranındaki güncel
bakiyeyi** ister. Bu adım atlanamaz.

**Neden?** Çünkü dosyalar hangi tarafın haklı olduğunu tek başına söyleyemez.
Dışa aktarım pencerenizden **önce** alıp **hiç satmadığınız** bir coin hiçbir
dosyada iz bırakmaz: ne alışı görünür, ne satışı. Sistem onu göremediği için
"fazladan girilmiş" sanar ve silmeyi önerir — oysa coin gerçekten sizdedir.

Girdiğiniz rakam kararı verir:

| Girdiğiniz bakiye | Sonuç |
|:---|:---|
| **Hesaplananla** uyuşuyor | Defteriniz eksik/yanlış. Düzeltme uygulanır. |
| **Defterinizle** uyuşuyor | Eksik olan dosya. **Defterinize dokunulmaz.** |
| İkisiyle de uyuşmuyor | Üçüncü bir kaynak eksik (başka cüzdan, kilitli bakiye, kapsam dışı borsa). Uygulanmaz. |

> Kutu bilerek **boş** açılır ve öneriyle doldurulmaz. Doldurulsaydı borsaya
> bakmadan onaylardınız ve doğrulama bir tiyatroya dönerdi.

### Düzeltme neyi değiştirir?

- Elle girdiğiniz kayıtlar **silinmez, kapatılır**. Her düzeltme geri alınabilir.
- Yerlerine borsa kaydından kurulmuş, gerçek tarih ve fiyatlı alımlar gelir.
- **Nakit bakiyeniz değişmez.** Bu bir alım satım değil, kayıt düzeltmesidir.
- Geçmişte yaptığınız satışların gerçekleşmiş kâr/zararı da deftere geçer.

Son madde önemli. FIFO'da hayatta kalan lotlar en **son** alımlardır; düşen bir
coinde bunlar en ucuz alımlardır. Yalnızca açık lotları düzeltmek pozisyonu
ucuzlatır ve sizi **olduğunuzdan kârlı** gösterirdi. Bu yüzden kapanmış
alım-satımların sonucu da tek bir özet kayıt olarak yazılır.

Pozisyonun defterinizde zaten satış kaydı varsa bu K/Z **yazılmaz** — iki kez
saymak tabloyu bozardı.

### Bu iş her ay tekrarlanacak mı?

**Hayır, bir kereliktir.** Dosyalar borsa API'sinin asla veremeyeceği derinliği
(2023'e kadar) getirir. O geçmiş bir kere alınıp arşive girdikten sonra bir daha
gerekmez.

> ⚠️ **Excel'inizi veya eski kayıtlarınızı atmayın.** Borsa dosyası yalnızca
> kapsadığı aralıkta kesindir. 2023-02 öncesi Binance, 2024-10 öncesi MEXC ve tüm
> cüzdan/DEX varlıklarınız için tek kaynak hâlâ sizin kendi kaydınız.

---

## 11. Cüzdan bağlantıları

**Grafikler → 🔗 Cüzdan Bağlantıları**

Cüzdanınızın **herkese açık adresini** girersiniz; sistem zincirden okur ve
defterinizle karşılaştırır. Dosya indirmek gerekmez.

> ### 🛡️ Önce bunu okuyun
>
> **CoinTakip asla kurtarma ifadesi (seed phrase) veya özel anahtar istemez.**
> Yalnızca herkese açık adresinizi ister — o adres zaten blok gezginlerinde
> herkesin görebildiği bir bilgidir ve okuma yapı gereği salt okunurdur; adresle
> kimse paranıza dokunamaz.
>
> Size kurtarma ifadenizi veya özel anahtarınızı soran **her ekran, her site ve
> her kişi dolandırıcıdır.** Bu, CoinTakip için de geçerlidir: ileride böyle bir
> şey soran bir ekran görürseniz o CoinTakip değildir. Adres kutusuna yanlışlıkla
> böyle bir şey yapıştırırsanız sistem kabul etmez ve sizi uyarır.

### Cüzdan değil, zincir okunur

MetaMask, Phantom, Ledger, Trust, Rabby — hangisini kullandığınız **fark etmez.**
Bunların bağlanılacak bir API'si yoktur; anahtarı tutan programlardır, varlık ise
zincirde durur. Bu yüzden okuyucu cüzdan başına değil zincir başına çalışır:

| Zincir ailesi | Kapsadığı |
|:---|:---|
| **EVM** | Ethereum, BNB Chain, Polygon, Arbitrum, Optimism, Base, Avalanche |
| **Solana** | Phantom, Solflare, Backpack ve diğer Solana cüzdanları |

Bir bağlantıyı benzersiz kılan şey **adrestir** — konum adı değil, konum+zincir
çifti de değil. Bir cüzdan uygulaması bir kimlik değil bir **kaptır**: içinde
istediğiniz kadar hesap olur (Phantom'da Hesap 2, Hesap 3…) ve her hesap birden
çok zincirde yaşar. Hepsini ayrı ayrı ekleyin; hiçbiri diğerinin yerine geçmez,
hepsi aynı konumun altında yan yana durur.

- **MetaMask**: aynı `0x` adresi tüm EVM zincirlerinde geçerlidir, ama her
  zincirdeki bakiyeniz ayrıdır. MetaMask'te ağ kutusundan Ethereum → Polygon →
  Arbitrum diye geçtiğinizde listenin değişmesinin sebebi budur. Varlık
  tuttuğunuz **her zincir için ayrı bir bağlantı** ekleyin: konum aynı, adres
  aynı, yalnızca zincir farklı. Boş zinciri eklemenin faydası yoktur.
- **Phantom**: Solana ve Ethereum adresleriniz **farklıdır**. Her birini kendi
  zinciriyle, kendi adresiyle ekleyin.

Kaydettikten sonra konum kutusu temizlenmez — zinciri değiştirip yeni adresi
girip tekrar kaydetmeniz yeterlidir.

### Adım adım

1. Cüzdanınızdan **adresi kopyalayın** (MetaMask'te hesap adına tıklayınca
   kopyalanır; Phantom'da aynı şekilde).
2. **Konum** kutusuna o cüzdanı defterinizde ne diye adlandırdığınızı yazın —
   örneğin `METAMASK`. Açılır listede yalnızca defterinizde **hâlihazırda geçen**
   konumlar görünür; yeni bir isim yazmanız tamamen normaldir.
3. **Zincir**'i seçin, adresi yapıştırın.
4. **Önce Dene** deyin. Kaç varlık okunduğunu söyler; kaydetmeden görürsünüz.
5. **Kaydet**, sonra **Bakiyeleri Getir**.

### Anahtar kasası

Ekranın üstündeki kasa, gizli tutulması gereken anahtarları saklar. Anahtar
**PIN'inizden türetilen bir anahtarla şifrelenir**; çözme anahtarı diskte hiçbir
yerde durmaz, yalnızca kasayı açtığınız oturum boyunca bellekte kalır. Uygulama
siz açmadan hiçbir yere bağlanmaz.

Bunun için önce **Ayarlar → Güvenlik** bölümünden bir PIN tanımlamış olmanız
gerekir.

> ⚠️ **PIN'i kurtarma anahtarıyla sıfırlarsanız veya PIN korumasını kapatırsanız
> kasa temizlenir.** Sebebi şu: eski PIN olmadan içerik bir daha çözülemez ve
> çözülemeyen şifreli veriyi saklamak size "anahtarım duruyor" yanılgısı verirdi.
> PIN'i normal yoldan *değiştirirseniz* anahtarlarınız korunur.

### Etherscan anahtarı ne işe yarar?

**Solana için hiçbir şey gerekmez** — bakiyeler doğrudan okunur.

EVM zincirlerinde ise anahtarsız yalnızca **yerel coin** bakiyesi okunabilir
(ETH, BNB, POL…). Hangi tokenlara sahip olduğunuzu bulmak zincir taraması
gerektirir ve bunun için `etherscan.io` üzerinden alınan **ücretsiz** bir anahtar
gerekir.

**Anahtarı girmek için:** Anahtar Kasası panelinde PIN'inizi yazıp *Kasayı Aç*
deyin; kasa açılınca alttaki *Etherscan API anahtarı* kutusu belirir. Anahtarı
yapıştırıp *Kaydet*'e basın, sonra *Bakiyeleri Getir* deyin. Anahtar şifreli
saklanır ama çözme anahtarı diskte durmadığı için **uygulamayı her açtığınızda
kasayı yeniden açmanız gerekir.**

#### Tek anahtar her zincirde geçerli, ama ücretsiz plan hepsini kapsamıyor

Bu ikisi aynı şey değil ve karıştırılması zaman kaybettirir. Etherscan tek
anahtarı bütün zincirlerde **kabul eder**, fakat ücretsiz plan token taramasını
yalnızca bir kısmında **açar**. Kapsam dışı bir zincirde istek
*"Free API access is not supported for this chain"* diye geri döner.

| Otomatik token keşfi | Zincirler |
|:---|:---|
| ✅ Ücretsiz anahtarla çalışır | Ethereum, Polygon, Arbitrum One |
| ❌ Ücretli plan ister | BNB Chain, Base, Optimism, Avalanche |

Zincir açılır listesinde ücretli olanların yanında *"token keşfi ücretli"*
yazar, yani seçerken görürsünüz.

#### Ücretli plana gerek yok: tokenı elle tanımlayın

Kapsam dışı zincirlerde eksik olan tek şey **"hangi tokenlara sahipsiniz"**
bilgisidir. Bakiye okumak zaten ücretsizdir. Siz hangi tokenu takip etmek
istediğinizi zaten bildiğiniz için o boşluğu doğrudan kapatabilirsiniz:

1. Bağlantı listesinde ilgili satırda **Düzenle** deyin.
2. **Elle tanımlı tokenlar** bölümüne tokenın **kontrat adresini** yapıştırın ve
   *Kontrattan Getir*'e basın. Sembolü ve ondalık haneyi sistem zincire sorar.
3. **Kaydet**, sonra **Bakiyeleri Getir**.

Kontrat adresini cüzdanınızdaki token detayından veya blok gezgininden
alabilirsiniz. Dikkat: **aynı tokenın her zincirde ayrı bir kontratı vardır**;
BNB Chain'deki adresi Ethereum'a girerseniz sistem "bu adres ERC-20 kontratı
gibi cevap vermiyor" der.

Bu yol ücretsiz zincirlerde de kullanılabilir — orada otomatik keşfin **yerine
geçmez, üstüne eklenir**. Keşfin kaçırdığı eski bir token için işe yarar.

Anahtar girmezseniz sistem bunu **açıkça söyler**; boş liste gösterip
"varlığınız yok" demez.

### Okuma raporunu okuyun

*Bakiyeleri Getir* her bağlantı için tek satır üretir ve satırlar üç durumdan
birindedir:

| Etiket | Anlamı |
|:---|:---|
| **Okundu** | Her şey geldi. |
| **Eksik okundu** | Bağlantı cevap verdi ama bir kısım veri gelmedi — örneğin token keşfi yapılamadı. |
| **Okunamadı** | Hiçbir şey gelmedi. |

Satır altındaki notlar da ayrışır: ⛔ okunamadı, ⚠ eksik okundu, ℹ bilgi.
**Bilgi notu bir sorun değildir** — örneğin Solana'daki doğrulanmamış token
bildirimi. O tokenlar okundu ve tabloda duruyorlar; yalnızca tanınmış listede
olmadıkları söyleniyor.

> ⚠️ **Uygulamayı her açtığınızda kasa kilitlidir.** Anahtarınız kasada durur ama
> çözme anahtarı diskte durmaz. Kasayı açmadan *Bakiyeleri Getir* derseniz EVM
> tokenlarınız okunmaz — sistem bunu artık okumaya başlamadan önce söylüyor.

### Zincirdeki varlığı deftere ekleme

Karşılaştırma tablosunda **Zincirde var** (veya zincirde defterinizden fazlası
olan **Fark var**) satırlarında **+ Deftere Ekle** düğmesi çıkar. Basınca işlem
formu **coin, miktar ve konum dolu** olarak açılır.

**Tarihi ve birim maliyeti siz girersiniz.** Sistem bunları sizin yerinize
dolduramaz, çünkü **zincir miktarı bilir, maliyeti bilmez.** Zincirde 0.05 BNB
durduğunu görür ama onu kaç dolara aldığınızı görmez — o bilgi ya bir borsanın
geçmişinde ya sizin aklınızdadır. Sıfır maliyetle yazmak, olmayan bir %100 kâr
uydurmak olurdu; mutabakat düzeltmesinde aynı hatayı bir kez yapıp düzeltmiştik.

Bunu **varlık başına bir kez** yaparsınız. Sonrasında o varlık Kasa
toplamınızda, kâr/zarar hesabınızda ve tüm raporlarda normal bir pozisyon gibi
durur; her açılışta tekrar girmeniz gerekmez.

Kayıttan sonra tablo kendiliğinden tazelenir ve satır **Eşleşiyor**'a döner.

> **Alım tarihi alanı** artık her işlem formunda var (yalnızca burada değil).
> Boş bırakırsanız bugünün tarihi kullanılır. Geçmişte alınmış bir varlığı doğru
> tarihiyle girmek önemlidir: FIFO satış maliyetini tarihe göre seçer.

> **Konum kutusu** artık sabit bir liste değil. Defterinizde geçen konumların
> yanı sıra **bağlantı tanımladığınız cüzdanlar** da listede çıkar. Daha önce
> yalnızca BINANCE / MEXC / GATE.IO / DEX seçilebildiği için cüzdandaki varlığı
> "DEX'teymiş gibi" girmek zorunda kalıyordunuz.

### Karşılaştırmayı okuyun

| Etiket | Anlamı |
|:---|:---|
| **Fark var** | Zincirdeki miktar defterinizle uyuşmuyor. |
| **Zincirde var** | Cüzdanda duruyor ama defterinize girmemişsiniz. |
| **Zincirde yok** | Defterinizde var ama bu adreste yok — taşımış veya satmış olabilirsiniz. |
| **Okunamadı** | Bağlantı kurulamadı. **Bu bir fark değildir**, bakiye bilinmiyor. |
| **Eşleşiyor** | Tutuyor. |

Son iki satırın ayrımı önemli: okunamayan bir cüzdanı "boş" saymak, varlığınızı
yok saymak olurdu. Sistem bilmediğinde bunu söyler.

#### Miktarın altındaki tutar

Her miktarın altında **USD karşılığı** yazar. Asıl işe yarayan, farkın
karşılığıdır: `+0,00013 BNB` kararı zorlaştırır, `≈ $0,09` kararı anında
verdirir. Tablo bu yüzden farkın **parasal büyüklüğüne göre** sıralanır —
$412'lik bir fark, $0,002'lik farkın üstünde durur.

Fiyatı bulunamayan varlıkta tutar yerine `—` yazar. **Sıfır yazılmaz**, çünkü
bilinmeyen değer sıfır değer değildir; bir mikro-cap veya delist olmuş coin
gerçekten değerli olabilir.

> **İlk seferde `—` görebilirsiniz.** Fiyat motoru daha önce yalnızca
> defterinizdeki coinleri takip ediyordu. Borsanızda veya cüzdanınızda durup
> deftere yazmadığınız bir varlığı ilk kez gördüğünde onu takibe alır, ama
> fiyatı bir sonraki güncelleme turunda gelir. Birkaç saniye sonra
> **Tüm Bakiyeleri Getir**'e tekrar basın; tutarlar dolmuş olur.

#### Önemsiz farkların katlanması

Borsa bağlantısı ekledikten sonra tablo ücret kırıntılarıyla dolar. Belirlediğiniz
tutarın altındaki farklar bu yüzden **katlanır**: kaç tane oldukları ve toplamları
tablonun altında yazar, "Yine de göster" ile açarsınız. Eşiği aynı satırdan
değiştirebilirsiniz; seçtiğiniz değer kalıcı olarak saklanır (varsayılan `$1`).

Katlama, gizleme değildir — ve **fiyatı bilinmeyen satırlar bu eşiğe hiç
girmez.** Değerini bilmediğimiz bir varlığı "önemsiz" sayıp katlamak, tam olarak
kaçınmaya çalıştığımız hata olurdu.

### Varlıklarınızı yanlış konuma girdiyseniz

Cüzdanınızdaki varlıkları `DEX` gibi genel bir adla girmiş olabilirsiniz —
büyük ihtimalle mecburen, çünkü konum kutusunda cüzdanınızın adı yoktu. Artık
var. Bu kayıtları gerçek konumlarına (`METAMASK`, `PHANTOM`) taşımak için İşlem
Defteri'nden ilgili kaydı düzenleyip konumunu değiştirin. Kaydın adı da o
konuma göre kendiliğinden düzelir: borsaya taşırsanız `SOL` → `SOLUSDT`,
cüzdana taşırsanız `SOLUSDT` → `SOL`.

**Sistem bunu size hatırlatır.** Aynı varlık bir konumda “defterde var, zincirde
yok”, başka bir konumda “zincirde var, defterde yok” çıkıyorsa ve miktarlar
birbirine yakınsa, bu neredeyse her zaman iki ayrı eksiklik değil **yanlış rafa
yazılmış tek bir varlıktır**. Tabloda iki satır görürsünüz ama ortada tek bir
sorun vardır.

O satırlarda **+ Deftere Ekle** düğmesi bilerek gösterilmez; yerine **Konumu
düzelt** çıkar. Sebebi şu: ekleseydiniz aynı varlık defterinize ikinci kez
girer ve portföyünüz olduğundan büyük görünürdü.

> **Konumu düzelt** bir transfer değildir. Transfer, gerçekten yaşanmış bir
> hareketi kaydeder ve iki iz bırakır. Burada varlık o konumda hiç bulunmadı;
> kayıt baştan yanlış yazıldı. Bu yüzden düzeltme yalnızca **konumu ve sembolü**
> değiştirir — miktar, maliyet, tarih ve notlar aynı kalır, kapalı kayıtlara
> hiç dokunulmaz. O konumdaki birden çok lot varsa hepsi birlikte taşınır.

Gerçekten bir hareket yaptıysanız (paranızı bir cüzdandan diğerine
gönderdiyseniz) doğru araç **Transfer**'dir, bu değil.

### Tanımadığınız tokenlar

Zincir üstü adreslere istenmeden token gönderilmesi yaygındır; bazıları sadece
gürültü, bazıları sizi kendi sitesine çekmeye çalışan tuzaklardır. Sistem
bunların defterinize kendiliğinden girmesini engeller ama **iki ayrı durumu
birbirinden ayırır**:

| Durum | Ne demek | Ne yapılır |
|:---|:---|:---|
| **Katlanmış (spam)** | Doğrulanmış token listesi bu tokenı tanımıyor (Solana). | Tablo altında sayısı yazar; “Yine de göster” ile açabilirsiniz. |
| **İnceleme bekliyor** | Elimizde bir hüküm yok: token yalnızca zincir keşfinden geldi, elle tanımlamadınız, defterinizde geçmiyor ve fiyat kaynağı yok (EVM). | Satır **görünür kalır**, yalnızca ekleme önerilmez. |

Bu ayrım önemli: “bilmiyorum” ile “sahte” aynı şey değildir. EVM zincirlerinde
kürasyonlu bir doğrulanmış-token listesi kullanmıyoruz, dolayısıyla bir tokenın
sahte olduğunu söyleyecek dayanağımız da yok. Onu spam sayıp gizleseydik,
Ethereum'da gerçekten USDC tutan ve henüz deftere yazmamış bir kullanıcının
varlığı kendisinden saklanırdı.

Son söz sizindir. Her iki durumda da satırın sonunda **Bu gerçek** düğmesi
vardır; bastığınızda token doğrulanmış sayılır, katlanmaz ve deftere
ekleyebilirsiniz. Tersi de mümkün: tanımadığınız bir tokenın yanındaki **spam**
bağlantısına basarsanız katlanır. İşaret kalıcıdır ve **kontrat adresine**
bağlanır — sembole değil, çünkü sembol taklit edilebilir ve spam tokenlar bunu
bilerek yapar.

Bir token şu üç durumdan birindeyse zaten doğrulanmış sayılır ve hiç
işaretlemeniz gerekmez: kontratını **elle tanımladıysanız**, sembolü
**defterinizde geçiyorsa**, veya onun için bir **fiyat kaynağı** tanımlıysa.

### Borsa bağlantıları

Cüzdanlarda olduğu gibi borsadaki bakiyenizi de doğrudan okuyabilirsiniz; her ay
tarayıcıdan dosya indirip uygulamaya vermeniz gerekmez. Borsa okuması, cüzdan
okumasıyla **aynı tabloda** görünür ve aynı karşılaştırmaya girer — yanlış konum
tespiti, deftere ekleme ve not seviyeleri borsalarda da aynen çalışır.

> ⚠️ **Borsa API anahtarı, cüzdan adresinden farklıdır.** Adres herkese açıktır
> ve paylaşılmak içindir. API anahtarı ise **gerçek bir sırdır**: salt okunur
> olsa bile tüm işlem geçmişinizi açar. Bu yüzden anahtar **şifreli kasada**
> saklanır ve `settings.json` içinde düz metin olarak asla bulunmaz.

**Anahtarı borsada oluştururken yalnızca okuma iznini açın.** Para çekme ve emir
verme izinlerini kapalı bırakın; mümkünse IP kısıtlaması da tanımlayın.
CoinTakip yazma yetkisi taşıyan bir anahtarı **kabul etmez** — portföy takibi
için okuma yeterlidir ve yazma yetkili bir anahtarın burada durması gereksiz bir
risktir.

Bağlantı yalnızca **GET** isteği yapar. Emir verme veya para çekme çağrısı
uygulamada **yoktur**.

#### İzin doğrulaması ve doğrulanamayan borsalar

| Durum | Ne demek |
|:---|:---|
| **Salt okunur (doğrulandı)** | Borsa, anahtarınızın yetkilerini bize söyledi ve anahtar yalnızca okuyabiliyor. |
| **Reddedildi** | Anahtar para çekebiliyor veya emir verebiliyor. Kaydedilmez. |
| **İzin doğrulanamadı** | Borsanın API'si bir anahtarın yetkilerini bildiren uç sunmuyor. |

Üçüncü durum Binance'te değil ama **MEXC'te** geçerlidir. Böyle bir borsada
anahtarınızın gerçekten salt okunur olduğunu doğrulayamayız, bu yüzden size
açıkça söyler ve onayınızı isteriz. Hesabın `canTrade` gibi alanlarına
bakmıyoruz: onlar **anahtarın değil hesabın** yetkisidir ve onları anahtar
yetkisi saymak, size veremeyeceğimiz bir güvence vermek olurdu.

#### Yeni bir borsa eklemek

Hazır profiller (Binance, MEXC) tek tıkla formu doldurur. Ama borsa listesi koda
gömülü değildir: **Profil ayrıntıları** bölümünden taban adresi, uç noktaları ve
alan eşlemesini kendiniz tanımlayarak yeni bir borsa ekleyebilirsiniz.

Bunun bir sınırı var ve dürüstçe söylemek gerekir: her borsa isteği **farklı
imzalar**. Uygulamada şu an bir imzalama ailesi var — Binance tipi (HMAC-SHA256,
sorgu dizisi). MEXC'in v3 API'si bu ailenin bir klonudur, dolayısıyla aynı
adaptör iki borsayı birden kapsıyor ve v3'ü klonlayan diğer borsalar da profil
tanımlayarak eklenebilir. Farklı bir imzalama şeması kullanan bir borsa (Gate.io,
OKX ailesi, Bybit) yine kod değişikliği ister. **"Her borsa çalışır" demiyoruz.**

#### Konum adı defterinizle aynı olmalı

Profildeki konum adı (`BINANCE`, `MEXC`) defterinizdeki konum adıyla birebir
aynı olmalıdır. Farklı olursa karşılaştırma iki ayrı yer görür: defteriniz bir
konumda, borsa bakiyeniz başka bir konumda çıkar.

#### Ne okunur, ne okunmaz

Bu okuma **spot cüzdanı** kapsar. Vadeli, kaldıraçlı ve Earn/Staking
hesaplarındaki varlıklarınız görünmez; spot bakiyeniz boş çıkıyorsa sebebi
genellikle budur ve uygulama bunu size söyler.

Bağlantıyı sildiğinizde kasadaki anahtarınız da silinir. "Sildim" dediğiniz bir
sırrın diskte durmaya devam etmesi doğru olmazdı. Defterinizdeki kayıtlara
dokunulmaz.

---

## 12. Arşiv ve net varlık eğrisi

**Grafikler → 🗄️ Arşiv & Net Varlık**

Borsalar geçmişi süresiz saklamaz ve pencereleri kayar. Uygulama her çalıştığında
o günkü portföy durumunu yerel bir SQLite arşivine (`data/archive.db`) yazar:
toplam değer, pozisyon bazında miktar ve **fiyat**, konum bazında dağılım.

Böylece borsanın sildiği geçmiş sizde kalır ve zamanla gerçek bir net varlık
eğrisi oluşur.

Üç kural:

- Günde **bir** kayıt tutulur; aynı gün tekrar açarsanız üzerine yazılır.
- Fiyat çekilemediyse **kayıt alınmaz** — yanlış veri hiç veriden kötüdür.
- Kayıt bulunmayan günler **gizlenmez**, açıkça bildirilir.

**Fotoğraf Al** düğmesiyle elle de kayıt alabilirsiniz.

---

## 13. Vergi-hazır dışa aktarım

**Grafikler → 📊 Performans & Dağılım → Vergi-Hazır Dışa Aktarım**

Yılda bir kez, mali müşavirinize verebileceğiniz bir dosya üretir. Dönemi
seçersiniz (`Tüm yıllar` veya tek bir yıl), **Excel (.xlsx)** ya da **CSV**
indirirsiniz.

### Bu dosya bir vergi hesabı değildir

Dosya matrah, oran, istisna veya mahsup **içermez** ve içermemesi bilinçlidir.
Yaptığı tek şey, defterinizdeki gerçekleşmiş olayları denetlenebilir düz bir
tabloya dökmektir. Hesaplanmış bir yükümlülük üretmek sorumluluk doğurur ve
Türkiye'de kripto vergilendirmesi henüz oturmuş değildir.

### Neden TRY yok

Tüm tutarlar **USD** cinsindendir. Beyan TRY üzerinden yapılır ve **işlem
tarihindeki kur** gerekir — ama "hangi kur" sorusunun üç ayrı cevabı vardır:
hangi kurum (TCMB, borsa), hangi kur (alış, satış, efektif) ve tatil günlerinde
hangi günün kuru. Bunlar uygulamanın sizin adınıza veremeyeceği kararlardır ve
yanlış kur, doğru veriden yanlış beyan üretir. Kuru mali müşaviriniz uygular.

### Dosyanın içinde ne var

Excel dosyası dört sayfadır:

| Sayfa | İçeriği |
|:---|:---|
| **Özet** | Dönem, para birimi, kapsam beyanı ve toplamlar |
| **Gerçekleşmiş İşlemler** | Asıl tablo — her kapanmış olay bir satır |
| **Eksik Veri** | Kapanmış ama çıkış fiyatı olmayan kayıtlar |
| **Kapsam Dışı** | Transferler, mutabakat kapanışları, açık pozisyonlar |

Ana tabloda her satır şunları taşır: kayıt numarası (deftere geri izlemek için),
varlık, konum, olay türü, alış ve çıkış tarihi, miktar, birim fiyatlar, toplam
maliyet, toplam hasılat, komisyon, gerçekleşmiş K/Z, maliyet yöntemi ve açıklama.

**Olay türü üç değer alır** ve bunlar aynı şey değildir:

- **Satış** — normal bir elden çıkarma.
- **Yazım (değersiz)** — sıfıra kapatılmış pozisyon. Hasılatı yoktur; gider
  yazılabilirliği mali müşavirinizin kararıdır.
- **Mutabakat özeti (toplu)** — **tek bir işlem değildir.** Borsa dosyasından
  yeniden kurulmuş, kapanmış birçok işlemin toplu sonucudur.

### "Eksik Veri" sayfasına mutlaka bakın

Defterinizde kapanmış görünen ama çıkış fiyatı taşımayan kayıtlar olabilir.
Bunlar büyük ihtimalle satılmış ama satış fiyatı girilmemiş pozisyonlardır.

Uygulama bunları dosyadan **atmaz.** Atsaydı tablo hem kazancınızı hem zararınızı
eksik gösterirdi ve siz bunu fark edemezdiniz. Bunun yerine ayrı bir sayfada,
kayıt numarası ve maliyetiyle listelenirler. Panelde de indirmeden önce sarı bir
uyarı olarak görünür.

Bir kayıt oraya düştüyse yapmanız gereken, İşlem Defteri'nden o kaydı bulup satış
fiyatını ve tarihini girmektir. Sonra dosyayı yeniden indirin.

### Neden "Kapsam Dışı" diye bir sayfa var

Bir vergi dosyasının denetlenebilir olması, dışarıda bıraktığı şeyi de göstermesi
demektir. Defterinizdeki her kayıt dört kümeden birindedir ve toplamları defterin
tamamını verir:

```
Gerçekleşmiş  +  Eksik Veri  +  Kapsam Dışı  =  Defterdeki toplam kayıt
```

Kapsam dışı bırakılanlar ve nedenleri:

- **Transfer** — kendi cüzdanınıza taşımak satış değildir, K/Z üretmez.
- **Mutabakat kapanışı** — hatalı kaydın düzeltilmesidir, elden çıkarma değil.
- **Açık pozisyon** — henüz satılmamıştır.

### CSV ne zaman işe yarar

Aynı içeriği taşır, noktalı virgülle ayrılmış ve UTF-8'dir. Excel'i olmayan ya da
veriyi başka bir programa aktaracak bir müşavir için pratiktir. Excel dosyası
biçimli olduğu için okumaya daha uygundur.

---

## 14. Güvenlik: PIN ve gizlilik modu

**PIN koruması** Ayarlar'dan açılır. Kuruluma özel bir salt ile SHA-256 kullanılır;
PIN'in kendisi hiçbir yerde saklanmaz.

PIN kurarken size bir **kurtarma anahtarı** verilir. Kaybederseniz PIN'i sıfırlamanın
başka yolu yoktur — güvenli bir yere kaydedin.

**Gizlilik modu** tüm rakamları maskeler. Ekran paylaşırken veya birinin yanınızda
olduğu durumlarda kullanışlıdır.

> **API anahtarları hakkında:** `settings.json` içindeki anahtarlar Base64 ile
> okunaksızlaştırılır — bu **şifreleme değildir**. Dosyaya erişebilen biri
> anahtarınızı okuyabilir.

---

## 15. Yedekleme ve geri yükleme

Uygulama her gün otomatik yedek alır: `data/backups/portfolio_backup_YYYYMMDD.json`.

Ayarlar'dan **elle yedek indirebilir** ve bir yedeği **geri yükleyebilirsiniz**.

Tüm veriniz `data/` klasöründedir. Başka bir bilgisayara taşımak için o klasörü
kopyalamanız yeterlidir.

> ⚠️ `data/` klasörünü **asla paylaşmayın** ve depoya eklemeyin. `.gitignore`
> kapsamındadır ama dikkatli olun.

### Veri düzeltmeleri

Bazı sürümler, eski kayıtlardaki bir hatayı onarmak için **bir kez çalışan**
küçük düzeltmeler getirir. Bunlar uygulama açılışında yapılır, `settings.json`
içinde işaretlenir (`migrations`) ve ikinci kez çalışmaz.

Sessizce olmazlar: ne değiştiyse `data/logs/cointakip.log` dosyasına satır satır
yazılır. Sonucu beğenmezseniz o günün yedeğinden geri dönebilirsiniz.

Şimdiye kadar ikisi var ve ikisi de aynı işi yapar — `wallet_symbol_v1` ve
`wallet_symbol_v2`: transferle oluşmuş cüzdan kayıtlarındaki gereksiz `USDT`
ekini düşürürler (`BNBUSDT` → `BNB`). Yalnızca **adı** değiştirirler; miktara,
maliyete, tarihe veya duruma dokunmazlar ve elle girdiğiniz kayıtları hiç
ellemezler.

İkinci bir geçişin sebebi şu: birincisi çalıştıktan sonra, düzeltmenin kaynağı
olan kod değişikliği yüklenmeden önce yapılan transferler yine eski adla
kaydedilmişti. Birinci geçiş işaretlendiği için tekrar çalışmıyordu; bu yüzden
ayrı anahtarlı ikinci bir geçiş eklendi. Buradan çıkan ders koda da yazıldı:
açılışta veriye dokunan bir düzeltme, kendisini gerektiren kod değişikliğiyle
**aynı anda** diske inmelidir.

---

## 16. Sık sorulanlar

**İnternet gerekiyor mu?**
Fiyatlar için evet. Arayüz kütüphaneleri paketli olduğu için CDN erişimi olmasa da
arayüz yüklenir, ama fiyat çekmek için ağ gerekir.

**Verilerim buluta gidiyor mu?**
Hayır. Uygulama `127.0.0.1` üzerinde çalışır. Dışarı çıkan tek şey fiyat
sorgularıdır (hangi coinlerin fiyatını sorduğunuz görülebilir, portföyünüz değil).
Gemini anahtarı tanımlarsanız, yalnızca siz analiz istediğinizde portföy özeti
Google'a gider.

**Yapay zekâ zorunlu mu?**
Hayır. Gemini anahtarı girmezseniz yerel kural motoru devreye girer.

**Aynı coini iki borsada tutuyorum, neden iki satır görüyorum?**
Bilerek. Ayrı maliyet tabanları ayrı takip edilir. Konsolide görünüm için Kasa
sekmesindeki toplamlara bakın.

**Mutabakat, borsada gerçekten duran bir coini silmek istiyor. Ne oluyor?**
Dosya o coinin alımını görmüyor demektir — büyük ihtimalle dosya penceresinden
önce alıp hiç satmamışsınız, ya da airdrop/Convert gibi bir kanaldan gelmiş ve o
dosyayı klasöre koymamışsınız (Binance'te **Transaction History**). Onay
penceresinde borsadaki gerçek bakiyenizi yazın: rakam defterinizle uyuşuyorsa
sistem düzeltmeyi **reddeder** ve defterinize dokunmaz. Doğru davranış budur;
eksik olan sizin kaydınız değil, dosyadır.

**Etherscan anahtarını girdim ama tokenım hâlâ gelmiyor.**
Muhtemelen o token, ücretsiz planın kapsamadığı bir zincirde: BNB Chain, Base,
Optimism veya Avalanche. Bağlantının okuma satırında bunu açıkça yazar. Ücretli
plana geçmeye gerek yok — bağlantıyı **Düzenle**yip tokenın **kontrat adresini**
elle tanımlayın; bakiye doğrudan zincirden okunur ve anahtar gerekmez.

**"Eksik okundu" ile "bilgi" notu arasındaki fark ne?**
⚠ **eksik okundu**, bağlantının cevap verdiğini ama bir kısım verinin
gelmediğini söyler — bir şey yapmanız gerekir. ℹ **bilgi** ise eksiklik değildir;
örneğin Solana'daki doğrulanmamış token bildirimi. O tokenlar okundu ve tabloda
duruyorlar, sadece tanınmış listede yoklar.

**Bir işlemi yanlış girdim.**
İşlem defterinden silebilir veya düzenleyebilirsiniz. Transfer, zarar yazımı ve
mutabakat düzeltmesi ise kendi geri alma düğmelerine sahiptir.

**Vergi beyanı için kullanabilir miyim?**
Excel dışa aktarımı gerçekleşmiş kâr/zararı işlem bazında verir. Ancak rakamları
kendi kayıtlarınızla doğrulamadan kullanmayın — bu bir muhasebe yazılımı değildir.

**Uygulama açılmıyor / port 8000 dolu.**
`Durdur.bat` çalıştırın, sonra `Baslat.bat`. Başka bir program 8000'i kullanıyorsa
onu kapatın.
