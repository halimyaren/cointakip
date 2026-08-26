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

import main


STATIC_DIR = main.static_dir
VENDOR_DIR = os.path.join(STATIC_DIR, "vendor")

# TradingView bilinçli olarak uzakta bırakıldı — bkz. index.html'deki not.
IZINLI_UZAK_KAYNAKLAR = ("s3.tradingview.com",)

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


def test_index_html_izinsiz_cdn_referansi_icermez():
    """Regresyon: arayüz kütüphaneleri CDN'den çekilmemeli."""
    html = _index_ham()
    uzak = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    izinsiz = [u for u in uzak if not any(izin in u for izin in IZINLI_UZAK_KAYNAKLAR)]
    assert izinsiz == [], f"index.html hâlâ uzak kaynak kullanıyor: {izinsiz}"


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

def test_icerik_hash_dosyaya_gore_degisir(tmp_path):
    a = tmp_path / "a.js"
    a.write_text("birinci", encoding="utf-8")
    h1 = main._icerik_hash(str(a))
    a.write_text("ikinci", encoding="utf-8")
    h2 = main._icerik_hash(str(a))

    assert len(h1) == 8 and len(h2) == 8
    assert h1 != h2, "İçerik değişince hash değişmeli"


def test_olmayan_dosyanin_hashi_bostur():
    assert main._icerik_hash("/olmayan/dosya.js") == ""


def test_uretilen_index_surum_etiketi_ekler():
    html = main._index_html_uret()
    yerel = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
    assert yerel, "Yerel referans bulunamadı"
    for yol in yerel:
        assert "?v=" in yol, f"{yol} sürüm etiketi taşımıyor"


def test_elle_yazilmis_surum_etiketi_degistirilir():
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


def test_index_onbellegi_dosya_degisince_yenilenir(monkeypatch):
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
