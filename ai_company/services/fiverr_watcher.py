"""
Fiverr 注文 自動監視・生成・配信
- playwright で Fiverr orders ページを5分ごとポーリング
- 新規注文を検知したら API でコンテンツ生成
- 生成完了後 Fiverr の配信フォームにテキストを入力して自動送信
"""
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

POLL_INTERVAL = 300  # 秒（5分）
PLAYWRIGHT_DATA_DIR = str(Path(__file__).parent.parent / "playwright_data")
API_BASE = "http://localhost:8001"

# キーワードからギグ種別を自動判定
GIG_KEYWORDS = {
    "market_research": ["market", "research", "analysis", "industry", "report", "survey"],
    "seo_blog": ["blog", "article", "seo", "content", "write", "post", "wordpress"],
    "business_proposal": ["proposal", "business", "pitch", "plan", "deck", "startup"],
}


def _detect_gig_type(text: str) -> str:
    lower = text.lower()
    scores = {gig: sum(1 for kw in kws if kw in lower) for gig, kws in GIG_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "market_research"


class FiverrWatcher:
    def __init__(self, mem):
        self.mem = mem
        self._running = False
        self._task: asyncio.Task | None = None
        self._browser = None
        self._context = None

    # ── 公開インターフェース ──────────────────────────────────────

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())
            print("[Fiverr] 監視開始")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        print("[Fiverr] 監視停止")

    def status(self) -> dict:
        orders = self.mem.list_fiverr_orders(limit=10)
        return {
            "running": self._running,
            "poll_interval_sec": POLL_INTERVAL,
            "recent_orders": orders,
        }

    # ── メインループ ────────────────────────────────────────────

    async def _loop(self):
        while self._running:
            try:
                await self._poll_orders()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Fiverr] ポーリングエラー: {e}")
            await asyncio.sleep(POLL_INTERVAL)

    # ── playwright 操作 ─────────────────────────────────────────

    async def _get_context(self):
        if self._context:
            return self._context
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        Path(PLAYWRIGHT_DATA_DIR).mkdir(parents=True, exist_ok=True)
        self._browser = await pw.chromium.launch_persistent_context(
            PLAYWRIGHT_DATA_DIR,
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._browser
        return self._context

    async def _poll_orders(self):
        ctx = await self._get_context()
        page = await ctx.new_page()
        try:
            await page.goto("https://www.fiverr.com/orders?status=active", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # ログインチェック
            if "login" in page.url or "signup" in page.url:
                print("[Fiverr] 未ログイン — fiverr_auth.py を実行してください")
                return

            # 注文カードを取得
            order_links = await page.eval_on_selector_all(
                "a[href*='/orders/']",
                "els => els.map(el => ({href: el.href, text: el.textContent.trim()}))"
            )

            for item in order_links:
                href = item.get("href", "")
                m = re.search(r"/orders/([A-Z0-9]+)", href)
                if not m:
                    continue
                order_id = m.group(1)
                if self.mem.fiverr_order_exists(order_id):
                    continue

                # 注文詳細ページで要件を取得
                await self._process_new_order(ctx, order_id)

        except Exception as e:
            print(f"[Fiverr] poll エラー: {e}")
        finally:
            await page.close()

    async def _process_new_order(self, ctx, order_id: str):
        page = await ctx.new_page()
        try:
            url = f"https://www.fiverr.com/orders/{order_id}"
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # バイヤーメッセージ / 要件テキストを取得
            requirements = await self._extract_requirements(page)
            gig_type = _detect_gig_type(requirements)

            print(f"[Fiverr] 新規注文 {order_id} 検知 gig={gig_type}")
            self.mem.save_fiverr_order(order_id, gig_type, requirements, "generating")

            # API 呼び出し → コンテンツ生成
            import aiohttp
            async with aiohttp.ClientSession() as session:
                payload = {
                    "gig_type": gig_type,
                    "topic": f"Order {order_id}",
                    "requirements": requirements,
                }
                async with session.post(f"{API_BASE}/fiverr/order", json=payload) as resp:
                    data = await resp.json()
                    task_id = data["task_id"]

            # 完了を待機（最大10分）
            content = await self._wait_for_result(task_id, timeout=600)
            if not content:
                self.mem.update_fiverr_order(order_id, "failed")
                print(f"[Fiverr] {order_id} コンテンツ生成タイムアウト")
                return

            # 配信
            await self._deliver(page, order_id, content)

        except Exception as e:
            print(f"[Fiverr] 注文処理エラー {order_id}: {e}")
            self.mem.update_fiverr_order(order_id, "failed")
        finally:
            await page.close()

    async def _extract_requirements(self, page) -> str:
        selectors = [
            ".requirements-text",
            "[data-testid='order-requirements']",
            ".order-message-body",
            ".message-body",
            ".bubble-content",
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    if text.strip():
                        return text.strip()[:2000]
            except Exception:
                pass
        # フォールバック: ページ全体テキストから推測
        body = await page.inner_text("body")
        return body[:500]

    async def _wait_for_result(self, task_id: str, timeout: int = 600) -> str | None:
        import aiohttp
        waited = 0
        while waited < timeout:
            await asyncio.sleep(10)
            waited += 10
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{API_BASE}/tasks/{task_id}") as resp:
                        data = await resp.json()
                        if data.get("status") == "completed" and data.get("result"):
                            return data["result"]
                        if data.get("status") == "failed":
                            return None
            except Exception:
                pass
        return None

    async def _deliver(self, page, order_id: str, content: str):
        try:
            # 配信ボタン / フォームを探す
            await page.wait_for_selector(
                "button[data-testid='deliver-order'], button:has-text('Deliver'), a:has-text('Deliver')",
                timeout=5000
            )
            await page.click(
                "button[data-testid='deliver-order'], button:has-text('Deliver'), a:has-text('Deliver')"
            )
            await page.wait_for_timeout(1500)

            # メッセージ欄に入力
            textarea = await page.query_selector(
                "textarea[name='message'], textarea[placeholder*='message'], .delivery-message textarea"
            )
            if textarea:
                await textarea.fill(content[:5000])  # Fiverr文字制限考慮
                await page.wait_for_timeout(500)

            # 送信
            await page.click(
                "button[type='submit']:has-text('Deliver'), button:has-text('Submit Delivery'), "
                "button[data-testid='submit-delivery']"
            )
            await page.wait_for_timeout(2000)

            self.mem.update_fiverr_order(order_id, "delivered")
            print(f"[Fiverr] {order_id} 配信完了")

        except Exception as e:
            print(f"[Fiverr] 配信エラー {order_id}: {e}")
            # 配信失敗でも生成済みとして記録（手動配信をサポート）
            self.mem.update_fiverr_order(order_id, "generated")
