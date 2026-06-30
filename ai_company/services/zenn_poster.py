"""
Zenn.dev 自動投稿サービス（GitHub連携方式）

仕組み:
  1. Zennアカウントを GitHub リポジトリに連携（ユーザーが1回だけ設定）
  2. 記事を articles/<slug>.md として保存
  3. git push すると Zenn が自動で公開

セットアップ手順（ユーザーが1回だけ）:
  1. https://zenn.dev でアカウント作成
  2. https://zenn.dev/dashboard/deploys でGitHubリポジトリを連携
  3. ZENN_REPO_DIR を連携したリポジトリのローカルパスに設定
"""
import re
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path

# ── 設定 ──────────────────────────────────────────────────────
ZENN_REPO_DIR = r"C:\Users\admin\zenn-content"   # maouM-cmd/- リポジトリ


def is_configured() -> bool:
    return Path(ZENN_REPO_DIR).exists() and (Path(ZENN_REPO_DIR) / ".git").exists()


def _to_slug(text: str, max_len: int = 50) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.ASCII)
    text = re.sub(r"[\s_]+", "-", text).strip("-").lower()
    if not text:
        text = "article"
    return text[:max_len]


def _extract_title(raw_text: str) -> str:
    m = re.search(r"##\s*タイトル.*?\n(.*?)(?:\n|$)", raw_text)
    if m:
        line = m.group(1).strip()
        c = re.search(r"[「『]([^」』]+)[」』]|^\d+[\.．]\s*(.+)$", line, re.MULTILINE)
        if c:
            return (c.group(1) or c.group(2)).strip()
    m2 = re.search(r"^#+ (.+)$", raw_text, re.MULTILINE)
    return m2.group(1).strip() if m2 else "AI活用・副業ガイド"


def _build_frontmatter(title: str, emoji: str = "💡", topic: str = "idea") -> str:
    return f"""---
title: "{title}"
emoji: "{emoji}"
type: "idea"
topics: ["AI", "副業", "ChatGPT", "副業", "生産性向上"]
published: true
---

"""


EMOJIS = ["💡", "🚀", "💰", "📈", "🎯", "⚡", "🔥", "✨", "💪", "🌟"]


class ZennPoster:
    def post(self, raw_text: str, topic: str = "idea") -> dict:
        if not is_configured():
            return {
                "status": "error",
                "error": (
                    "Zennリポジトリが未設定です。"
                    f" {ZENN_REPO_DIR} にZenn連携済みGitHubリポジトリをcloneしてください。"
                    " セットアップ: https://zenn.dev/dashboard/deploys"
                ),
            }

        title = _extract_title(raw_text)
        date_str = datetime.now().strftime("%Y%m%d-%H%M")
        slug = f"{date_str}-{_to_slug(title)}"

        import random
        emoji = random.choice(EMOJIS)
        frontmatter = _build_frontmatter(title, emoji, topic)

        # 有料マーカー以降は Zenn では掲載しない（無料全文公開）
        body = raw_text
        for marker in ["## 🔒 ここから有料", "ここから有料", "【有料部分】"]:
            if marker in raw_text:
                body = raw_text[:raw_text.index(marker)].strip()
                body += "\n\n---\n\n*続きは [note.com の有料記事](https://note.com) でお読みいただけます。*"
                break

        content = frontmatter + body

        articles_dir = Path(ZENN_REPO_DIR) / "articles"
        articles_dir.mkdir(exist_ok=True)
        filepath = articles_dir / f"{slug}.md"
        filepath.write_text(content, encoding="utf-8")

        try:
            repo = Path(ZENN_REPO_DIR)
            subprocess.run(["git", "add", str(filepath)], cwd=repo, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"Add: {title[:60]}"],
                cwd=repo, check=True, capture_output=True,
            )
            subprocess.run(["git", "push"], cwd=repo, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            return {"status": "error", "error": f"git push 失敗: {e.stderr.decode(errors='replace')}"}

        zenn_url = f"https://zenn.dev/articles/{slug}"
        print(f"[Zenn] 投稿完了: {zenn_url}")
        return {"status": "published", "url": zenn_url, "title": title, "slug": slug}
