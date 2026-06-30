"""
Reddit 初回ログイン用スクリプト（1回だけ実行）

実行方法:
    python services/reddit_auth.py

ブラウザが開くのでRedditにログインしてください。
ログイン完了を自動検知してセッションを保存します。
"""
import asyncio
from pathlib import Path

REDDIT_DATA_DIR = str(Path(__file__).parent.parent / "reddit_playwright_data")


async def main():
    from playwright.async_api import async_playwright

    print("=== Reddit 初回ログイン ===")
    print(f"セッション保存先: {REDDIT_DATA_DIR}")
    Path(REDDIT_DATA_DIR).mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            REDDIT_DATA_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            slow_mo=100,
        )
        page = await ctx.new_page()
        await page.goto("https://www.reddit.com/login")
        print("ブラウザが開きました。Redditにログインしてください。")
        print("ログイン完了を自動検知します（最大3分待機）...")

        # ログイン完了（URLが/loginから離れる）を自動検知
        try:
            await page.wait_for_url(
                lambda url: "reddit.com/login" not in url and "reddit.com/register" not in url,
                timeout=180000,
            )
            print("✅ ログイン成功！セッションを保存しました。")
        except Exception:
            print("⏱️ タイムアウト — 再度実行してください")

        await ctx.close()
    print("完了。ダッシュボードで「Redditに投稿」ボタンが使えます。")


if __name__ == "__main__":
    asyncio.run(main())
