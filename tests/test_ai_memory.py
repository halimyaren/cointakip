"""
YZ analizinin hafızası, çerçevesi ve arşivi.

NEDEN VAR
---------
Kullanıcı üst üste günlerde analiz istedi ve model her seferinde aynı şeyi
söyledi: *"BTC bakiyenin %25'ini limit emirle sat (~55 USDT)"*. Oysa kullanıcı
bunu 24 Ağustos'ta ZATEN yapmıştı ve deftere notunu bile düşmüştü:
`"Gerçekleşen Kısmi Satış @$79000.0000 YZ Önerisi"`.

Üç ayrı kusur vardı:

1. **Raporlar hiç saklanmıyordu.** Yalnızca tarayıcı belleğindeydiler; sayfa
   yenilenince kayboluyorlardı. Ne kullanıcı geri okuyabiliyordu ne de model
   kendi geçmişini görebiliyordu.

2. **Bağlamda geçmiş yoktu.** Modele yalnızca AÇIK pozisyonlar ve KPI'lar
   gidiyordu. Kapanmış satışlar, gerçekleşmiş K/Z ve kullanıcının önceki
   tavsiyeyi uygulayıp uygulamadığı hiç gitmiyordu.

3. **Çerçeve yoktu.** "Serbest nakit kasasını büyüt" talimatı vardı ama
   "yeterli" kavramı yoktu (kullanıcının nakdi zaten kasasının ~%49'uydu) ve
   işlem büyüklüğü eşiği yoktu ($220'lık pozisyonun %25'i ~$55 eder).

ÖNEMLİ AYRIM — bu testlerin savunduğu şey "model her seferinde farklı şey
söylesin" DEĞİL. Koşullar değişmediyse aynı tavsiyeyi tekrar vermesi doğrudur.
Savunulan şey, modelin gereken olguları GÖRMESİ ve tekrarı GİZLEMEMESİ.

Hiçbir test Gemini API'sine çıkmaz; `load_settings` boş anahtar döndürecek
şekilde değiştirilir ve yerel kural motoru kullanılır.
"""

import copy

import pytest

import archive
import ai_service
import data_manager as dm


# ===========================================================================
# GERÇEK VAKA: kullanıcının BTC defteri
# ===========================================================================

def _btc_defteri():
    """4 açık lot + YZ önerisiyle yapılmış 1 kapanmış satış.

    Sayılar kullanıcının gerçek defterinden. 0.00269 BTC × $81.788 ≈ $220;
    %25'i ≈ $55 — modelin tekrar tekrar önerdiği işlem tam olarak buydu.
    """
    return {
        "wallets": {"usdt_cash": 1220.31,
                    "exchange_cash": {"BINANCE": 1220.31}},
        "transactions": [
            {"id": 1, "date": "2026-08-22", "coin": "BTCUSDT", "exchange": "BINANCE",
             "qty": 0.00079, "cost": 60000.0, "status": "Aktif"},
            {"id": 2, "date": "2026-08-22", "coin": "BTCUSDT", "exchange": "BINANCE",
             "qty": 0.00067, "cost": 75467.0, "status": "Aktif"},
            {"id": 3, "date": "2026-08-22", "coin": "BTCUSDT", "exchange": "BINANCE",
             "qty": 0.00065, "cost": 78070.0, "status": "Aktif"},
            {"id": 4, "date": "2026-08-22", "coin": "BTCUSDT", "exchange": "BINANCE",
             "qty": 0.00058, "cost": 87200.0, "status": "Aktif"},
            # Kullanıcının YZ tavsiyesiyle yaptığı satış — notu kritik.
            {"id": 5, "date": "2026-08-22", "coin": "BTCUSDT", "exchange": "BINANCE",
             "qty": 0.00089, "cost": 74083.0, "status": "Kapandı / İzleme",
             "exit_price": 79000.0, "exit_date": "2026-08-24", "exit_value": 70.31,
             "realized_pnl_usd": 4.32, "fee_usd": 0.0527,
             "notes": "Gerçekleşen Kısmi Satış @$79000.0000 YZ Önerisi"},
        ],
        "targets": {},
    }


BTC_FIYAT = {"BTCUSDT": {"price": 81788.0, "open_price": 81000.0,
                         "change_pct": 1.0, "source": "TEST"}}


@pytest.fixture
def yz(monkeypatch):
    """Gemini'siz danışman. API anahtarı YOK → yerel kural motoru çalışır."""
    monkeypatch.setattr(ai_service, "load_settings", lambda: {"api_keys": {}})
    return ai_service.AIFinancialAdvisor()


@pytest.fixture
def btc_kurulu(monkeypatch):
    defter = _btc_defteri()
    dm.save_portfolio(defter)
    monkeypatch.setattr(ai_service, "load_portfolio", lambda: copy.deepcopy(defter))
    monkeypatch.setattr(ai_service.price_service, "get_prices", lambda: dict(BTC_FIYAT))
    return defter


# ===========================================================================
# 1. ARŞİV
# ===========================================================================

class TestRaporArsivi:

    def test_rapor_uretilince_arsivlenir(self, yz, btc_kurulu):
        assert archive.ai_report_count() == 0
        sonuc = yz.analyze(mode="take_profit")

        assert sonuc["archived"] is True
        assert isinstance(sonuc["report_id"], int)
        assert archive.ai_report_count() == 1

    def test_arsivden_tam_metin_okunur(self, yz, btc_kurulu):
        sonuc = yz.analyze(mode="full_audit")
        kayit = archive.get_ai_report(sonuc["report_id"])

        assert kayit["report_markdown"] == sonuc["report_markdown"]
        assert kayit["mode"] == "full_audit"
        assert kayit["source"] == "LOCAL_EXPERT_ENGINE"

    def test_liste_metin_tasimaz(self, yz, btc_kurulu):
        """Liste hafif kalmalı; tam metinler ayrı uçtan çekiliyor."""
        yz.analyze(mode="full_audit")
        kayitlar = archive.list_ai_reports()
        assert len(kayitlar) == 1
        assert "report_markdown" not in kayitlar[0]

    def test_moda_gore_suzulur(self, yz, btc_kurulu):
        yz.analyze(mode="full_audit")
        yz.analyze(mode="take_profit")
        yz.analyze(mode="take_profit")

        assert len(archive.list_ai_reports()) == 3
        assert len(archive.list_ai_reports(mode="take_profit")) == 2
        assert len(archive.list_ai_reports(mode="recovery")) == 0

    def test_yeniden_eskiye_siralanir(self, yz, btc_kurulu):
        ilk = yz.analyze(mode="full_audit")["report_id"]
        son = yz.analyze(mode="full_audit")["report_id"]
        kayitlar = archive.list_ai_reports()
        assert [k["id"] for k in kayitlar] == [son, ilk]

    def test_silinebilir(self, yz, btc_kurulu):
        rid = yz.analyze(mode="full_audit")["report_id"]
        assert archive.delete_ai_report(rid) is True
        assert archive.get_ai_report(rid) is None
        assert archive.delete_ai_report(rid) is False

    def test_kasa_fotografi_saklanir(self, yz, btc_kurulu):
        """Rapor, yazıldığı günün koşullarıyla okunabilmeli."""
        sonuc = yz.analyze(mode="take_profit")
        ozet = archive.get_ai_report(sonuc["report_id"])["portfolio_digest"]

        assert ozet["cash"] == pytest.approx(1220.31)
        assert ozet["cash_ratio_pct"] > 0
        assert "BTCUSDT" in ozet["positions"]

    def test_veritabani_bozuksa_kendi_hatasini_yutar(self, yz, btc_kurulu, monkeypatch):
        """Arşiv konfor katmanı; kritik yolu ASLA düşürmemeli.

        `archive.py` tasarım kuralı 1: her giriş noktası kendi hatasını yutar.
        Burada gerçek bir arıza üretiliyor (bağlantı açılamıyor) ve fonksiyonun
        istisna fırlatmak yerine None döndürdüğü doğrulanıyor.
        """
        def bozuk_baglanti(*a, **k):
            raise OSError("disk dolu")
        monkeypatch.setattr(archive, "_connect", bozuk_baglanti)

        # Fırlatmamalı, None dönmeli.
        assert archive.save_ai_report(mode="full_audit", report_markdown="x") is None
        assert archive.list_ai_reports() == []
        assert archive.last_ai_report() is None
        assert archive.get_ai_report(1) is None
        assert archive.ai_report_count() == 0

    def test_arsivlenemese_bile_rapor_kullaniciya_doner(self, yz, btc_kurulu, monkeypatch):
        """Kaydetme başarısız olsa da kullanıcı raporunu görmeli."""
        monkeypatch.setattr(archive, "save_ai_report", lambda **k: None)

        sonuc = yz.analyze(mode="full_audit")
        assert sonuc["success"] is True
        assert sonuc["report_markdown"].strip()
        assert sonuc["archived"] is False
        assert sonuc["report_id"] is None

    def test_bos_rapor_arsivlenmez(self):
        assert archive.save_ai_report(mode="full_audit", report_markdown="") is None
        assert archive.save_ai_report(mode="full_audit", report_markdown="   ") is None
        assert archive.ai_report_count() == 0


# ===========================================================================
# 2. BAĞLAMDA GEÇMİŞ
# ===========================================================================

class TestBaglamdaGecmis:

    def test_kapanmis_satislar_gonderiliyor(self, yz, btc_kurulu):
        ctx = yz.get_portfolio_context()
        gecmis = ctx["realized_history"]

        assert gecmis["closed_tx_count"] == 1
        assert len(gecmis["recent_closed_trades"]) == 1

    def test_yz_onerisi_notu_modele_ulasiyor(self, yz, btc_kurulu):
        """ASIL MESELE.

        Kullanıcının modelin tavsiyesini uyguladığını gösteren tek kanıt bu
        not. Gitmezse model kendi önerisinin yapıldığını göremez.
        """
        ctx = yz.get_portfolio_context()
        islem = ctx["realized_history"]["recent_closed_trades"][0]

        assert "YZ Önerisi" in islem["notes"]
        assert islem["exit_date"] == "2026-08-24"
        assert islem["realized_pnl_usd"] == pytest.approx(4.32, abs=0.01)

    def test_ilk_analizde_onceki_yok(self, yz, btc_kurulu):
        assert yz.get_portfolio_context()["previous_analysis"] is None

    def test_ikinci_analiz_oncekini_gorur(self, yz, btc_kurulu):
        ilk = yz.analyze(mode="take_profit")
        ikinci_ctx = yz.get_portfolio_context()

        onceki = ikinci_ctx["previous_analysis"]
        assert onceki is not None
        assert onceki["mode"] == "take_profit"
        assert onceki["report_excerpt"]
        # Modele ne yapması gerektiği açıkça söylenmeli.
        assert "tekrar" in onceki["note"].lower()

        ikinci = yz.analyze(mode="take_profit")
        assert ikinci["previous_report_at"] is not None
        assert ikinci["report_id"] != ilk["report_id"]

    def test_onceki_rapor_kisaltiliyor(self, yz, btc_kurulu, monkeypatch):
        """Tam metni geri göndermek istemi şişirir; kullanıcı kota sınırında."""
        uzun = "A" * 50000
        archive.save_ai_report(mode="full_audit", report_markdown=uzun,
                               source="TEST", model_name="TEST")
        onceki = yz.get_portfolio_context()["previous_analysis"]

        assert len(onceki["report_excerpt"]) <= archive.ONCEKI_RAPOR_KARAKTER_SINIRI + 40
        assert "kisaltildi" in onceki["report_excerpt"]

    def test_nakit_orani_hesaplaniyor(self, yz, btc_kurulu):
        """'Daha çok nakit yap' tavsiyesinin çerçevesi."""
        ctx = yz.get_portfolio_context()
        beklenen = ctx["total_usdt_cash"] / ctx["total_equity"] * 100.0
        assert ctx["cash_ratio_pct"] == pytest.approx(beklenen, abs=0.1)
        # Kullanıcının gerçek durumu: nakit ağırlıklı bir kasa.
        assert ctx["cash_ratio_pct"] > 50


# ===========================================================================
# 3. İŞLEM BÜYÜKLÜĞÜ ÇERÇEVESİ
# ===========================================================================

class TestIslemBuyuklugu:

    def test_pozisyon_esigi_tek_basina_bu_vakayi_kacirir(self, yz, btc_kurulu):
        """İlk denemede yapılan hatanın kalıcı kaydı.

        BTC pozisyonu ~$220; yalnızca pozisyon büyüklüğüne bakan bir eşik
        ($150) bunu "yeterince büyük" sayıp geçiyordu. Oysa şikâyete konu olan
        şey pozisyon değil, önerilen %25'lik satıştı (~$55).
        """
        btc = self._btc(yz)
        assert btc["current_value"] > ai_service.MIN_POZISYON_DEGERI_USD
        assert btc["too_small_to_trade"] is False

    def test_islem_tutari_esigi_vakayi_yakalar(self, yz, btc_kurulu):
        btc = self._btc(yz)
        assert btc["value_of_25pct_usd"] == pytest.approx(55.0, abs=0.5)
        assert btc["partial_sale_not_worth_it"] is True

    def test_yerel_rapor_kismi_satis_onermiyor(self, yz, btc_kurulu):
        """Kullanıcının şikâyet ettiği cümlenin artık üretilmediğinin kanıtı."""
        rapor = yz.analyze(mode="take_profit")["report_markdown"]
        assert "Kısmi satış önerilmez" in rapor
        assert "%25-%35 Kısmi Satış" not in rapor

    def test_buyuk_pozisyonda_kismi_satis_hala_onerilir(self, yz, monkeypatch):
        """Eşik her şeyi susturmamalı — büyük pozisyonda öneri sürmeli."""
        defter = _btc_defteri()
        for t in defter["transactions"]:
            if t["status"] == "Aktif":
                t["qty"] *= 50            # ~$11.000'lık pozisyon
        dm.save_portfolio(defter)
        monkeypatch.setattr(ai_service, "load_portfolio", lambda: copy.deepcopy(defter))
        monkeypatch.setattr(ai_service.price_service, "get_prices", lambda: dict(BTC_FIYAT))

        rapor = yz.analyze(mode="take_profit")["report_markdown"]
        assert "%25-%35 Kısmi Satış" in rapor

    def test_nakit_orani_yuksekse_uyari_cikar(self, yz, btc_kurulu):
        rapor = yz.analyze(mode="take_profit")["report_markdown"]
        assert "zaten nakit" in rapor

    def _btc(self, yz):
        return [c for c in yz.get_portfolio_context()["coins"]
                if c["symbol"] == "BTCUSDT"][0]


# ===========================================================================
# 4. SÜREKLİLİK BLOĞU (yerel motor)
# ===========================================================================

class TestSureklilikBlogu:

    def test_ilk_raporda_blok_yok(self, yz, btc_kurulu):
        rapor = yz.analyze(mode="full_audit")["report_markdown"]
        assert "Önceki Analize Göre" not in rapor

    def test_ikinci_raporda_blok_var(self, yz, btc_kurulu):
        yz.analyze(mode="full_audit")
        rapor = yz.analyze(mode="full_audit")["report_markdown"]

        assert "Önceki Analize Göre Ne Değişti" in rapor
        assert "Nakit oranı" in rapor

    def test_uygulanmamis_oneri_acikca_soylenir(self, yz, btc_kurulu):
        """Kullanıcının asıl şikâyeti buydu: tekrar gizleniyordu."""
        yz.analyze(mode="take_profit")
        rapor = yz.analyze(mode="take_profit")["report_markdown"]
        assert "uygulanmamış görünüyor" in rapor

    def test_rapordan_sonra_kapanan_islem_listelenir(self, yz, btc_kurulu, monkeypatch):
        """Kullanıcı tavsiyeyi uygularsa rapor bunu teyit etmeli."""
        yz.analyze(mode="take_profit")

        defter = copy.deepcopy(btc_kurulu)
        defter["transactions"].append({
            "id": 99, "date": "2026-08-22", "coin": "BTCUSDT", "exchange": "BINANCE",
            "qty": 0.0005, "cost": 74000.0, "status": "Kapandı / İzleme",
            "exit_price": 81788.0, "exit_date": "2099-01-01", "exit_value": 40.89,
            "realized_pnl_usd": 3.89,
            "notes": "Gerçekleşen Kısmi Satış @$81788 YZ Önerisi",
        })
        monkeypatch.setattr(ai_service, "load_portfolio", lambda: copy.deepcopy(defter))

        rapor = yz.analyze(mode="take_profit")["report_markdown"]
        assert "O tarihten beri kapanan işlemler" in rapor
        assert "YZ Önerisi" in rapor
        assert "uygulanmamış görünüyor" not in rapor

    def test_kasa_degisimi_gosterilir(self, yz, btc_kurulu, monkeypatch):
        yz.analyze(mode="full_audit")
        # Nakdi artır → kasa değişti
        defter = copy.deepcopy(btc_kurulu)
        defter["wallets"]["usdt_cash"] = 1500.0
        defter["wallets"]["exchange_cash"]["BINANCE"] = 1500.0
        monkeypatch.setattr(ai_service, "load_portfolio", lambda: copy.deepcopy(defter))

        rapor = yz.analyze(mode="full_audit")["report_markdown"]
        assert "**Kasa:**" in rapor


# ===========================================================================
# 5. ÖLÜ ALAN TEMİZLİĞİ
# ===========================================================================

class TestOluAlan:

    def test_is_dead_alani_kaldirildi(self, yz, btc_kurulu):
        """`data_manager` bu alanı hiç üretmiyordu; modele hep False gidiyordu.

        Ölü alan, dolu alan gibi okunur. Yerine ölçütün kendisi kondu.
        """
        btc = [c for c in yz.get_portfolio_context()["coins"]
               if c["symbol"] == "BTCUSDT"][0]
        assert "is_dead" not in btc
        assert "deeply_underwater" in btc
        assert btc["deeply_underwater"] is False


# ===========================================================================
# 6. GEMINI'YE ÇIKILMADIĞININ KANITI
# ===========================================================================

class TestAgaCikilmiyor:

    def test_hicbir_test_gemini_cagirmaz(self, yz, btc_kurulu, monkeypatch):
        """Çalışma kuralı: hiçbir test Gemini API'sine istek atmaz."""
        def patla(*a, **k):
            raise AssertionError("Test Gemini API'sine çıkmaya çalıştı!")
        monkeypatch.setattr(ai_service.urllib.request, "urlopen", patla)

        sonuc = yz.analyze(mode="full_audit")
        assert sonuc["source"] == "LOCAL_EXPERT_ENGINE"
