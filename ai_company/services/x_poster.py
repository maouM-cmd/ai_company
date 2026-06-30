"""
X（Twitter）自動投稿サービス
- Playwright でログイン済みセッションを使って自動ツイート
- セッション: x_playwright_data/ に保存
"""
from pathlib import Path

X_DATA_DIR = str(Path(__file__).parent.parent / "x_playwright_data")

HASHTAGS_JA = "#AI副業 #ChatGPT #副業 #note"
HASHTAGS_EN = "#AI #SideHustle #PassiveIncome"


def is_logged_in() -> bool:
    data_dir = Path(X_DATA_DIR)
    return (data_dir / "Default" / "Cookies").exists() or \
           (data_dir / "Default" / "Network" / "Cookies").exists()


class XPoster:
    def __init__(self):
        self._ctx = None

    def is_configured(self) -> bool:
        return is_logged_in()

    async def _get_context(self):
        if self._ctx:
            return self._ctx
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        Path(X_DATA_DIR).mkdir(parents=True, exist_ok=True)
        self._ctx = await pw.chromium.launch_persistent_context(
            X_DATA_DIR,
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        return self._ctx

    async def post_async(self, text: str) -> dict:
        """X にツイートを投稿する（最大280文字）"""
        if len(text) > 280:
            text = text[:277] + "..."

        ctx = await self._get_context()
        page = await ctx.new_page()
        try:
            await page.goto("https://x.com/home", timeout=30000)
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            current_url = page.url
            page_title = await page.title()
            print(f"[X] ページ状態: url={current_url}, title={page_title}")

            if "login" in current_url or "signin" in current_url or "flow" in current_url:
                return {"status": "error", "error": "未ログイン — python services/x_auth.py を実行してください"}

            # 現在のページのdata-testidを確認
            testids = await page.evaluate(
                "Array.from(document.querySelectorAll('[data-testid]')).map(e => e.dataset.testid).slice(0, 30)"
            )
            print(f"[X] 検出したtestid: {testids}")

            # 投稿テキストエリア
            tweet_sel = "[data-testid='tweetTextarea_0']"
            await page.wait_for_selector(tweet_sel, timeout=30000)
            await page.click(tweet_sel)
            await page.wait_for_timeout(500)
            await page.keyboard.type(text, delay=15)
            await page.wait_for_timeout(1000)

            post_btn = "[data-testid='tweetButtonInline']"
            await page.wait_for_selector(post_btn, timeout=10000)
            await page.click(post_btn)
            await page.wait_for_timeout(3000)

            url = page.url
            print(f"[X] 投稿完了: {url}")
            return {"status": "posted", "url": url, "text": text[:50]}

        except Exception as e:
            # エラー時もページ状態をログ出力
            try:
                err_url = page.url
                err_title = await page.title()
                print(f"[X] エラー時ページ: url={err_url}, title={err_title}")
            except Exception:
                pass
            print(f"[X] 投稿エラー: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            await page.close()
