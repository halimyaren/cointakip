"""
Paketleme ve Önbellek Kırma testleri (FAZ D)

Bu testler iki şeyi korur:

1. **Kütüphaneler yerelde.** Arayüz, CDN erişimine bağlı olmadan açılmalı.
   Biri yanlışlıkla bir `<script src="https://cdn...">` geri eklerse test kırılır.
   (Tek izinli istisna TradingView'dir; betik çalışma anında kendi sunucusundan
   veri çektiği için kopyalamanın faydası yoktur.)

2. **Önbellek kırma otomatik.** Eskiden `app.js` elle yazılmış `?v=2.2` etiketiyle
   sunuluyordu; sürüm elle güncellenmediği sürece tarayıcı eski dosyayı
   önbellekten veriyordu. Artık içerik hash'i kullanılıyor.
"""

import os
import re

import pytest

# DİKKAT: `main` burada MODÜL SEVİYESİNDE import EDİLMEZ.
#
# `main.py`'nin gövdesi import anında iş yapar: veri dosyasını hazırlar,
# bekleyen veri düzeltmelerini çalıştırır ve fiyat motorunun arka plan
# thread'ini başlatır. Modül seviyesinde import edilirse bunlar **toplama
# (collection) anında**, yani `izole_veri` fixture'ı devreye girmeden ÖNCE
# çalışır. Bu üç ayrı ihlale yol açıyordu:
#
#   1. Veri düzeltmeleri GERÇEK `data/portfolio.json` üzerinde koşabilirdi.
#      (Zarar görmedi çünkü iki migration da zaten "yapıldı" işaretliydi —
#      tasarım değil, şans.)
#   2. Fiyat thread'i tüm oturum boyunca canlı kalıp 4 saniyede bir AĞA
#      çıkıyordu; README'nin "testler ağa dokunmaz" sözü bozuluyordu.
#   3. O thread `price_service.prices`'ı arka planda değiştirdiği için
#      testler seyrek ve tekrar üretilemez şekilde kırılıyordu.
#
# Bu yüzden `main` yalnızca fixture içinden import edilir.
# `conftest.py::fiyat_ipligi_calismadi` kuralı ayrıca bekçilikle korur.

PROJE_KOKU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(PROJE_KOKU, "app", "static")
VENDOR_DIR = os.path.join(STATIC_DIR, "vendor")


@pytest.fixture
def main():
    """`main` modülü — fixture'lar aktifken, izole veri yollarıyla."""
    import main as main_modulu
    return main_modulu

# TradingView bilinçli olarak uzakta bırakıldı — bkz. index.html'deki not.
IZINLI_UZAK_KAYNAKLAR = ("s3.tradingview.com",)

# Kullanıcının TIKLAYARAK gittiği dış bağlantılar. Bunlar YÜKLENEN kaynak
# değildir: sayfa açıldığında hiçbir istek üretmezler, uygulama çevrimdışı
# çalışmaya devam eder ve hiçbir veri sızmaz. Ancak yine de sayılı ve
# gerekçeli tutuluyor — bir gün yanlışlıkla eklenen bir izleyici bağlantısı
# fark edilmeden geçmesin diye liste açık uçlu DEĞİL.
#
# coingecko.com/en/api/pricing : ücretsiz piyasa verisi anahtarının alındığı
#   sayfa (FAZ M1). Anahtarlı kullanım tercih edilen yol olduğu için
#   kullanıcının oraya nasıl gideceği arayüzde yazılı olmalı.
IZINLI_TIKLAMA_BAGLANTILARI = ("https://www.coingecko.com/en/api/pricing",)

BEKLENEN_KUTUPHANELER = [
    "tailwind.min.js",
    "alpine.min.js",
    "chart.min.js",
    "lucide.min.js",
    "fonts.css",
]


def _index_ham():
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()


# ===========================================================================
# YEREL KÜTÜPHANELER
# ===========================================================================

@pytest.mark.parametrize("dosya", BEKLENEN_KUTUPHANELER)
def test_kutuphane_vendor_klasorunde_var(dosya):
    yol = os.path.join(VENDOR_DIR, dosya)
    assert os.path.exists(yol), f"{dosya} vendor klasöründe yok"
    assert os.path.getsize(yol) > 1000, f"{dosya} şüpheli derecede küçük"


def _tiklama_baglantilari(html):
    """`<a href="http...">` — kullanıcının tıklayarak gittiği bağlantılar."""
    return re.findall(r'<a\b[^>]*\bhref="(https?://[^"]+)"', html)


def test_index_html_izinsiz_cdn_referansi_icermez():
    """Regresyon: arayüz kütüphaneleri CDN'den çekilmemeli.

    Sayfa AÇILDIĞINDA yüklenen her şeyi kapsar: script/img/iframe `src`'leri
    ve `<link href>` stil dosyaları. Kullanıcının tıklayarak gittiği
    `<a href>` bağlantıları ayrı bir testte ve ayrı bir izin listesinde
    denetlenir — onlar sayfa yüklenirken hiçbir istek üretmez.
    """
    html = _index_ham()
    tiklama = set(_tiklama_baglantilari(html))
    uzak = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    yuklenen = [u for u in uzak if u not in tiklama]
    izinsiz = [u for u in yuklenen
               if not any(izin in u for izin in IZINLI_UZAK_KAYNAKLAR)]
    assert izinsiz == [], f"index.html hâlâ uzak kaynak yüklüyor: {izinsiz}"


def test_dis_baglantilar_sayili_ve_gerekceli():
    """Dış bağlantılar açık uçlu olamaz.

    Tıklama bağlantısı yüklenen kaynak değildir ama yine de denetimsiz
    bırakılmaz: bir gün eklenen bir izleyici/analitik bağlantısı fark
    edilmeden geçmesin diye her biri listede gerekçesiyle durmalı.
    """
    html = _index_ham()
    izinsiz = [u for u in _tiklama_baglantilari(html)
               if u not in IZINLI_TIKLAMA_BAGLANTILARI]
    assert izinsiz == [], (
        "index.html'de listelenmemiş dış bağlantı var: "
        f"{izinsiz} — gerekçesiyle IZINLI_TIKLAMA_BAGLANTILARI'na ekle")


def test_dis_baglantilar_tabnabbing_e_kapali():
    """Her dış bağlantı `rel="noopener"` taşımalı.

    `target="_blank"` ile açılan bir sayfa, `rel="noopener"` olmadan
    `window.opener` üzerinden bu sayfayı başka bir adrese yönlendirebilir.
    Portföy uygulamasında bu, kimlik avı sayfasına yönlendirme demektir.
    """
    html = _index_ham()
    for etiket in re.findall(r'<a\b[^>]*\bhref="https?://[^"]+"[^>]*>', html):
        assert "noopener" in etiket, f"rel=noopener eksik: {etiket[:120]}"


def test_index_html_yerel_kutuphaneleri_kullanir():
    html = _index_ham()
    for dosya in BEKLENEN_KUTUPHANELER:
        assert f"/static/vendor/{dosya}" in html, f"{dosya} index.html'de referanslanmıyor"


def test_fontlar_yerel_dosyalari_gosterir():
    """
    Google Fonts CSS'i indirildi ama içindeki woff2 adresleri hâlâ uzaktaysa
    paketleme yarım kalmış olur — internetsizken yazı tipleri yüklenmez.
    """
    with open(os.path.join(VENDOR_DIR, "fonts.css"), "r", encoding="utf-8") as f:
        css = f.read()
    assert "https://fonts.gstatic.com" not in css, "fonts.css hâlâ uzak font çekiyor"

    yerel = re.findall(r"url\((fonts/[^)]+)\)", css)
    assert len(yerel) >= 5, "Yerel font dosyası referansı beklenenden az"
    for rel in set(yerel):
        assert os.path.exists(os.path.join(VENDOR_DIR, rel)), f"{rel} diskte yok"


# ===========================================================================
# ÖNBELLEK KIRMA
# ===========================================================================

def test_icerik_hash_dosyaya_gore_degisir(main, tmp_path):
    a = tmp_path / "a.js"
    a.write_text("birinci", encoding="utf-8")
    h1 = main._icerik_hash(str(a))
    a.write_text("ikinci", encoding="utf-8")
    h2 = main._icerik_hash(str(a))

    assert len(h1) == 8 and len(h2) == 8
    assert h1 != h2, "İçerik değişince hash değişmeli"


def test_olmayan_dosyanin_hashi_bostur(main):
    assert main._icerik_hash("/olmayan/dosya.js") == ""


def test_uretilen_index_surum_etiketi_ekler(main):
    html = main._index_html_uret()
    yerel = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
    assert yerel, "Yerel referans bulunamadı"
    for yol in yerel:
        assert "?v=" in yol, f"{yol} sürüm etiketi taşımıyor"


def test_elle_yazilmis_surum_etiketi_degistirilir(main):
    """
    Regresyon: index.html'de `app.js?v=2.2` gibi elle yazılmış bir sürüm
    varsa, üretilen çıktıda onun yerine içerik hash'i olmalı.
    """
    html = main._index_html_uret()
    assert "app.js?v=2.2" not in html
    m = re.search(r'/static/app\.js\?v=([0-9a-f]{8})', html)
    assert m, "app.js içerik hash'i taşımıyor"

    beklenen = main._icerik_hash(os.path.join(STATIC_DIR, "app.js"))
    assert m.group(1) == beklenen


def test_kok_yol_onbelleklenmeyi_engeller(client):
    """
    HTML'in kendisi önbelleğe alınırsa yeni sürüm etiketleri tarayıcıya hiç
    ulaşmaz ve önbellek kırma anlamsızlaşır.
    """
    r = client.get("/")
    assert r.status_code == 200
    cache = r.headers.get("cache-control", "")
    assert "no-cache" in cache or "no-store" in cache


def test_kok_yol_surum_etiketli_html_doner(client):
    r = client.get("/")
    assert "?v=" in r.text
    assert "/static/vendor/alpine.min.js?v=" in r.text


def test_index_onbellegi_dosya_degisince_yenilenir(main, monkeypatch):
    """
    Üretilen HTML önbelleğe alınıyor; dosya değiştiğinde damga değişmeli ve
    HTML yeniden üretilmeli. Aksi halde kullanıcı sunucu yeniden başlatılana
    kadar eski etiketleri görür.
    """
    imza1 = main._index_imzasi()
    assert imza1, "İmza üretilemedi"

    sahte = tuple(list(imza1) + [12345])
    monkeypatch.setattr(main, "_index_imzasi", lambda: sahte)
    main._index_cache["imza"] = imza1

    # Yeni imza eskisinden farklı olduğu için önbellek geçersiz sayılmalı
    assert main._index_imzasi() != main._index_cache["imza"]


# ===========================================================================
# KURULUM SİHİRBAZI
# ===========================================================================

def test_setup_bat_mevcut_ve_temel_adimlari_icerir():
    # app/static → app → proje kökü
    kok = os.path.dirname(os.path.dirname(STATIC_DIR))
    yol = os.path.join(kok, "setup.bat")
    assert os.path.exists(yol), "setup.bat proje kökünde yok"

    with open(yol, "r", encoding="utf-8", errors="replace") as f:
        icerik = f.read()

    for beklenen in ("python --version", "requirements.txt", "import fastapi"):
        assert beklenen in icerik, f"setup.bat '{beklenen}' adımını içermiyor"

    # Kurulum betiği kullanıcı verisini ASLA silmemeli
    for tehlikeli in ("del data", "rmdir", "rd /s"):
        assert tehlikeli not in icerik.lower(), f"setup.bat tehlikeli komut içeriyor: {tehlikeli}"


# ===========================================================================
# GERÇEK VERİYE YAZMA DUVARI
#
# 5 Eylül 2026'da gerçek `data/settings.json` bir test oturumu sırasında
# varsayılan ayarlarla üzerine yazıldı ve kullanıcının Gemini anahtarı,
# cüzdan bağlantıları, şifreli borsa anahtarları ve PIN'i kayboldu.
# `izole_veri` yönlendirmesi vardı ama yetmedi. Artık ek olarak işletim
# sistemi seviyesinde bir duvar var; aşağıdaki testler o duvarın gerçekten
# ayakta olduğunu doğrular.
# ===========================================================================

def test_gercek_veriye_yazma_duvari_ayakta(tmp_path):
    """Duvar çalışıyor mu? Gerçekten deneyip görüyoruz."""
    gercek = os.path.join(PROJE_KOKU, "data", "settings.json")
    with pytest.raises(AssertionError, match="GERÇEK KULLANICI VERİSİNE"):
        open(gercek, "w").close()


def test_duvar_gercek_veriyi_okumaya_engel_degil():
    """Okumak serbest — engellenen yalnızca YAZMA."""
    hedef = os.path.join(PROJE_KOKU, "data", "settings.json")
    if not os.path.exists(hedef):
        pytest.skip("gerçek settings.json yok")
    with open(hedef, "r", encoding="utf-8") as f:
        assert f.read() is not None


def test_duvar_gecici_dizine_yazmaya_engel_degil(tmp_path):
    """Testlerin kendi geçici dosyalarını yazması engellenmemeli."""
    hedef = tmp_path / "deneme.json"
    with open(hedef, "w", encoding="utf-8") as f:
        f.write("{}")
    assert hedef.exists()


def test_duvar_log_dosyasini_engellemez():
    """Günlük kaydı veri değildir; log yazımı serbest kalmalı."""
    from conftest import _gercek_veri_yolu_mu
    log = os.path.join(PROJE_KOKU, "data", "logs", "cointakip.log")
    assert _gercek_veri_yolu_mu(log) is False
    assert _gercek_veri_yolu_mu(os.path.join(PROJE_KOKU, "data", "portfolio.json")) is True
    assert _gercek_veri_yolu_mu(os.path.join(PROJE_KOKU, "data", "archive.db")) is True
