"""
İşlem numarası bütünlüğü — 9 Eylül 2026 çakışması.

NE OLDU
-------
Defterde aynı numarayı taşıyan kayıtlar bulundu. Numara üretmek iki ayrı
yoldan yapılıyordu ve ikisi birbirinden habersizdi:

  * `data_manager` içindeki toplu ekleme yolları `max(numaralar)+1`
    hesaplıyor ama `next_tx_id` sayacını İLERLETMİYORDU;
  * `main.py` ve `trade_sync.py` ise YALNIZCA sayacı okuyordu.

Mutabakat düzeltmeleri numaraları 145'e çıkarırken sayaç 74'te dondu.
Sonraki her yeni kayıt var olan bir numarayı aldı: 31 Ağustos'ta zincirden
okunan bir SOL kaydı 74'ü, 9 Eylül'de borsadan yakalanan bir ARB alımı 75'i.

NEDEN CİDDİ
-----------
Numaraya göre arama yapan uçlar (`sell`, `düzenle`, `durum değiştir`)
listede İLK eşleşeni bulup duruyor ve eski kayıtlar listede önce geliyor.
Yani kullanıcı yeni ARB lotunu satmaya kalksa, sistem onun yerine kapanmış
bir transfer kaydını işleme alırdı. Gerçek parayla ilgili bir defterde bu,
sessizce yanlış pozisyonu kapatmak demektir.

Buradaki testler üç katmanı da ayrı ayrı kilitler: numara üreticinin
kendisi, kaydetme anındaki eşitleme ve bütünlük denetimi.
"""

import pytest

import data_manager as dm
import trade_sync


def _defter(kayitlar, next_tx_id):
    """Verilen numaralara sahip bir defter."""
    return {
        "wallets": {"usdt_cash": 1000.0, "exchange_cash": {"BINANCE": 1000.0}},
        "settings": {"currency": "USD", "default_exchange": "BINANCE"},
        "transactions": [
            {"id": no, "date": "2026-08-22", "coin": "RDNTUSDT",
             "exchange": "BINANCE", "qty": 10.0, "cost": 1.0,
             "status": "Aktif", "notes": "", "category": "Altcoin"}
            for no in kayitlar
        ],
        "next_tx_id": next_tx_id,
        "targets": {},
    }


# =====================================================================
# Katman 1 — numara üreticisi
# =====================================================================
class TestNumaraUreticisi:

    def test_bayat_sayac_cakisan_numara_veremez(self):
        """Asıl hata buydu: sayaç 74'te donmuşken defterde 145'e kadar
        numara vardı ve sayaca bakmak var olan bir numara veriyordu."""
        defter = _defter(list(range(1, 146)), next_tx_id=74)
        assert dm._sonraki_tx_id(defter) == 146

    def test_sayac_ileridiyse_ona_uyulur(self):
        """Sayaç ileriyse geri dönmek, silinmiş bir kaydın numarasını
        yeniden kullanmak olurdu."""
        defter = _defter([1, 2, 3], next_tx_id=99)
        assert dm._sonraki_tx_id(defter) == 99

    def test_bos_defterde_birden_baslar(self):
        assert dm._sonraki_tx_id({"transactions": [], "next_tx_id": 0}) == 1

    def test_sayac_yoksa_defterden_hesaplanir(self):
        defter = {"transactions": [{"id": 7}]}
        assert dm._sonraki_tx_id(defter) == 8

    def test_uretilen_numara_hic_kullanilmamis_olur(self):
        defter = _defter(list(range(1, 146)), next_tx_id=74)
        mevcut = {t["id"] for t in defter["transactions"]}
        assert dm._sonraki_tx_id(defter) not in mevcut


# =====================================================================
# Katman 2 — kaydetme anındaki eşitleme
# =====================================================================
class TestSayacEsitlemesi:

    def test_kaydetme_sayaci_gercekle_esitler(self):
        """Hangi kod yolu kayıt eklerse eklesin sayaç gerçeğe yakınsamalı."""
        defter = _defter(list(range(1, 146)), next_tx_id=74)
        dm.save_portfolio(defter)
        assert dm.load_portfolio()["next_tx_id"] == 146

    def test_sayac_geriye_cekilmez(self):
        """Geri çekmek, silinmiş kayıtların numaralarını yeniden dağıtır."""
        defter = _defter([1, 2, 3], next_tx_id=500)
        dm.save_portfolio(defter)
        assert dm.load_portfolio()["next_tx_id"] == 500

    def test_esitleme_kayitlara_dokunmaz(self):
        defter = _defter([1, 2, 3], next_tx_id=74)
        dm.tx_id_sayacini_esitle(defter)
        assert [t["id"] for t in defter["transactions"]] == [1, 2, 3]


# =====================================================================
# Katman 3 — bütünlük denetimi
# =====================================================================
class TestCakismaDenetimi:

    def test_cakisma_bildirilir(self):
        """Bu kusur 9 gün görünmedi çünkü hiçbir yer bakmıyordu."""
        defter = _defter([1, 2, 2, 3, 3], next_tx_id=4)
        assert dm.cakisan_tx_id_var_mi(defter) == [2, 3]

    def test_saglam_defterde_bos_doner(self):
        assert dm.cakisan_tx_id_var_mi(_defter([1, 2, 3], 4)) == []

    def test_bos_defter_saglamdir(self):
        assert dm.cakisan_tx_id_var_mi({"transactions": []}) == []


# =====================================================================
# Gerçek senaryo — 9 Eylül 2026
# =====================================================================
class TestCakismaSenaryosu:
    """Hatanın gerçekleştiği iki yol da ayrı ayrı sınanır: kullanıcının elle
    eklemesi ve borsadan yakalanan alımın işlenmesi."""

    def test_elle_eklenen_kayit_cakismaz(self, client):
        dm.save_portfolio(_defter(list(range(1, 146)), next_tx_id=74))
        yanit = client.post("/api/transactions", json={
            "date": "2026-09-09", "coin": "ARBUSDT", "exchange": "BINANCE",
            "qty": 91.3, "cost": 0.151, "category": "Altcoin",
        })
        assert yanit.status_code == 200
        defter = dm.load_portfolio()
        assert dm.cakisan_tx_id_var_mi(defter) == []

    def test_borsadan_yakalanan_alim_cakismaz(self, monkeypatch):
        """9 Eylül'deki ARB alımı tam olarak bu yoldan geldi ve kapanmış bir
        transfer kaydıyla aynı numarayı aldı."""
        dm.save_portfolio(_defter(list(range(1, 146)), next_tx_id=74))

        servis = trade_sync.TradeSyncService()
        olay = {
            "event_uid": "BINANCE:trade:ARBUSDT:1", "exchange": "BINANCE",
            "kind": trade_sync.TRADE, "symbol": "ARBUSDT",
            "base_asset": "ARB", "quote_asset": "USDT", "side": "BUY",
            "qty": 91.3, "price": 0.151, "quote_qty": 13.7863,
            "fee_asset": "BNB", "fee_qty": 1.399e-05,
            "trade_at": "2026-09-09T19:53:19", "trade_ts": 1789000000.0,
        }
        servis._alimi_isle(olay, "BINANCE", "ARBUSDT", 91.3, 0.151,
                           "2026-09-09", dm.load_portfolio, dm.save_portfolio,
                           dm.DEFAULT_CATEGORIES)

        defter = dm.load_portfolio()
        assert dm.cakisan_tx_id_var_mi(defter) == []
        yeni = [t for t in defter["transactions"] if t["coin"] == "ARBUSDT"]
        assert len(yeni) == 1 and yeni[0]["id"] == 146

    def test_pes_pese_eklemeler_de_cakismaz(self, client):
        """Sayaç bir kez düzeldikten sonra da düzgün ilerlemeli."""
        dm.save_portfolio(_defter(list(range(1, 146)), next_tx_id=74))
        for i in range(3):
            client.post("/api/transactions", json={
                "date": "2026-09-09", "coin": f"AAA{i}USDT",
                "exchange": "BINANCE", "qty": 1.0, "cost": 1.0,
                "category": "Altcoin"})
        defter = dm.load_portfolio()
        assert dm.cakisan_tx_id_var_mi(defter) == []
        assert len(defter["transactions"]) == 148

    def test_numaraya_gore_arama_dogru_kaydi_bulur(self, client):
        """Çakışmanın asıl zararı buydu: arama listede ilk eşleşeni bulup
        duruyor ve eski kayıt önce geliyor."""
        dm.save_portfolio(_defter(list(range(1, 146)), next_tx_id=74))
        yanit = client.post("/api/transactions", json={
            "date": "2026-09-09", "coin": "ARBUSDT", "exchange": "BINANCE",
            "qty": 91.3, "cost": 0.151, "category": "Altcoin"})
        yeni_no = yanit.json().get("transaction", {}).get("id") \
            or [t for t in dm.load_portfolio()["transactions"]
                if t["coin"] == "ARBUSDT"][0]["id"]

        bulunan = [t for t in dm.load_portfolio()["transactions"]
                   if t["id"] == yeni_no]
        assert len(bulunan) == 1
        assert bulunan[0]["coin"] == "ARBUSDT"


class TestAcilistaDenetim:
    """Kusurun dokuz gün görünmemesinin sebebi hiçbir yerin bakmamasıydı."""

    def test_cakisma_varsa_loglanir(self, caplog, monkeypatch):
        import logging
        import main

        dm.save_portfolio(_defter([1, 2, 2], next_tx_id=3))
        # `save_portfolio` sayacı düzeltir ama çakışan kayıtları DEĞİŞTİRMEZ;
        # denetimin görmesi gereken durum tam olarak budur.
        with caplog.at_level(logging.ERROR, logger="cointakip"):
            main._tx_id_butunlugunu_denetle()
        assert any("DEFTER UYARISI" in r.message for r in caplog.records)

    def test_saglam_defterde_susulur(self, caplog):
        import logging
        import main

        dm.save_portfolio(_defter([1, 2, 3], next_tx_id=4))
        with caplog.at_level(logging.ERROR, logger="cointakip"):
            main._tx_id_butunlugunu_denetle()
        assert not any("DEFTER UYARISI" in r.message for r in caplog.records)

    def test_defter_okunamazsa_patlamaz(self, monkeypatch):
        """Denetim, açılışı engelleyecek bir risk olmamalı."""
        import main

        def patla():
            raise RuntimeError("defter bozuk")

        monkeypatch.setattr(main, "load_portfolio", patla)
        main._tx_id_butunlugunu_denetle()      # sessizce geçmeli
