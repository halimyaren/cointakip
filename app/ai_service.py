import os
import json
import urllib.request
import urllib.parse
from datetime import datetime
from data_manager import load_settings, load_portfolio, calculate_portfolio_metrics
from price_service import price_service
from log_config import get_logger

logger = get_logger("ai_service")

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
                "is_dead": c.get("is_dead", False),
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
        return context

    def analyze(self, mode: str = "full_audit", custom_question: str = ""):
        context = self.get_portfolio_context()
        settings = load_settings()
        api_key = settings.get("api_keys", {}).get("gemini_api_key", "").strip()

        if api_key:
            try:
                llm_response, model_display = self._call_gemini_api(api_key, mode, context, custom_question)
                if llm_response:
                    return {
                        "success": True,
                        "source": "GEMINI_AI",
                        "model_name": model_display or "Google Gemini AI",
                        "mode": mode,
                        "report_markdown": llm_response,
                        "generated_at": datetime.now().strftime("%H:%M:%S")
                    }
            except Exception as e:
                logger.warning("Gemini çağrısı başarısız, yerel kural motoruna düşülüyor: %s", e)

        # Fallback to Local Algorithmic Financial Advisor
        if not api_key:
            logger.info("Gemini API anahtarı tanımlı değil — yerel kural motoru kullanılıyor (mod: %s).", mode)
        else:
            logger.info("Gemini modellerinin hiçbiri yanıt vermedi — yerel kural motoruna düşülüyor (mod: %s).", mode)
        local_report = self._generate_local_report(mode, context, custom_question)
        return {
            "success": True,
            "source": "LOCAL_EXPERT_ENGINE",
            "model_name": "Yerel Finansal Motor",
            "mode": mode,
            "report_markdown": local_report,
            "generated_at": datetime.now().strftime("%H:%M:%S")
        }

    def _call_gemini_api(self, api_key: str, mode: str, context: dict, custom_question: str):
        mode_instructions = {
            "recovery": """Sen kıdemli bir Kripto Risk ve Portföy Kurtarma Stratejistisin. GÖREV: Kullanıcının zarardaki pozisyonlarını (pnl_usd < 0) detaylı incele. Hangi varlıkların toparlanma potansiyeli yüksek, hangilerinin riskli olduğunu belirle ve serbest nakitle DCA planı çıkar. Türkçe Markdown ile yaz.""",
            "brutal": """Sen tavizsiz ve acı gerçekleri söyleyen bir Kripto Başuzmanısın. GÖREV: Kullanıcının sepetindeki %50+ zararda olan veya likiditesi bitmiş varlıkları tespit et. Kalan son bakiyeyi kurtarıp BTC/SOL/XAUT gibi sağlam varlıklara aktarmanın avantajını anlat ve net stop-loss / kol kesme tavsiyeleri ver. Türkçe Markdown ile yaz.""",
            "take_profit": """Sen bir Kripto Kâr Realizasyonu Danışmanısın. GÖREV: Kârdaki pozisyonları incele, kısmi kâr alma (%25-%50 anapara çekme) ve serbest nakit kasasını büyütme planı çıkar. Türkçe Markdown ile yaz.""",
            "full_audit": """Sen bir Kurumsal Kripto Portföy Yöneticisisin. GÖREV: Tüm portföyü, borsa nakitlerini ve risk oranlarını 360 derece denetle. En acil yapılması gereken 3 somut eylem maddesi çıkar. Türkçe Markdown ile yaz."""
        }

        system_instruction = mode_instructions.get(mode, mode_instructions["full_audit"])
        if custom_question:
            system_instruction += f"\n\nKULLANICININ ÖZEL SORUSU/TALEBİ:\n{custom_question}"

        prompt = f"""{system_instruction}

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

    def _generate_local_report(self, mode: str, context: dict, custom_question: str) -> str:
        coins = context.get("coins", [])
        total_cash = context.get("total_usdt_cash", 0.0)
        spot_val = context.get("total_spot_current_value", 0.0)
        total_equity = context.get("total_equity") or (spot_val + total_cash)
        cash_ratio = (total_cash / total_equity * 100.0) if total_equity > 0 else 0.0

        losers = [c for c in coins if c.get("pnl_usd", 0) < 0]
        gainers = [c for c in coins if c.get("pnl_usd", 0) > 0]
        dead_coins = [c for c in coins if c.get("is_dead") or c.get("pnl_pct", 0) <= -50.0]

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
            return "\n".join(lines)

        elif mode == "take_profit":
            lines = [
                "# 🏆 Kâr Realizasyonu & Kasa Büyütme Stratejisi",
                f"**Rapor Tarihi:** `{context.get('analysis_time')}`\n",
                "---",
                "### 💰 1. Kârdaki Varlıklar ve Kâr Alma Kademeleri",
            ]
            if not gainers:
                lines.append("Şu anda kârda olan aktif pozisyon bulunmuyor. Piyasa fırsatları ve DCA toparlanmaları takip ediliyor.")
            else:
                lines.append("| Varlık | Borsa | Net Kâr ($) | Getiri (%) | Portföy Payı | Tavsiye Edilen Kâr Alma Planı |")
                lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
                for c in gainers[:5]:
                    lines.append(f"| **{c.get('name')}** | `{c.get('exchange')}` | `+${c.get('pnl_usd', 0):,.2f}` | `+%{c.get('pnl_pct', 0):.1f}` | `%{c.get('portfolio_share_pct', 0):.1f}` | 🎯 **%25-%35 Kısmi Satış:** Anaparayı serbest kasaya çekip kalan kârı ana hedefte bekletin. |")

                lines.extend([
                    "\n### 🛡️ 2. Kasa Zırhlama Tavsiyesi",
                    "* Kârdaki varlıklardan düzenli kâr realize etmek, serbest nakit kasanızı büyüterek olası piyasa düzeltmelerinde yeni fırsatlar yakalamanızı sağlar."
                ])
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
        return "\n".join(lines) + disclaimer

ai_advisor = AIFinancialAdvisor()
