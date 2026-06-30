"""
Fiverr 初回ログイン用スクリプト（1回だけ実行）

実行方法:
    python services/fiverr_auth.py

ブラウザが開くのでFiverrにログインしてください。
ログイン完了後 Enter を押すとセッションが保存されます。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PLAYWRIGHT_DATA_DIR = str(Path(__file__).parent.parent / "playwright_data")


async def main():
    from playwright.async_api import async_playwright

    print("=== Fiverr 初回ログイン ===")
    print(f"セッション保存先: {PLAYWRIGHT_DATA_DIR}")
    print()

    Path(PLAYWRIGHT_DATA_DIR).mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            PLAYWRIGHT_DATA_DIR,
            headless=False,  # ブラウザを表示
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = await ctx.new_page()
        await page.goto("https://www.fiverr.com/login")

        print("ブラウザが開きました。Fiverr にログインしてください。")
        print("ログイン完了後、ここで Enter を押してください...")
        input()

        # ログイン確認
        await page.goto("https://www.fiverr.com/orders")
        await page.wait_for_load_state("networkidle", timeout=10000)

        if "login" in page.url or "signup" in page.url:
            print("❌ ログインできていません。もう一度試してください。")
        else:
            print("✅ ログイン成功！セッションを保存しました。")
            print("今後はサーバー起動時に自動でFiverrを監視します。")

        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
