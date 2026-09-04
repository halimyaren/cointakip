import os
import json
import urllib.request
import urllib.parse
from datetime import datetime
from data_manager import (
    load_settings, load_portfolio, calculate_portfolio_metrics,
    calculate_realized_metrics,
)
from price_service import price_service
from log_config import get_logger

import archive

logger = get_logger("ai_service")


# ===========================================================================
# MODELE VERİLEN ÇERÇEVE
#
# Gerçek bir kullanım hatasından doğdu. Kullanıcı üst üste günlerde analiz
# istedi ve model her seferinde aynı şeyi söyledi: "BTC bakiyenin %25'ini
# sat (~55 USDT)". Oysa kullanıcı 24 Ağustos'ta bunu ZATEN yapmıştı ve
# deftere notunu bile düşmüştü: "Gerçekleşen Kısmi Satış @$79000 YZ Önerisi".
#
# İki ayrı eksik vardı:
#
# 1. GEÇMİŞ YOK. `get_portfolio_context` yalnızca AÇIK pozisyonları ve
#    KPI'ları yolluyordu. Kapanmış satışlar, gerçekleşmiş K/Z ve modelin
#    kendi önceki raporu hiç gitmiyordu. Model ne dediğini de, kullanıcının
#    ne yaptığını da bilemiyordu.
#
# 2. ÇERÇEVE YOK. `take_profit` talimatı "serbest nakit kasasını büyüt"
#    diyordu ama "yeterli" diye bir kavram vermiyordu. Kullanıcının nakdi
#    zaten kasasının ~%49'uydu. Böyle bir talimat alan model her seferinde
#    satacak bir şey bulur — işi bu. Ayrıca asgari pozisyon büyüklüğü
#    eşiği olmadığı için $220'lık bir pozisyonun %25'ini satmayı, yani
#    ~$55 için işlem yapmayı öneriyordu.
#
# ÖNEMLİ AYRIM: amaç modeli "tutarlı" olmaya zorlamak DEĞİL. Koşullar
# değişmediyse aynı tavsiyeyi tekrar vermesi doğrudur; kendini tekrar
# etmemek için tavsiye değiştiren bir model, taze görünmek adına yeni işlem
# sebepleri uydurur ve bu daha kötüdür. Amaç tekrarı GÖRÜNÜR kılmak.
# ===========================================================================

# İki ayrı eşik, çünkü iki ayrı soru var.
#
# MIN_POZISYON_DEGERI_USD — pozisyonun kendisi bu kadar küçükse onunla
#   uğraşmaya değmez; kısmi işlem değil, "kapat ya da dokunma" denir.
#
# MIN_ISLEM_TUTARI_USD — asıl mesele bu. Şikâyete konu olan vakada pozisyon
#   ~$220'dı, yani "küçük pozisyon" eşiğini rahatça geçiyordu; ama modelin
#   önerdiği %25'lik satış ~$55 ediyordu. Sorun pozisyonun büyüklüğü değil,
#   ÖNERİLEN İŞLEMİN büyüklüğüydü. Sadece pozisyona bakan bir eşik bu vakayı
#   kaçırıyor — ilk denemede tam olarak bu oldu.
#
# İkisi de kullanıcının kasa ölçeğine (~$2.5K) göre seçildi; dogma değil.
MIN_POZISYON_DEGERI_USD = 150.0
MIN_ISLEM_TUTARI_USD = 75.0

# Kısmi satış önerileri tipik olarak bu oranda yapılıyor; "önerilen işlem ne
# kadar eder" sorusunu somutlaştırmak için kullanılıyor.
TIPIK_KISMI_SATIS_ORANI = 0.25

# Modele geri verilecek kapanmış işlem sayısı. Tam liste istem boyutunu
# şişirir; kullanıcı ücretsiz Gemini katmanında.
GECMIS_ISLEM_SINIRI = 12


class AIFinancialAdvisor:
    def __init__(self):
        pass

    def get_portfolio_context(self):
        data = load_portfolio()
        prices = price_service.get_prices()
        metrics = calculate_portfolio_metrics(data, prices)

        coins_summary = []
        for c in metrics.get("consolidated_coins", []):
            # NET BAŞA BAŞ — modele MUTLAKA verilmeli. Aksi halde elindeki tek
            # başabaş göstergesi `breakeven_req_rise_pct` olur ve o yalnızca
            # AÇIK lotların maliyetine dönüşü ölçer. Geçmişte kapanmış zararlı
            # satışları olan bir coinde model "az kaldı, %73 yeter" der; oysa
            # gerçek kurtulma eşiği çok daha yukarıdadır. Yanlış sayıya dayanan
            # bir tavsiye, tavsiye vermemekten kötüdür.
            bb = c.get("net_breakeven") or {}
            bb_ozet = None
            if bb.get("history_quality") and bb.get("history_quality") != "no_history":
                bb_ozet = {
                    "net_breakeven_price": (round(bb["price"], 8)
                                            if bb.get("price") is not None else None),
                    "state": bb.get("state"),
                    "realized_pnl_usd": bb.get("realized_pnl_usd"),
                    "total_pnl_usd": bb.get("symbol_total_pnl_usd"),
                    "note": ("Bu coinde gecmis satislar var. 'avg_cost' ve "
                             "'breakeven_req_rise_pct' YALNIZCA acik lotlari anlatir; "
                             "gercek kurtulma esigi 'net_breakeven_price'dir. "
                             "Sembolun tum konumlarini birlikte kapsar."),
                }

            coins_summary.append({
                "net_breakeven": bb_ozet,
                "symbol": c.get("symbol"),
                "name": c.get("display_name"),
                "exchange": c.get("exchange", "BINANCE"),
                "category": c.get("category", "Altcoin"),
                "total_invested": round(c.get("total_invested", 0), 2),
                "current_value": round(c.get("current_value", 0), 2),
                "avg_cost": round(c.get("avg_cost", 0), 6),
                "live_price": round(c.get("live_price", 0), 6),
                "pnl_usd": round(c.get("pnl_usd", 0), 2),
                "pnl_pct": round(c.get("pnl_pct", 0), 2),
                "change_24h_pct": round(c.get("change_24h_pct", 0), 2),
                "change_7d_pct": round(c.get("change_7d_pct", 0), 2),
                "breakeven_req_rise_pct": round(c.get("breakeven_req_rise_pct", 0), 2),
                "profit_margin_pct": round(c.get("profit_margin_pct", 0), 2),
                "portfolio_share_pct": round(c.get("portfolio_share_pct", 0), 2),
                # `is_dead` KALDIRILDI: data_manager bu alanı hiç üretmiyordu,
                # yani modele her zaman False gidiyordu. Ölü alan, dolu alan
                # gibi okunuyor. Yerine ölçütün kendisi aşağıda.
                "deeply_underwater": round(c.get("pnl_pct", 0), 2) <= -50.0,
                # Pozisyonun kendisi uğraşmaya değer mi?
                "too_small_to_trade": round(c.get("current_value", 0), 2) < MIN_POZISYON_DEGERI_USD,
                # ASIL ÖLÇÜT: önerilecek kısmi satış kaç dolar eder? Model
                # $220'lık pozisyonun %25'ini satmayı öneriyordu — ~$55. Pozisyon
                # eşiğini geçiyordu ama işlem tutarı anlamsızdı.
                "value_of_25pct_usd": round(c.get("current_value", 0) * TIPIK_KISMI_SATIS_ORANI, 2),
                "partial_sale_not_worth_it": (
                    round(c.get("current_value", 0) * TIPIK_KISMI_SATIS_ORANI, 2)
                    < MIN_ISLEM_TUTARI_USD),
                "target": c.get("target")
            })

        kpis = metrics.get("kpis", {})
        exchange_cash = {
            ex_name: round(float(ex.get("usdt_cash", 0.0)), 2)
            for ex_name, ex in metrics.get("exchange_kpis", {}).items()
            if ex_name != "ALL"
        }
        context = {
            "total_spot_invested": round(kpis.get("spot_invested", 0), 2),
            "total_spot_current_value": round(kpis.get("spot_current_value", 0), 2),
            "total_usdt_cash": round(kpis.get("usdt_cash", 0), 2),
            "total_equity": round(kpis.get("total_kasa", 0), 2),
            "total_net_pnl_usd": round(kpis.get("net_pnl_usd", 0), 2),
            "total_net_pnl_pct": round(kpis.get("net_pnl_pct", 0), 2),
            "daily_diff_24h_usd": round(kpis.get("daily_diff_24h_usd", 0), 2),
            "exchange_cash": exchange_cash,
            "coins": coins_summary,
            "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # --- Nakit oranı: "daha çok nakit yap" tavsiyesinin çerçevesi ---
        # Bu sayı olmadan model her seferinde satacak bir şey buluyordu.
        toplam = context["total_equity"] or 0.0
        nakit = context["total_usdt_cash"] or 0.0
        context["cash_ratio_pct"] = round((nakit / toplam * 100.0), 1) if toplam > 0 else 0.0

        # --- Geçmiş: model ne dediğini ve kullanıcının ne yaptığını bilmeli ---
        context["realized_history"] = self._gerceklesmis_ozet(data)
        context["previous_analysis"] = self._onceki_analiz_ozeti(mode=None)
        return context

    # -------------------------------------------------------------------
    def _gerceklesmis_ozet(self, data):
        """Kapanmış işlemlerin modele gidecek özeti.

        `notes` alanı BİLEREK dahil: kullanıcı YZ önerisiyle yaptığı satışa
        deftere "YZ Önerisi" diye not düşüyor. Model kendi tavsiyesinin
        uygulandığını ancak buradan görebiliyor.
        """
        try:
            rm = calculate_realized_metrics(data) or {}
        except Exception as e:
            logger.debug("Gerçekleşmiş özet üretilemedi: %s", e)
            return {}

        islemler = []
        for t in (rm.get("closed_transactions") or [])[:GECMIS_ISLEM_SINIRI]:
            islemler.append({
                "coin": t.get("coin"),
                "exit_date": t.get("exit_date"),
                "qty": t.get("qty"),
                "exit_price": t.get("exit_price"),
                "realized_pnl_usd": t.get("realized_pnl_usd"),
                "notes": (t.get("notes") or "")[:120],
            })

        return {
            "total_realized_pnl_usd": rm.get("total_realized_pnl_usd"),
            "closed_tx_count": rm.get("closed_tx_count"),
            "win_rate_pct": rm.get("win_rate_pct"),
            "recent_closed_trades": islemler,
            "note": ("Bunlar KAPANMIS islemler. Kullanicinin gecmiste ne yaptigini "
                     "gosterir. 'notes' alaninda 'YZ Onerisi' yazan bir satis, "
                     "kullanicinin daha onceki bir YZ tavsiyesini UYGULADIGI "
                     "anlamina gelir."),
        }

    def _onceki_analiz_ozeti(self, mode=None):
        """En son üretilen raporun özeti ve o günden bu yana neyin değiştiği."""
        try:
            son = archive.last_ai_report(mode)
        except Exception as e:
            logger.debug("Önceki analiz okunamadı: %s", e)
            return None
        if not son:
            return None

        metin = (son.get("report_markdown") or "")
        kisa = metin[:archive.ONCEKI_RAPOR_KARAKTER_SINIRI]
        if len(metin) > len(kisa):
            kisa += "\n…(kisaltildi)"

        return {
            "created_at": son.get("created_at"),
            "mode": son.get("mode"),
            "portfolio_digest": son.get("portfolio_digest") or {},
            "report_excerpt": kisa,
            "note": ("Bu, EN SON verdigin rapordur. Ayni tavsiyeyi tekrar vermen "
                     "kosullar degismediyse DOGRUDUR — ama bunu acikca soyle. "
                     "Kullanicinin uygulayip uygulamadigini 'realized_history' ile "
                     "karsilastirarak anla."),
        }

    def _kasa_ozeti(self, context):
        """Rapora iliştirilen küçük kasa fotoğrafı.

        Bir sonraki analizde "geçen sefer şu haldeydi, şimdi bu halde"
        karşılaştırması buradan yapılıyor; ham geçmişi modele yollamaya gerek
        kalmıyor.
        """
        return {
            "total_equity": context.get("total_equity"),
            "cash": context.get("total_usdt_cash"),
            "cash_ratio_pct": context.get("cash_ratio_pct"),
            "spot_value": context.get("total_spot_current_value"),
            "net_pnl_usd": context.get("total_net_pnl_usd"),
            "positions": {
                c["symbol"]: {"qty_value_usd": c["current_value"],
                              "pnl_usd": c["pnl_usd"]}
                for c in (context.get("coins") or [])
            },
        }

    def analyze(self, mode: str = "full_audit", custom_question: str = ""):
        context = self.get_portfolio_context()
        settings = load_settings()
        api_key = settings.get("api_keys", {}).get("gemini_api_key", "").strip()

        if api_key:
            try:
                llm_response, model_display = self._call_gemini_api(api_key, mode, context, custom_question)
                if llm_response:
                    return self._sonuc(
                        context, mode, custom_question,
                        source="GEMINI_AI",
                        model_name=model_display or "Google Gemini AI",
                        report_markdown=llm_response,
                    )
            except Exception as e:
                logger.warning("Gemini çağrısı başarısız, yerel kural motoruna düşülüyor: %s", e)

        # Fallback to Local Algorithmic Financial Advisor
        if not api_key:
            logger.info("Gemini API anahtarı tanımlı değil — yerel kural motoru kullanılıyor (mod: %s).", mode)
        else:
            logger.info("Gemini modellerinin hiçbiri yanıt vermedi — yerel kural motoruna düşülüyor (mod: %s).", mode)
        local_report = self._generate_local_report(mode, context, custom_question)
        return self._sonuc(
            context, mode, custom_question,
            source="LOCAL_EXPERT_ENGINE",
            model_name="Yerel Finansal Motor",
            report_markdown=local_report,
        )

    def _sonuc(self, context, mode, custom_question, source, model_name, report_markdown):
        """Raporu arşive yazar ve yanıtı kurar.

        Arşive yazma BAŞARISIZ OLSA BİLE rapor kullanıcıya döner — arşiv
        konfor katmanıdır, kritik yol değildir (bkz. archive.py tasarım
        kuralı 1).
        """
        rapor_id = archive.save_ai_report(
            mode=mode,
            report_markdown=report_markdown,
            source=source,
            model_name=model_name,
            custom_question=custom_question,
            portfolio_digest=self._kasa_ozeti(context),
        )
        onceki = context.get("previous_analysis") or {}
        return {
            "success": True,
            "source": source,
            "model_name": model_name,
            "mode": mode,
            "report_markdown": report_markdown,
            "generated_at": datetime.now().strftime("%H:%M:%S"),
            "report_id": rapor_id,
            "archived": rapor_id is not None,
            # Arayüz "bu analiz öncekini biliyordu" diyebilsin.
            "previous_report_at": onceki.get("created_at"),
        }

    def _call_gemini_api(self, api_key: str, mode: str, context: dict, custom_question: str):
        mode_instructions = {
            "recovery": """Sen kıdemli bir Kripto Risk ve Portföy Kurtarma Stratejistisin. GÖREV: Kullanıcının zarardaki pozisyonlarını (pnl_usd < 0) detaylı incele. Hangi varlıkların toparlanma potansiyeli yüksek, hangilerinin riskli olduğunu belirle ve serbest nakitle DCA planı çıkar. Türkçe Markdown ile yaz.""",
            "brutal": """Sen tavizsiz ve acı gerçekleri söyleyen bir Kripto Başuzmanısın. GÖREV: Kullanıcının sepetindeki %50+ zararda olan veya likiditesi bitmiş varlıkları tespit et. Kalan son bakiyeyi kurtarıp BTC/SOL/XAUT gibi sağlam varlıklara aktarmanın avantajını anlat ve net stop-loss / kol kesme tavsiyeleri ver. Türkçe Markdown ile yaz.""",
            # "serbest nakit kasasını büyüt" talimatı tek başına tehlikeliydi:
            # "yeterli" kavramı olmadığı için model her seferinde satacak bir
            # şey buluyordu. Kullanıcının nakdi zaten kasasının ~%49'uydu.
            "take_profit": """Sen bir Kripto Kâr Realizasyonu Danışmanısın. GÖREV: Kârdaki pozisyonları incele ve kısmi kâr alma planı çıkar. ÖNEMLİ: Önce `cash_ratio_pct` değerine bak. Nakit oranı zaten %30'un üzerindeyse daha fazla nakde geçmeyi VARSAYILAN olarak önerme; bunun yerine mevcut nakdin nasıl değerlendirileceğini tartış ve satış önereceksen bunun nakit oranına rağmen neden gerekli olduğunu ayrıca gerekçelendir. Türkçe Markdown ile yaz.""",
            "full_audit": """Sen bir Kurumsal Kripto Portföy Yöneticisisin. GÖREV: Tüm portföyü, borsa nakitlerini ve risk oranlarını 360 derece denetle. En acil yapılması gereken 3 somut eylem maddesi çıkar. Türkçe Markdown ile yaz."""
        }

        system_instruction = mode_instructions.get(mode, mode_instructions["full_audit"])
        if custom_question:
            system_instruction += f"\n\nKULLANICININ ÖZEL SORUSU/TALEBİ:\n{custom_question}"

        # Her modda geçerli çerçeve. Bunlar olmadan model sürekli aynı işlemi
        # öneriyor, kullanıcının o işlemi zaten yaptığını göremiyor ve
        # uğraşmaya değmeyecek büyüklükte pozisyonlarda işlem tarif ediyordu.
        cerceve = f"""
HER MODDA GEÇERLİ KURALLAR:

1. SÜREKLİLİK. `previous_analysis` alanı en son verdiğin raporu içerir.
   Aynı tavsiyeyi tekrar vermen, koşullar değişmediyse DOĞRUDUR — kendini
   tekrar etmemek için tavsiye DEĞİŞTİRME. Ama tekrar ediyorsan bunu AÇIKÇA
   söyle ve şu ikisinden birini yap:
     • Kullanıcı önceki tavsiyeni uygulamamışsa: "Bu, {{tarih}} tarihli
       önerimin aynısı, uygulanmamış" de ve tezin hâlâ geçerli olup
       olmadığını yeniden tartış.
     • Uygulamışsa: bunu teyit et ve bir SONRAKİ adımı anlat, aynı adımı
       tekrar isteme.

2. KULLANICININ NE YAPTIĞINI OKU. `realized_history.recent_closed_trades`
   kapanmış satışları verir. `notes` alanında "YZ Önerisi" geçen bir satış,
   kullanıcının daha önceki bir yapay zekâ tavsiyesini UYGULADIĞI anlamına
   gelir. Bunu görmeden "şunu sat" deme.

3. UĞRAŞMAYA DEĞER BÜYÜKLÜK. Kısmi satış önermeden ÖNCE o satışın kaç dolar
   edeceğini hesapla; `value_of_25pct_usd` bunu hazır veriyor.
     • `partial_sale_not_worth_it: true` ise elde edilecek tutar
       {MIN_ISLEM_TUTARI_USD:.0f} USD'nin altındadır. KISMİ SATIŞ ÖNERME —
       ya "tamamen kapat" ya da "dokunma" de. Pozisyonun toplam değeri makul
       görünse bile bu geçerlidir; ölçüt işlemin tutarıdır, pozisyonun değil.
     • `too_small_to_trade: true` ise pozisyonun tamamı
       {MIN_POZISYON_DEGERI_USD:.0f} USD'nin altındadır; burada da kademeli
       plan tarif etme.

4. NAKİT ORANI. `cash_ratio_pct` kasanın yüzde kaçının nakit olduğunu
   söyler. "Nakde geç" tavsiyesi vermeden önce bu sayıya bak; zaten yüksekse
   daha fazla nakit üretmek bir çözüm değil, atıl para demektir.

5. NET BAŞA BAŞ. Bir coinde `net_breakeven` doluysa gerçek kurtulma eşiği
   odur; `avg_cost` yalnızca elde kalan lotları anlatır ve geçmiş zararları
   KAPSAMAZ. "Az kaldı" derken doğru eşiğe bak.
"""

        prompt = f"""{system_instruction}
{cerceve}
---
KULLANICININ CANLI PORTFÖY VERİLERİ (JSON):
```json
{json.dumps(context, indent=2, ensure_ascii=False)}
```
---
Lütfen hemen kapsamlı, anlaşılır, madde madde, tablolu ve doğrudan uygulanabilir Türkçe analiz raporunu eksiksiz üret. ÖNEMLİ KURAL: Raporu 600-900 kelime aralığında, tüm bölümleri, maddeleri, tabloları ve sonuç değerlendirmesini EKSİKSİZ sonuçlandırarak bitir. Asla cümlenin veya tablonun ortasında yarım bırakma. Raporun sonuna kısa bir Yasal Uyarı (YTD) ekle:
"""

        # En gelişmiş modelden (3.7 Flash) başlayarak dene
        models_to_try = [
            ("gemini-3.7-flash", "Google Gemini 3.7 Flash"),
            ("gemini-3.6-flash", "Google Gemini 3.6 Flash")
        ]

        for model_id, model_display in models_to_try:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.4,
                        "maxOutputTokens": 8192
                    }
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=65) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    candidates = result.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text = parts[0].get("text", "")
                            if text:
                                logger.info("AI raporu %s ile üretildi (%d karakter, mod: %s).", model_display, len(text), mode)
                                return text, model_display
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    logger.warning("%s dakikalık istek sınırına (429) takıldı.", model_id)
                    # Return immediately to avoid bursting the minute limit
                    return ("# ⏳ Dakikalık İstek Sınırı (Rate Limit)\nGoogle AI ücretsiz katmanda dakikada en fazla 5 istek kabul etmektedir. Lütfen 30-45 saniye bekleyip tekrar deneyiniz.\n\n*(Günlük kotanız tükenmemiştir, sadece 1 dakika dinlenmesi gerekmektedir.)*", model_display)
                else:
                    # Fallback zincirinin izi: 3.7 düşerse 3.6 devralır, o da düşerse yerel motor.
                    logger.warning("%s çağrısı HTTP hatası verdi: %s — sonraki modele geçiliyor.", model_id, e)
            except Exception as e:
                logger.warning("%s çağrısı başarısız: %s — sonraki modele geçiliyor.", model_id, e)
                continue

        return "", ""

    def _sureklilik_notu(self, context):
        """Yerel motorun rapor sonuna eklediği "geçen sefer ne demiştik" bloğu.

        Yerel motor bir dil modeli değil, kural motoru — önceki raporu okuyup
        yorumlayamaz. Ama en azından kullanıcıya şunu söyleyebilir: bir önceki
        analiz ne zaman üretildi ve o günden bu yana kasa nasıl değişti.
        Modelin göremediği için sürekli aynı şeyi tekrarlaması sorununun
        yerel motordaki karşılığı buydu.
        """
        onceki = context.get("previous_analysis")
        if not onceki:
            return []

        satirlar = ["\n---", "### 🔁 Önceki Analize Göre Ne Değişti",
                    f"* **Bir önceki rapor:** `{onceki.get('created_at', '—')}` "
                    f"(mod: `{onceki.get('mode', '—')}`)"]

        eski = onceki.get("portfolio_digest") or {}
        eski_kasa = eski.get("total_equity")
        yeni_kasa = context.get("total_equity")
        if isinstance(eski_kasa, (int, float)) and isinstance(yeni_kasa, (int, float)):
            fark = yeni_kasa - eski_kasa
            isaret = "+" if fark >= 0 else "−"
            satirlar.append(
                f"* **Kasa:** `${eski_kasa:,.2f}` → `${yeni_kasa:,.2f}` "
                f"({isaret}${abs(fark):,.2f})")

        eski_nakit = eski.get("cash_ratio_pct")
        yeni_nakit = context.get("cash_ratio_pct")
        if isinstance(eski_nakit, (int, float)) and isinstance(yeni_nakit, (int, float)):
            satirlar.append(f"* **Nakit oranı:** `%{eski_nakit:.1f}` → `%{yeni_nakit:.1f}`")

        # Önceki rapordan sonra kapanan işlemler: tavsiye uygulanmış mı?
        gecmis = (context.get("realized_history") or {}).get("recent_closed_trades") or []
        kesim = str(onceki.get("created_at") or "")[:10]
        sonrakiler = [t for t in gecmis if str(t.get("exit_date") or "") >= kesim and kesim]
        if sonrakiler:
            satirlar.append("* **O tarihten beri kapanan işlemler:**")
            for t in sonrakiler[:5]:
                not_ = (t.get("notes") or "").strip()
                ek = f" — _{not_[:70]}_" if not_ else ""
                satirlar.append(
                    f"  * `{t.get('exit_date')}` **{t.get('coin')}** "
                    f"K/Z `${t.get('realized_pnl_usd', 0):,.2f}`{ek}")
        else:
            satirlar.append(
                "* **O tarihten beri kapanan işlem yok** — önceki rapordaki "
                "satış önerileri uygulanmamış görünüyor.")

        return satirlar

    def _generate_local_report(self, mode: str, context: dict, custom_question: str) -> str:
        coins = context.get("coins", [])
        total_cash = context.get("total_usdt_cash", 0.0)
        spot_val = context.get("total_spot_current_value", 0.0)
        total_equity = context.get("total_equity") or (spot_val + total_cash)
        cash_ratio = (total_cash / total_equity * 100.0) if total_equity > 0 else 0.0

        losers = [c for c in coins if c.get("pnl_usd", 0) < 0]
        gainers = [c for c in coins if c.get("pnl_usd", 0) > 0]
        # Eskiden burada `c.get("is_dead")` de vardı; data_manager o alanı hiç
        # üretmediği için her zaman False'tu ve ölçüt aslında tek başına
        # pnl_pct'ydi. Alan kaldırıldı, ölçüt olduğu gibi kaldı.
        dead_coins = [c for c in coins if c.get("deeply_underwater")
                      or c.get("pnl_pct", 0) <= -50.0]

        losers.sort(key=lambda x: x.get("pnl_usd", 0))
        gainers.sort(key=lambda x: x.get("pnl_usd", 0), reverse=True)

        if mode == "recovery":
            lines = [
                "# 🎯 Yapay Zeka: Zarardan Kurtarma & Akıllı DCA Raporu",
                f"**Rapor Tarihi:** `{context.get('analysis_time')}` | **Mevcut Serbest Kasa:** `${total_cash:,.2f} USDT`\n",
                "---",
                "### 🔍 1. Maliyet Altındaki Varlıkların Durum Analizi",
            ]
            if not losers:
                lines.append("🎉 **Tebrikler!** Portföyünüzde şu an zararda olan hiçbir pozisyon bulunmuyor. Tüm varlıklarınız maliyet üstünde kârda.")
            else:
                lines.append("| Varlık | Borsa | Zarar ($) | Zarar (%) | Başabaş İçin Gereken Yükseliş | Tavsiye Edilen Strateji |")
                lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
                for c in losers[:6]:
                    req_rise = c.get("breakeven_req_rise_pct", 0)
                    sym = c.get("name")
                    ex = c.get("exchange")
                    pnl_u = c.get("pnl_usd", 0)
                    pnl_p = c.get("pnl_pct", 0)
                    if req_rise <= 20:
                        strat = "🟢 **Hafif DCA:** 1 kademe alımla anında kâra geçer."
                    elif req_rise <= 50:
                        strat = "🟡 **Kademeli DCA:** Serbest nakitten %15-%20 ayırarak maliyeti çekin."
                    else:
                        strat = "🔴 **Bekle / İzle:** Agresif DCA yerine dip onayı bekleyin."
                    lines.append(f"| **{sym}** | `{ex}` | `-${abs(pnl_u):,.2f}` | `%{pnl_p:.1f}` | `+%{req_rise:.1f}` | {strat} |")

                lines.extend([
                    "\n### 💡 2. Akıllı Sermaye Dağılımı ve Eylem Planı",
                    f"* **Kullanılabilir Serbest Nakit:** `${total_cash:,.2f}`",
                    f"* **Öncelikli Kurtarma Hedefi:** `{losers[0].get('name')}` (Zarar: `-${abs(losers[0].get('pnl_usd', 0)):,.2f}`) varlığına serbest kasanızdan kademeli ekleme yaparak ortalama maliyetinizi düşürebilirsiniz.",
                    "* **Kritik Kural:** Tek seferde tüm nakitle DCA yapmayın; kasadaki USDT'yi 3 parçaya bölerek (%30 - %30 - %40) kademeli giriş yapın."
                ])
            lines.extend(self._sureklilik_notu(context))
            return "\n".join(lines)

        elif mode == "brutal":
            lines = [
                "# ⚠️ Acı Gerçek / Kol Kesme (Brutal Honesty) Raporu",
                f"**Rapor Tarihi:** `{context.get('analysis_time')}`\n",
                "---",
                "### 🚨 1. Yüksek Riskli & Erimiş Varlık Denetimi",
            ]
            if not dead_coins:
                lines.append("🛡️ **Portföyünüz Temiz:** Sepetinizde %50'den fazla erimiş veya likiditesi bitmiş kritik ölü varlık tespit edilmedi.")
            else:
                lines.append("> [!WARNING]\n> Aşağıdaki varlıklar sermayenizin büyük kısmını eritmiş durumda. Bu varlıkların eski maliyetine gelmesi için devasa yükselişler (+%150 - +%500) gerekmektedir.\n")
                lines.append("| Riskli Varlık | Borsa | Erime Oranı | Kalan Değer | Kurtarma Simülasyonu (Kol Kesme) |")
                lines.append("| :--- | :--- | :--- | :--- | :--- |")
                for c in dead_coins:
                    val = c.get("current_value", 0)
                    pnl_p = c.get("pnl_pct", 0)
                    lines.append(f"| **{c.get('name')}** | `{c.get('exchange')}` | `%{pnl_p:.1f}` | `${val:,.2f}` | Kalan `${val:,.2f}` nakdi BTC/SOL'a aktarmak bu paranın sıfırlanmasını önler. |")

                lines.extend([
                    "\n### ⚖️ 2. Gerçekçi Finansal Değerlendirme",
                    "* Likiditesi bitmiş veya %80+ düşmüş altcoinlerde 'nasılsa maliyete gelir' diye beklemek en büyük portföy tuzağıdır.",
                    "* Kalan son bakiyeyi sağlam majör varlıklara aktarmak, sermaye bileşik getirisini yeniden çalıştırmanın en sağlıklı yoludur."
                ])
            lines.extend(self._sureklilik_notu(context))
            return "\n".join(lines)

        elif mode == "take_profit":
            lines = [
                "# 🏆 Kâr Realizasyonu & Kasa Büyütme Stratejisi",
                f"**Rapor Tarihi:** `{context.get('analysis_time')}`\n",
                "---",
                "### 💰 1. Kârdaki Varlıklar ve Kâr Alma Kademeleri",
            ]
            # Nakit oranı zaten yüksekse "daha çok nakit yap" bir çözüm değil,
            # atıl para demektir. Bu uyarı olmadan motor her koşumda satış
            # öneriyordu — Gemini tarafındaki kusurun yerel eşdeğeriydi.
            if cash_ratio >= 30.0:
                lines.append(
                    f"> [!NOTE]\n> Kasanızın **%{cash_ratio:.1f}**'i zaten nakit "
                    f"(`${total_cash:,.2f}`). Bu seviyede daha fazla nakde geçmek "
                    "genellikle bir çözüm değil, atıl para demektir. Aşağıdaki "
                    "önerileri bu çerçevede değerlendirin.\n")

            if not gainers:
                lines.append("Şu anda kârda olan aktif pozisyon bulunmuyor. Piyasa fırsatları ve DCA toparlanmaları takip ediliyor.")
            else:
                lines.append("| Varlık | Borsa | Net Kâr ($) | Getiri (%) | Portföy Payı | Tavsiye Edilen Kâr Alma Planı |")
                lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
                for c in gainers[:5]:
                    # Ölçüt pozisyonun değil, ÖNERİLEN İŞLEMİN büyüklüğü.
                    # Şikâyete konu vakada pozisyon ~$220'dı (eşiği geçiyordu)
                    # ama %25'i ~$55 ediyordu ve asıl saçmalık oradaydı.
                    if c.get("partial_sale_not_worth_it") or c.get("too_small_to_trade"):
                        plan = (f"⚪ **Kısmi satış önerilmez:** %25'i yalnızca "
                                f"`${c.get('value_of_25pct_usd', 0):,.2f}` eder "
                                f"({MIN_ISLEM_TUTARI_USD:.0f} USD eşiğinin altında). "
                                "Ya tamamen kapatın ya da dokunmayın.")
                    else:
                        plan = ("🎯 **%25-%35 Kısmi Satış:** Anaparayı serbest kasaya "
                                "çekip kalan kârı ana hedefte bekletin.")
                    lines.append(f"| **{c.get('name')}** | `{c.get('exchange')}` | `+${c.get('pnl_usd', 0):,.2f}` | `+%{c.get('pnl_pct', 0):.1f}` | `%{c.get('portfolio_share_pct', 0):.1f}` | {plan} |")

                lines.extend([
                    "\n### 🛡️ 2. Kasa Zırhlama Tavsiyesi",
                    "* Kârdaki varlıklardan düzenli kâr realize etmek, serbest nakit kasanızı büyüterek olası piyasa düzeltmelerinde yeni fırsatlar yakalamanızı sağlar."
                ])
            lines.extend(self._sureklilik_notu(context))
            return "\n".join(lines)

        else: # full_audit
            lines = [
                "# 🩺 Bütünsel Portföy Check-Up & Yönetici Eylem Planı",
                f"**Rapor Tarihi:** `{context.get('analysis_time')}`\n",
                "---",
                "### 📊 1. Temel Finansal Göstergeler",
                f"* **Toplam Portföy Büyüklüğü:** `${total_equity:,.2f}`",
                f"* **Spot Yatırımlar:** `${spot_val:,.2f}` | **Serbest Nakit (USDT):** `${total_cash:,.2f}` (`%{cash_ratio:.1f}`)",
                f"* **Toplam Net Gerçekleşmemiş K/Z:** `+{context.get('total_net_pnl_usd', 0):,.2f}$`" if context.get('total_net_pnl_usd', 0) >= 0 else f"* **Toplam Net Gerçekleşmemiş K/Z:** `-${abs(context.get('total_net_pnl_usd', 0)):,.2f}`",
                "\n### 🎯 2. Öncelikli 3 Karar Destek Maddesi",
                "1. **Nakit Tamponu Dengesi:** " + ("Nakit oranınız ideal seviyede (%15-%35)." if 15 <= cash_ratio <= 35 else "Nakit oranınızı %20 seviyelerine çekmek için kârdaki varlıklardan kısmi kâr realizasyonu planlanabilir."),
                f"2. **Maliyet Yönetimi:** Sepetteki `{len(losers)}` maliyet altı varlık için Akıllı DCA simülatörü üzerinden başabaş senaryosu hesaplayabilirsiniz.",
                f"3. **Hedef Fiyat Disiplini:** Kârdaki `{len(gainers)}` varlık için 'Hedef Belirle' simülatörünü kullanarak kâr alma kademeleri tanımlayabilirsiniz."
            ]

        # Append standard YTD disclaimer to all reports
        disclaimer = "\n\n---\n> [!NOTE]\n> ⚠️ **Yasal Bilgilendirme:** Bu analizler yapay zeka modelleri ve algoritmalar tarafından simülasyon ve karar destek amaçlı üretilmiştir. Kesinlikle yatırım tavsiyesi (YTD) niteliği taşımaz. Yatırım kararlarınızı kendi risk tercihlerinize göre alınız."
        lines.extend(self._sureklilik_notu(context))
        return "\n".join(lines) + disclaimer

ai_advisor = AIFinancialAdvisor()
