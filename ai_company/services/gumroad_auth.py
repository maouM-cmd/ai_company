"""
Gumroad 初回ログイン用スクリプト（1回だけ実行）

実行方法:
    python services/gumroad_auth.py

ブラウザが開くのでGumroadにログインしてください。
ログイン完了を自動検知してセッションを保存します。
"""
import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

GUMROAD_DATA_DIR = str(Path(__file__).parent.parent / "gumroad_playwright_data")


async def main():
    from playwright.async_api import async_playwright

    print("=== Gumroad 初回ログイン ===")
    print(f"セッション保存先: {GUMROAD_DATA_DIR}")
    Path(GUMROAD_DATA_DIR).mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            GUMROAD_DATA_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            slow_mo=100,
        )
        page = await ctx.new_page()
        await page.goto("https://gumroad.com/login")
        print("ブラウザが開きました。Gumroadにログインしてください。")
        print("ログイン完了を自動検知します（最大3分待機）...")

        try:
            # Gumroadのダッシュボードに到達するまで待つ（Google OAuth完了後）
            await page.wait_for_url(
                lambda url: (
                    "gumroad.com" in url
                    and "accounts.google.com" not in url
                    and "gumroad.com/login" not in url
                    and "gumroad.com/signup" not in url
                    and "gumroad.com/users/auth" not in url
                ),
                timeout=180000,
            )
            print(f"✅ Gumroadにログイン成功: {page.url}")
            # Cookieをフラッシュするために少し待つ
            await page.wait_for_timeout(2000)
            print("✅ セッションを保存しました。")
        except Exception as e:
            print(f"⏱️ タイムアウトまたはエラー: {e}")

        await ctx.close()
    print("完了。Gumroad商品生成時にPDFが自動アップロードされます。")


if __name__ == "__main__":
    asyncio.run(main())
