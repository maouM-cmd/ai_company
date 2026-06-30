"""
Gumroad PDF アップロード（Playwright使用）
gumroad_auth.py で事前にログインが必要
"""
import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

GUMROAD_DATA_DIR = str(Path(__file__).parent.parent / "gumroad_playwright_data")


async def upload_pdf_to_product(product_short_url: str, pdf_path: str) -> bool:
    """
    指定GumroadのShort URL（例: 'tkdrf'）にPDFをアップロードする
    Returns True on success
    """
    from playwright.async_api import async_playwright

    if not Path(GUMROAD_DATA_DIR).exists():
        raise RuntimeError(
            "Gumroadセッション未保存。先に `python services/gumroad_auth.py` を実行してください。"
        )

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            GUMROAD_DATA_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = await ctx.new_page()

        edit_url = f"https://gumroad.com/products/{product_short_url}/edit/content"
        print(f"[Gumroad] コンテンツ編集ページを開く: {edit_url}")
        await page.goto(edit_url, wait_until="networkidle")

        # ログイン確認（リダイレクトされていたら再ログイン待ち）
        if "login" in page.url or "signup" in page.url:
            print("[Gumroad] セッション期限切れ。ログインしてください（最大2分）...")
            try:
                await page.wait_for_url(
                    lambda url: "gumroad.com/login" not in url and "gumroad.com/signup" not in url,
                    timeout=120000,
                )
                await page.goto(edit_url, wait_until="networkidle")
            except Exception:
                await ctx.close()
                raise RuntimeError("ログインタイムアウト。`python services/gumroad_auth.py` を再実行してください。")

        # file input を取得
        file_input = page.locator('input[type="file"][name="file"]')
        await file_input.wait_for(state="attached", timeout=15000)

        print(f"[Gumroad] PDFをアップロード中: {pdf_path}")

        # ネットワークリクエストをキャプチャ
        captured = []
        page.on("request", lambda r: captured.append(r.url) if r.method in ("POST","PUT") else None)

        # file chooser をJSクリックで開く（pointer-eventsの干渉を回避）
        async with page.expect_file_chooser(timeout=10000) as fc_info:
            await page.evaluate("document.querySelector('input[type=\"file\"][name=\"file\"]').click()")

        file_chooser = await fc_info.value
        await file_chooser.set_files(pdf_path)
        print("[Gumroad] ファイル選択完了。アップロード中...")

        # ネットワークアイドルまで待つ（アップロード完了）
        print("[Gumroad] S3アップロード完了を待機中...")
        try:
            await page.wait_for_load_state("networkidle", timeout=60000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        # デバッグ: 現在のページ状態を確認
        page_text = await page.evaluate("document.body.innerText.slice(0, 200)")
        print(f"[Gumroad] ページ内容: {page_text[:100]!r}")

        all_btns = await page.evaluate(
            "[...document.querySelectorAll('button')].map(b => b.innerText.trim()).filter(t => t).slice(0,10)"
        )
        print(f"[Gumroad] ボタン一覧: {all_btns}")

        # 保存ボタンを探してクリック（テキストに関係なく最初の submit/保存系）
        saved = False
        for btn_text in ["変更を保存する", "保存", "Save changes", "Save"]:
            try:
                btn = page.get_by_text(btn_text, exact=False).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    print(f"[Gumroad] '{btn_text}' ボタンをクリックして保存しました")
                    saved = True
                    break
            except Exception:
                pass

        if not saved:
            await page.keyboard.press("Control+s")
            await page.wait_for_timeout(3000)
            print("[Gumroad] Ctrl+Sで保存を試みました")

        await page.wait_for_timeout(2000)

        # 「Publish and continue」で公開する
        for publish_text in ["Publish and continue", "公開して続ける"]:
            try:
                pub_btn = page.get_by_text(publish_text, exact=False).first
                if await pub_btn.is_visible(timeout=3000):
                    await pub_btn.click()
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    print(f"[Gumroad] '{publish_text}' → 公開完了")
                    break
            except Exception:
                pass

        await page.wait_for_timeout(2000)

        await ctx.close()
        print(f"[Gumroad] アップロード完了: {product_short_url}")
        return True


def upload_pdf_sync(product_short_url: str, pdf_path: str) -> bool:
    return asyncio.run(upload_pdf_to_product(product_short_url, pdf_path))


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("使い方: python services/gumroad_uploader.py <short_url> <pdf_path>")
        print("例:     python services/gumroad_uploader.py tkdrf gumroad_products/prompt_pack.pdf")
        sys.exit(1)
    ok = upload_pdf_sync(sys.argv[1], sys.argv[2])
    print("✅ 成功" if ok else "❌ 失敗")
