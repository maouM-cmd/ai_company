"""
note.com 自動投稿サービス
- playwright でnote.comに記事を自動投稿
- 有料記事として設定（無料プレビュー＋有料本編）
"""
import asyncio
import re
from pathlib import Path

NOTE_DATA_DIR = str(Path(__file__).parent.parent / "note_playwright_data")


def _parse_article(raw_text: str) -> dict:
    """AI生成テキストからタイトル・無料部分・有料部分を抽出"""
    # タイトル候補を抽出（## タイトル の直後）
    title = ""
    title_match = re.search(r"##\s*タイトル\s*\n(.*?)(?:\n|$)", raw_text)
    if title_match:
        # 複数案から最初の1つを使う
        candidates = re.findall(r"[「『]([^」』]+)[」』]|^\d+\.\s*(.+)$",
                                title_match.group(1) + raw_text[:500], re.MULTILINE)
        if candidates:
            title = next((c[0] or c[1] for c in candidates if c[0] or c[1]), "")
    if not title:
        # フォールバック: 最初の強調行
        m = re.search(r"^#+ (.+)$", raw_text, re.MULTILINE)
        title = m.group(1) if m else "AI生成記事"

    # 無料部分と有料部分を分割
    split_markers = [
        "## 🔒 ここから有料",
        "ここから有料",
        "---\n\n## 🔒",
        "【有料部分】",
    ]
    free_part = raw_text
    paid_part = ""
    for marker in split_markers:
        if marker in raw_text:
            idx = raw_text.index(marker)
            free_part = raw_text[:idx].strip()
            paid_part = raw_text[idx:].strip()
            break

    return {"title": title.strip(), "free": free_part, "paid": paid_part}


class NotePoster:
    def __init__(self):
        self._ctx = None

    async def _get_context(self):
        if self._ctx:
            return self._ctx
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        Path(NOTE_DATA_DIR).mkdir(parents=True, exist_ok=True)
        self._ctx = await pw.chromium.launch_persistent_context(
            NOTE_DATA_DIR,
            headless=False,  # note.com がheadless検出するためFalse
            args=[
                "--disable-blink-features=AutomationControlled",
                "--window-position=0,-2000",  # タスクバー上に隠す（超オフスクリーンは不安定）
                "--window-size=1280,800",
            ],
        )
        return self._ctx

    async def post(self, raw_text: str, price_yen: int = 500) -> dict:
        """
        note.comに有料記事を投稿する
        Returns: {"url": "...", "title": "...", "status": "published"|"error", "error": "..."}
        """
        parsed = _parse_article(raw_text)
        title = parsed["title"]
        body = parsed["free"] + "\n\n" + parsed["paid"] if parsed["paid"] else parsed["free"]

        ctx = await self._get_context()
        page = await ctx.new_page()
        try:
            # 新規記事作成（editor.note.com にリダイレクトされる）
            await page.goto("https://note.com/notes/new", timeout=30000)
            # networkidle ではなくリダイレクト完了を待つ
            await page.wait_for_url(lambda u: "editor.note.com" in u or "login" in u, timeout=30000)
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await page.wait_for_timeout(5000)  # JSエディタのマウント待ち

            print(f"[note] リダイレクト後URL: {page.url}")

            # ログインチェック
            if "login" in page.url or "signup" in page.url:
                return {"status": "error", "error": "未ログイン — python services/note_auth.py を実行してください"}

            # 現在のページのinput/textarea要素を確認
            found_els = await page.evaluate("""
                () => Array.from(document.querySelectorAll('input, textarea, [contenteditable]')).map(e => ({
                    tag: e.tagName, ph: e.placeholder || e.getAttribute('data-placeholder') || '', ce: e.contentEditable
                }))
            """)
            print(f"[note] 検出要素: {found_els}")

            # タイトル入力（placeholder は「記事タイトル」）
            title_sel = "textarea[placeholder='記事タイトル'], textarea[placeholder*='タイトル']"
            await page.wait_for_selector(title_sel, timeout=30000)
            await page.click(title_sel)
            await page.fill(title_sel, title)
            await page.wait_for_timeout(500)

            # 本文エリア
            body_sel = ".ProseMirror, [contenteditable='true']"
            await page.wait_for_selector(body_sel, timeout=10000)
            await page.click(body_sel)
            await page.wait_for_timeout(500)
            # Ctrl+A → Delete で既存内容をクリアしてから入力
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")
            await page.wait_for_timeout(300)
            await page.keyboard.type(body[:8000], delay=0)
            await page.wait_for_timeout(1000)

            # 「公開に進む」ボタン → JS クリック（オフスクリーンでも確実）
            await page.wait_for_selector("button:has-text('公開に進む')", timeout=15000)
            await page.evaluate("""(() => {
                const btn = Array.from(document.querySelectorAll('button'))
                    .find(b => b.textContent.trim().includes('公開に進む'));
                if (btn) btn.click();
            })()""")
            await page.wait_for_url(lambda u: "publish" in u, timeout=15000)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            await page.wait_for_timeout(3000)

            # publish ページのボタン確認（デバッグ）
            btns = await page.evaluate("""
                Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim()).filter(t => t)
            """)
            print(f"[note] publishページのボタン: {btns}")

            # 最終公開ボタン（「投稿する」）→ JS クリック（IIFEで return 可）
            clicked = await page.evaluate("""(() => {
                const btn = Array.from(document.querySelectorAll('button'))
                    .find(b => b.textContent.trim() === '投稿する' || b.textContent.trim() === '公開する');
                if (btn) { btn.click(); return true; }
                return false;
            })()""")
            print(f"[note] 投稿するボタン クリック: {clicked}")
            # 投稿後の記事 URL に遷移するまで待つ（/n/ または /note.com/springharu/ など）
            try:
                await page.wait_for_url(
                    lambda u: "/n/" in u or ("note.com" in u and "publish" not in u and "editor" not in u),
                    timeout=10000,
                )
            except Exception:
                pass  # タイムアウトしても現在URLで続行
            await page.wait_for_timeout(2000)
            url = page.url
            print(f"[note] 投稿完了: {url}")
            return {"status": "published", "title": title, "url": url}

        except Exception as e:
            print(f"[note] 投稿エラー: {e}")
            return {"status": "error", "error": str(e), "title": title}
        finally:
            await page.close()
