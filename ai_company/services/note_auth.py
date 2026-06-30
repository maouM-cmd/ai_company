"""
note.com 初回ログイン用スクリプト（1回だけ実行）

実行方法:
    python services/note_auth.py

ブラウザが開くのでnote.comにログインしてください。
ホーム画面が表示されたら自動でセッションが保存されます。
"""
import asyncio
from pathlib import Path

NOTE_DATA_DIR = str(Path(__file__).parent.parent / "note_playwright_data")


async def main():
    from playwright.async_api import async_playwright

    print("=== note.com ログイン ===")
    print(f"セッション保存先: {NOTE_DATA_DIR}")
    Path(NOTE_DATA_DIR).mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            NOTE_DATA_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()
        await page.goto("https://note.com/login")

        print("ブラウザが開きました。note.com にログインしてください。")
        print("ホーム画面が表示されたら自動で保存されます（最大3分待機）...")

        # ログイン完了を自動検出
        await page.wait_for_url(
            lambda url: (
                "note.com" in url
                and "login" not in url
                and "signup" not in url
                and "auth" not in url
            ),
            timeout=180000,
        )
        await page.wait_for_timeout(2000)
        await ctx.close()

    print("✅ セッション保存完了！")


if __name__ == "__main__":
    asyncio.run(main())
