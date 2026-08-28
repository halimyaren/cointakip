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
11. [Arşiv ve net varlık eğrisi](#11-arşiv-ve-net-varlık-eğrisi)
12. [Güvenlik: PIN ve gizlilik modu](#12-güvenlik-pin-ve-gizlilik-modu)
13. [Yedekleme ve geri yükleme](#13-yedekleme-ve-geri-yükleme)
14. [Sık sorulanlar](#14-sık-sorulanlar)

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

Binance için **Spot Trade History**, ayrıca varsa **Deposit History** ve
**Withdraw History**. MEXC için **Trade History** ve **Statement**.

> "Order History" ile "Trade History" farklıdır: ilki verdiğiniz emirleri, ikincisi
> gerçekleşen dolumları içerir. Sistem doğru olanı seçer, ikisini de koyabilirsiniz.

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
| **Uygulanabilir** | Dosya bu varlığın geçmişini baştan sona kapsıyor. Öneri güvenilir. |
| **Önce uyarıyı oku** | Öneri hesaplandı ama bilmeniz gereken bir şey var — genelde o borsadan coin çekmiş olmanız. Satırdaki ⚠ cümlesini okuyun. |
| **Kapsam yetersiz** | Öneri **verilmiyor**. Uydurmaktansa susmayı tercih ediyor. |
| **Zaten uyumlu** | Yapılacak bir şey yok. |

**Bu Pozisyonu Düzelt** düğmesi bir onay penceresi açar: defterdekiyle borsanın
dediği yan yana, ne olacağı ve neye dikkat etmeniz gerektiği ayrı ayrı, ve deftere
yazılacak alımların tam dökümü.

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

## 11. Arşiv ve net varlık eğrisi

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

## 12. Güvenlik: PIN ve gizlilik modu

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

## 13. Yedekleme ve geri yükleme

Uygulama her gün otomatik yedek alır: `data/backups/portfolio_backup_YYYYMMDD.json`.

Ayarlar'dan **elle yedek indirebilir** ve bir yedeği **geri yükleyebilirsiniz**.

Tüm veriniz `data/` klasöründedir. Başka bir bilgisayara taşımak için o klasörü
kopyalamanız yeterlidir.

> ⚠️ `data/` klasörünü **asla paylaşmayın** ve depoya eklemeyin. `.gitignore`
> kapsamındadır ama dikkatli olun.

---

## 14. Sık sorulanlar

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

**Bir işlemi yanlış girdim.**
İşlem defterinden silebilir veya düzenleyebilirsiniz. Transfer, zarar yazımı ve
mutabakat düzeltmesi ise kendi geri alma düğmelerine sahiptir.

**Vergi beyanı için kullanabilir miyim?**
Excel dışa aktarımı gerçekleşmiş kâr/zararı işlem bazında verir. Ancak rakamları
kendi kayıtlarınızla doğrulamadan kullanmayın — bu bir muhasebe yazılımı değildir.

**Uygulama açılmıyor / port 8000 dolu.**
`Durdur.bat` çalıştırın, sonra `Baslat.bat`. Başka bir program 8000'i kullanıyorsa
onu kapatın.
