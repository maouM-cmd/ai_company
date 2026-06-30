"""
Reddit 自動投稿サービス（Playwright版 / APIキー不要）
- 一度 reddit_auth.py でログインするだけで使える
"""
import asyncio
import re
from pathlib import Path

REDDIT_DATA_DIR = str(Path(__file__).parent.parent / "reddit_playwright_data")

SUBREDDIT_MAP = {
    "seo_pack":       ["Entrepreneur", "smallbusiness", "marketing"],
    "ai_bundle":      ["Entrepreneur", "artificial", "SideProject"],
    "pitch_deck":     ["startups", "Entrepreneur", "SideProject"],
    "side_hustle":    ["passive_income", "SideProject", "Entrepreneur"],
    "ai_productivity":["productivity", "Entrepreneur", "ChatGPT"],
    "marketing":      ["marketing", "Entrepreneur", "smallbusiness"],
    "default":        ["Entrepreneur", "SideProject"],
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


class RedditPoster:
    def __init__(self):
        self._ctx = None

    def is_configured(self) -> bool:
        return is_logged_in()

    async def _get_context(self):
        if self._ctx:
            return self._ctx
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        Path(REDDIT_DATA_DIR).mkdir(parents=True, exist_ok=True)
        self._ctx = await pw.chromium.launch_persistent_context(
            REDDIT_DATA_DIR,
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        return self._ctx

    async def post_async(self, raw_text: str, topic_key: str = "default", subreddit: str = "") -> dict:
        parsed = _extract_reddit_post(raw_text, topic_key)
        target = subreddit or parsed["subreddits"][0]
        title = parsed["title"]
        body = parsed["body"]

        print(f"[Reddit] 投稿開始: r/{target}")
        ctx = await self._get_context()
        page = await ctx.new_page()
        try:
            url = f"https://www.reddit.com/r/{target}/submit?type=self"
            await page.goto(url, timeout=30000)
            # networkidle は Reddit では永遠に終わらないことがある → domcontentloaded に変更
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            current_url = page.url
            print(f"[Reddit] ページ読込完了: {current_url}")

            # ログインチェック（URLとページ内容の両方を確認）
            if "login" in current_url or "register" in current_url:
                print("[Reddit] 未ログイン検出 → reddit_auth.py を実行してください")
                return {"status": "error", "error": "未ログイン — python services/reddit_auth.py を実行してください"}

            # タイトル入力
            title_sel = "textarea[placeholder*='Title'], input[placeholder*='Title'], [data-testid='post-title'] textarea"
            await page.wait_for_selector(title_sel, timeout=30000)
            await page.click(title_sel)
            await page.fill(title_sel, title)
            await page.wait_for_timeout(500)

            # 本文入力（新Reddit UIはProseMirrorエディタ）
            body_sel = ".public-DraftEditor-content, .DraftEditor-editorContainer, [contenteditable='true'][data-slate-editor='true'], div[role='textbox']"
            try:
                await page.wait_for_selector(body_sel, timeout=8000)
                await page.click(body_sel)
                await page.keyboard.type(body[:5000], delay=5)
            except Exception:
                # フォールバック: textarea
                ta = await page.query_selector("textarea[name='text'], textarea[placeholder*='text']")
                if ta:
                    await ta.fill(body[:5000])

            await page.wait_for_timeout(1000)

            # 投稿ボタン
            post_btn = "button[type='submit']:has-text('Post'), button:has-text('Post'), button[data-testid='post-submit-button']"
            await page.click(post_btn, timeout=10000)
            await page.wait_for_timeout(3000)

            post_url = page.url
            print(f"[Reddit] 投稿完了: {post_url}")
            return {"status": "posted", "url": post_url, "subreddit": target, "title": title}

        except Exception as e:
            print(f"[Reddit] 投稿エラー: {e}")
            return {"status": "error", "error": str(e), "subreddits": parsed["subreddits"]}
        finally:
            await page.close()

    def post(self, raw_text: str, topic_key: str = "default", subreddit: str = "") -> dict:
        return asyncio.run(self.post_async(raw_text, topic_key, subreddit))
