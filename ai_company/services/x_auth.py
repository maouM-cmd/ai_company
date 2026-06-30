"""
X（Twitter）ログインセッション保存スクリプト
初回のみ実行: python services/x_auth.py
ログイン完了後、ホーム画面が出たら自動でセッションを保存します。
"""
import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

X_DATA_DIR = str(Path(__file__).parent.parent / "x_playwright_data")


async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        Path(X_DATA_DIR).mkdir(parents=True, exist_ok=True)
        ctx = await pw.chromium.launch_persistent_context(
            X_DATA_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()
        await page.goto("https://x.com/login")
        print("ブラウザが開きました。X にログインしてください。")
        print("ホーム画面が表示されたら自動で保存されます（最大3分待機）...")

        # ホーム画面に到達するまで待つ（最大3分）
        await page.wait_for_url(
            lambda url: "x.com/home" in url or (
                "x.com" in url
                and "login" not in url
                and "signup" not in url
                and "flow" not in url
            ),
            timeout=180000,
        )
        await page.wait_for_timeout(2000)
        await ctx.close()
    print("セッション保存完了！")


if __name__ == "__main__":
    asyncio.run(main())
