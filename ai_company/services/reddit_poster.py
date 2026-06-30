"""
Reddit 自動投稿サービス（Playwright版 / APIキー不要）
- 一度 reddit_auth.py でログインするだけで使える
"""
import asyncio
import re
from pathlib import Path

_post_lock = asyncio.Lock()
_poster_instance: "RedditPoster | None" = None

REDDIT_DATA_DIR = str(Path(__file__).parent.parent / "reddit_playwright_data")

SUBREDDIT_MAP = {
    "seo_pack":            ["Entrepreneur", "smallbusiness", "marketing"],
    "ai_bundle":           ["Entrepreneur", "artificial", "SideProject"],
    "pitch_deck":          ["startups", "Entrepreneur", "SideProject"],
    "side_hustle":         ["passive_income", "SideProject", "Entrepreneur"],
    "ai_productivity":     ["productivity", "Entrepreneur", "ChatGPT"],
    "marketing":           ["marketing", "Entrepreneur", "smallbusiness"],
    "investing":           ["personalfinance", "financialindependence", "passive_income"],
    "programming":         ["learnprogramming", "SideProject", "digitalnomad"],
    "content_monetization":["juststart", "Entrepreneur", "SideProject"],
    "digital_products":    ["passive_income", "Entrepreneur", "SideProject"],
    "chatgpt_business":    ["ChatGPT", "artificial", "Entrepreneur"],
    "default":             ["Entrepreneur", "SideProject"],
}


def _extract_reddit_post(raw_text: str, topic_key: str = "default") -> dict:
    # タイトル抽出
    title = ""
    m = re.search(r"##\s*タイトル.*?\n(.*?)(?:\n|$)", raw_text)
    if m:
        cand = re.search(r"[「『]([^」』]+)[」』]|\d+\.\s*(.+)", m.group(1))
        if cand:
            title = cand.group(1) or cand.group(2)
    if not title:
        m2 = re.search(r"^#+ (.+)$", raw_text, re.MULTILINE)
        title = m2.group(1) if m2 else "Sharing what I learned about side income"

    # 無料部分だけを本文に（有料部分は投稿しない）
    body = raw_text
    for marker in ["## 🔒 ここから有料", "ここから有料", "【有料部分】"]:
        if marker in raw_text:
            body = raw_text[:raw_text.index(marker)].strip()
            break

    # 英語向けに短縮（Redditは英語圏が多い）
    if len(body) > 2000:
        body = body[:2000] + "\n\n*[Full article available — link in profile]*"

    subreddits = SUBREDDIT_MAP.get(topic_key, SUBREDDIT_MAP["default"])
    return {"title": title.strip()[:300], "body": body, "subreddits": subreddits}


def is_logged_in() -> bool:
    data_dir = Path(REDDIT_DATA_DIR)
    return (data_dir / "Default" / "Cookies").exists() or \
           (data_dir / "Default" / "Network" / "Cookies").exists()


def get_poster() -> "RedditPoster":
    global _poster_instance
    if _poster_instance is None:
        _poster_instance = RedditPoster()
    return _poster_instance


class RedditPoster:
    def __init__(self):
        self._ctx = None

    def is_configured(self) -> bool:
        return is_logged_in()

    async def _get_context(self):
        if self._ctx:
            try:
                # コンテキストが生きているか確認
                _ = self._ctx.pages
                return self._ctx
            except Exception:
                self._ctx = None
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        Path(REDDIT_DATA_DIR).mkdir(parents=True, exist_ok=True)
        self._ctx = await pw.chromium.launch_persistent_context(
            REDDIT_DATA_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        return self._ctx

    async def post_async(self, raw_text: str, topic_key: str = "default", subreddit: str = "") -> dict:
        async with _post_lock:
            return await self._post_async_impl(raw_text, topic_key, subreddit)

    async def _post_async_impl(self, raw_text: str, topic_key: str = "default", subreddit: str = "") -> dict:
        parsed = _extract_reddit_post(raw_text, topic_key)
        target = subreddit or parsed["subreddits"][0]
        title = parsed["title"]
        body = parsed["body"]

        print(f"[Reddit] 投稿開始: r/{target}", flush=True)
        ctx = await self._get_context()
        page = await ctx.new_page()
        try:
            # old.reddit.com はシンプルな HTML フォームなので自動化しやすい
            url = f"https://old.reddit.com/r/{target}/submit?selftext=true"
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            current_url = page.url
            print(f"[Reddit] ページ読込完了: {current_url}", flush=True)

            # ログインチェック
            if "login" in current_url or "register" in current_url:
                print("[Reddit] 未ログイン検出 → reddit_auth.py を実行してください", flush=True)
                return {"status": "error", "error": "未ログイン — python services/reddit_auth.py を実行してください"}

            # ブロック検知
            page_text = await page.inner_text("body")
            if "blocked by network security" in page_text or "whoa there" in page_text.lower():
                print(f"[Reddit] ブロック検知: {page_text[:100]}", flush=True)
                return {"status": "error", "error": "Redditにブロックされました（bot検出）"}

            # old.reddit のフォーム: title/text は textarea[name]
            await page.wait_for_selector("textarea[name='title']", timeout=20000)
            await page.fill("textarea[name='title']", title)
            await page.wait_for_timeout(300)

            # 本文（テキスト投稿）
            text_area = await page.query_selector("textarea[name='text']")
            if text_area:
                await text_area.fill(body[:40000])
            await page.wait_for_timeout(500)

            # 投稿ボタン: old.reddit は button.btn[type='submit']
            submit_btn = await page.query_selector("button.btn[type='submit']")
            if not submit_btn:
                submit_btn = await page.query_selector("input[type='submit'][value='submit']")
            if submit_btn:
                await submit_btn.scroll_into_view_if_needed()
                await submit_btn.click()
            else:
                raise Exception("投稿ボタンが見つかりません")

            # 投稿後: URLの変化 or 3秒待機
            try:
                await page.wait_for_url("**/comments/**", timeout=5000)
            except Exception:
                await page.wait_for_timeout(3000)

            post_url = page.url
            print(f"[Reddit] 投稿完了: {post_url}", flush=True)
            return {"status": "posted", "url": post_url, "subreddit": target, "title": title}

        except Exception as e:
            print(f"[Reddit] 投稿エラー: {e}", flush=True)
            return {"status": "error", "error": str(e), "subreddits": parsed["subreddits"]}
        finally:
            await page.close()

    def post(self, raw_text: str, topic_key: str = "default", subreddit: str = "") -> dict:
        return asyncio.run(self.post_async(raw_text, topic_key, subreddit))
