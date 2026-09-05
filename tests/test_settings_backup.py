"""
AYAR YEDEĞİ TESTLERİ

╔══════════════════════════════════════════════════════════════════════════╗
║  BU DOSYA GERÇEK BİR VERİ KAYBINDAN DOĞDU.                               ║
║                                                                          ║
║  5 Eylül 2026: `data/settings.json` varsayılan ayarlarla üzerine yazıldı.║
║  Kullanıcının Gemini API anahtarı, cüzdan bağlantıları, şifreli borsa    ║
║  anahtarları ve PIN'i kayboldu. GERİ ALINAMADI — çünkü uygulama sadece   ║
║  `portfolio.json` yedekliyordu; sekiz yedeğin hiçbirinde ayar yoktu.     ║
║                                                                          ║
║  Buradaki her test, o olayın tekrarını yakalamak için var.              ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import json
import os
import time

import pytest

import data_manager as dm


def _yedekteki_gemini(ad):
    """Bir yedek dosyasındaki Gemini anahtarını çözüp döndürür (test yardımcısı)."""
    with open(os.path.join(dm.BACKUP_DIR, ad), encoding="utf-8") as f:
        return dm._deobfuscate_key((json.load(f).get("api_keys") or {})
                                   .get("gemini_api_key", ""))


def _ornek_ayar(gemini="AIzaSyGIZLI", pin=True):
    a = json.loads(json.dumps(dm.DEFAULT_SETTINGS))
    a["api_keys"]["gemini_api_key"] = gemini
    a["connections"] = {"METAMASK": {"type": "onchain", "chain": "ethereum",
                                     "address": "0xABC"}}
    a["vault"] = {"binance_api_key": "sifreli-veri"}
    a["exchange_profiles"] = {"MEXC": {"family": "hmac_sha256"}}
    a["security"] = {"pin_enabled": pin, "pin_hash": "hash", "salt": "salt",
                     "auto_lock_minutes": 10, "privacy_mode": False}
    return a


# =====================================================================
# 1. OLAYIN KENDİSİ — bugünkü kayıp artık geri alınabilir mi?
# =====================================================================
class TestOlayTekrarlanirsa:

    def test_varsayilanlarla_ezilen_ayar_geri_alinabilir(self):
        """5 Eylül senaryosunun birebir tekrarı.

        Dolu bir ayar dosyası varsayılanlarla eziliyor. Eskiden bu kalıcı
        kayıptı; artık yedekten dönülebilmeli.
        """
        dm.save_settings(_ornek_ayar())
        assert dm.load_settings()["api_keys"]["gemini_api_key"] == "AIzaSyGIZLI"

        # FELAKET: varsayılanlarla üzerine yaz (bugün tam olarak bu oldu)
        dm.save_settings(dm.DEFAULT_SETTINGS)
        assert dm.load_settings()["api_keys"]["gemini_api_key"] == ""
        assert dm.load_settings()["connections"] == {}

        # KURTARMA
        yedekler = dm.list_settings_backups()
        assert yedekler, "felaketten önce yedek alınmamış"
        dolu = [y for y in yedekler if y["contents"]["gemini_api_key"]]
        assert dolu, "hiçbir yedekte Gemini anahtarı yok"

        dm.restore_settings_backup(dolu[0]["name"])
        geri = dm.load_settings()
        assert geri["api_keys"]["gemini_api_key"] == "AIzaSyGIZLI"
        assert geri["connections"]["METAMASK"]["address"] == "0xABC"
        assert geri["vault"]["binance_api_key"] == "sifreli-veri"
        assert geri["security"]["pin_enabled"] is True

    def test_her_hal_yedekte_kalir_eskisi_de_yenisi_de(self):
        """Kritik ayrım.

        Portföy yedeği yazdıktan SONRA alınıyor ve günde bir tane. Ayarlarda
        bu yetmez, iki ayrı boşluk bırakır:

          • Yalnızca "yazdıktan sonra" yedeklemek, `save_settings`in kendisi
            bir bölümü kaybederek çağrıldığında eski hâli kurtaramaz.
          • Yalnızca "yazmadan önce" yedeklemek ise EN YENİ hâli bir sonraki
            kayda kadar korumasız bırakır — kullanıcı anahtarını girip hemen
            ardından bir kayıp yaşarsa yine kurtarılamaz.

        Bu yüzden her iki uçta da yedek alınır ve içerik aynıysa dosya
        üretilmez. Sonuç: yazılan HER FARKLI hâl saklanır.
        """
        dm.save_settings(_ornek_ayar(gemini="ILK_ANAHTAR"))
        dm.save_settings(_ornek_ayar(gemini="IKINCI_ANAHTAR"))

        bulunan = set()
        for y in dm.list_settings_backups():
            with open(os.path.join(dm.BACKUP_DIR, y["name"]), encoding="utf-8") as f:
                icerik = json.load(f)
            bulunan.add(dm._deobfuscate_key(icerik["api_keys"]["gemini_api_key"]))

        assert "ILK_ANAHTAR" in bulunan, "önceki hâl kaybolmuş"
        assert "IKINCI_ANAHTAR" in bulunan, "en yeni hâl korumasız kalmış"

    def test_disaridan_ezilen_dosya_son_iyi_halden_donulur(self):
        """5 Eylül olayının mekanizması: dosya `save_settings` dışından
        eziliyor. Son iyi hâl yedekte durduğu için geri dönülebilmeli."""
        dm.save_settings(_ornek_ayar(gemini="SON_IYI_HAL"))

        # Uygulamayı hiç kullanmadan, dışarıdan üzerine yaz.
        with open(dm.SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(dm.DEFAULT_SETTINGS, f, indent=2, ensure_ascii=False)
        assert dm.load_settings()["api_keys"]["gemini_api_key"] == ""

        dolu = [y for y in dm.list_settings_backups()
                if y["contents"]["gemini_api_key"]]
        assert dolu, "dışarıdan ezilme senaryosunda kurtarılacak yedek yok"
        dm.restore_settings_backup(dolu[0]["name"])
        assert dm.load_settings()["api_keys"]["gemini_api_key"] == "SON_IYI_HAL"


# =====================================================================
# 2. YEDEK ALMA DAVRANIŞI
# =====================================================================
class TestYedekAlma:

    def test_ilk_yazmada_da_yeni_hal_yedeklenir(self):
        """Dosya yokken yedeklenecek ESKİ hâl yoktur; ama yazılan YENİ hâl
        derhal yedeklenmelidir. Aksi halde kullanıcı anahtarını girdikten
        hemen sonraki bir kayıp yine kurtarılamazdı."""
        assert not os.path.exists(dm.SETTINGS_FILE)
        dm.save_settings(_ornek_ayar())
        yedekler = dm.list_settings_backups()
        assert len(yedekler) == 1
        assert yedekler[0]["contents"]["gemini_api_key"] is True

    def test_her_farkli_hal_yedeklenir(self):
        dm.save_settings(_ornek_ayar())
        for i in range(3):
            dm.save_settings(_ornek_ayar(gemini=f"ANAHTAR{i}"))
        # 4 farklı hâl yazıldı; her biri bir kez saklanmalı.
        assert len(dm.list_settings_backups()) == 4

    def test_ayni_icerik_tekrar_yedeklenmez(self):
        """Aynı ayarı üst üste kaydetmek yedek klasörünü şişirmemeli."""
        dm.save_settings(_ornek_ayar())
        for _ in range(5):
            dm.save_settings(_ornek_ayar())
        assert len(dm.list_settings_backups()) == 1

    def test_yedek_sayisi_sinirli(self, monkeypatch):
        monkeypatch.setattr(dm, "SETTINGS_BACKUP_SAYISI", 3)
        dm.save_settings(_ornek_ayar())
        for i in range(5):
            dm.save_settings(_ornek_ayar(gemini=f"K{i}"))
        assert len(dm.list_settings_backups()) == 3

    def test_yedek_alinamazsa_kaydetme_yine_calisir(self, monkeypatch):
        """Yedekleme bir konfordur; kullanıcının ayar kaydetmesini engellememeli."""
        dm.save_settings(_ornek_ayar())

        def patla(*a, **k):
            raise OSError("disk dolu")

        monkeypatch.setattr(dm.shutil, "copyfile", patla)
        dm.save_settings(_ornek_ayar(gemini="YENI"))
        assert dm.load_settings()["api_keys"]["gemini_api_key"] == "YENI"

    def test_bos_dosya_yedeklenmez(self):
        dm.ensure_data_dir()
        with open(dm.SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.write("{}")
        dm.save_settings(_ornek_ayar())
        adlar = dm.list_settings_backups()
        assert len(adlar) == 1, "boş dosya yedeklenmemeli, yalnızca yeni hâl"
        assert adlar[0]["contents"]["gemini_api_key"] is True


# =====================================================================
# 3. LİSTELEME — sırlar ekrana düşmemeli
# =====================================================================
class TestListeleme:

    def test_liste_sirlarin_kendisini_dondurmez(self):
        dm.save_settings(_ornek_ayar())
        dm.save_settings(_ornek_ayar(gemini="BASKA"))

        metin = json.dumps(dm.list_settings_backups(), ensure_ascii=False)
        assert "AIzaSyGIZLI" not in metin
        assert "sifreli-veri" not in metin
        assert "0xABC" not in metin

    def test_liste_hangi_bolumun_dolu_oldugunu_soyler(self):
        """Kullanıcı doğru yedeği seçebilmeli — anahtarı görmeden."""
        dm.save_settings(_ornek_ayar())
        dm.save_settings(dm.DEFAULT_SETTINGS)

        # Liste yeniden eskiye sıralı; en yeni artık MEVCUT (boş) hâl.
        # Kullanıcı doğru yedeği tam da `contents` alanına bakarak seçer.
        hepsi = dm.list_settings_backups()
        assert hepsi[0]["contents"]["gemini_api_key"] is False
        dolu = [b for b in hepsi if b["contents"]["gemini_api_key"]]
        assert dolu, "anahtarlı hâl hiçbir yedekte yok"
        y = dolu[0]["contents"]
        assert y["gemini_api_key"] is True
        assert y["connections"] == 1
        assert y["vault_entries"] == 1
        assert y["pin_enabled"] is True

    def test_liste_yeniden_eskiye_siralidir(self):
        dm.save_settings(_ornek_ayar())
        dm.save_settings(_ornek_ayar(gemini="B"))
        dm.save_settings(_ornek_ayar(gemini="C"))

        adlar = [y["name"] for y in dm.list_settings_backups()]
        assert adlar == sorted(adlar, reverse=True)


# =====================================================================
# 4. GERİ YÜKLEME
# =====================================================================
class TestGeriYukleme:

    def test_geri_yukleme_once_mevcudu_yedekler(self):
        """Yanlış yedeği seçmek de geri alınabilir olmalı."""
        dm.save_settings(_ornek_ayar(gemini="ESKI"))
        dm.save_settings(_ornek_ayar(gemini="SIMDIKI"))

        hedef = next(y["name"] for y in dm.list_settings_backups()
                     if _yedekteki_gemini(y["name"]) == "ESKI")
        sonuc = dm.restore_settings_backup(hedef)
        assert sonuc["previous_backup"], "geri yüklemeden önce yedek alınmamış"
        assert dm.load_settings()["api_keys"]["gemini_api_key"] == "ESKI"

    def test_dizin_disina_cikilamaz(self):
        """`../` ile proje dosyalarına uzanılamamalı."""
        for kotu in ("../../../etc/passwd", "..\\..\\portfolio.json",
                     "portfolio.json", "settings_backup_x.txt"):
            with pytest.raises((ValueError, FileNotFoundError)):
                dm.restore_settings_backup(kotu)

    def test_olmayan_yedek_hata_verir(self):
        with pytest.raises(FileNotFoundError):
            dm.restore_settings_backup("settings_backup_20200101_000000.json")

    def test_bozuk_yedek_geri_yuklenmez(self):
        dm.save_settings(_ornek_ayar())
        dm.save_settings(_ornek_ayar(gemini="SAGLAM"))

        ad = dm.list_settings_backups()[0]["name"]
        with open(os.path.join(dm.BACKUP_DIR, ad), "w", encoding="utf-8") as f:
            f.write("{bu json degil")

        with pytest.raises(Exception):
            dm.restore_settings_backup(ad)
        # Mevcut ayarlar bozulmamış olmalı
        assert dm.load_settings()["api_keys"]["gemini_api_key"] == "SAGLAM"


# =====================================================================
# 5. ATOMİK YAZIM
# =====================================================================
def test_ayar_yazimi_atomik():
    """Yarım yazılmış ayar dosyası, olmayandan kötüdür: `load_settings` onu
    okuyamaz ve sessizce varsayılanlara döner — yani bugünkü kaybın aynısı."""
    import inspect
    kaynak = inspect.getsource(dm.save_settings)
    assert ".tmp" in kaynak and "os.replace" in kaynak, \
        "save_settings atomik yazmıyor"


# =====================================================================
# 6. UÇ NOKTALAR
# =====================================================================
def test_yedek_listeleme_ucu(client):
    y = client.get("/api/settings/backups")
    assert y.status_code == 200
    assert "backups" in y.json()


def test_geri_yukleme_ucu(client):
    dm.save_settings(_ornek_ayar(gemini="UCTAN"))
    dm.save_settings(dm.DEFAULT_SETTINGS)

    ad = next(y["name"] for y in dm.list_settings_backups()
              if y["contents"]["gemini_api_key"])
    y = client.post(f"/api/settings/backups/{ad}/restore")
    assert y.status_code == 200
    assert y.json()["success"] is True
    assert dm.load_settings()["api_keys"]["gemini_api_key"] == "UCTAN"


def test_olmayan_yedek_ucu_404(client):
    y = client.post("/api/settings/backups/settings_backup_20200101_000000.json/restore")
    assert y.status_code == 404


# =====================================================================
# 7. ARAYÜZ — görünmeyen yedek, olmayan yedektir
# =====================================================================
def _static(ad):
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(kok, "app", "static", ad), encoding="utf-8") as f:
        return f.read()


def test_yedek_paneli_arayuzde_var():
    html = _static("index.html")
    assert "Ayar Yedekleri" in html
    for parca in ("fetchSettingsBackups()", "restoreSettingsBackup(b)",
                  "settingsBackupSummary(b)"):
        assert parca in html, f"panel '{parca}' ile bağlanmamış"


def test_arayuz_metotlari_tanimli():
    js = _static("app.js")
    for m in ("async fetchSettingsBackups()", "async restoreSettingsBackup(b)",
              "settingsBackupSummary(b)"):
        assert m in js, f"app.js '{m}' tanımlamıyor"


def test_geri_yukleme_tarayici_confirm_kullanmaz():
    """Proje kuralı: tarayıcının confirm/alert kutuları kullanılmaz;
    uygulama içi onay penceresi var."""
    js = _static("app.js")
    bas = js.index("async restoreSettingsBackup(b)")
    blok = js[bas:bas + 2000]
    assert "askConfirm(" in blok, "geri yükleme onaysız çalışıyor"
    for yasak in ("confirm(", "alert(", "prompt("):
        # `askConfirm(` içindeki 'Confirm' eşleşmesin diye kelime başına bak
        assert f" {yasak}" not in blok and f"window.{yasak}" not in blok, \
            f"tarayıcı diyaloğu kullanılmış: {yasak}"
