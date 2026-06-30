"""
Qiita 自動投稿サービス（公式 API 使用）
- Playwright 不要・API トークンだけで動く
- note 記事の無料部分を Qiita に転載し Gumroad への流入を増やす
"""
import json
import re
import urllib.request
from urllib.error import HTTPError

QIITA_API = "https://qiita.com/api/v2/items"

TOPIC_TAGS = {
    "ai_productivity": ["AI", "ChatGPT", "生産性向上", "副業", "自動化"],
    "side_hustle":     ["副業", "フリーランス", "収入", "AI", "ChatGPT"],
    "marketing":       ["マーケティング", "SNS", "集客", "AI", "副業"],
    "investing":       ["資産運用", "投資", "初心者", "お金", "副業"],
    "programming":     ["プログラミング", "IT副業", "フリーランス", "Python", "AI"],
    "default":         ["AI", "ChatGPT", "副業", "生産性向上"],
}


def is_configured() -> bool:
    from config import QIITA_TOKEN
    return bool(QIITA_TOKEN)


def _extract_title(raw_text: str) -> str:
    m = re.search(r"##\s*タイトル.*?\n(.*?)(?:\n|$)", raw_text)
    if m:
        c = re.search(r"[「『]([^」』]+)[」』]|^\d+[\.．]\s*(.+)$", m.group(1), re.MULTILINE)
        if c:
            return (c.group(1) or c.group(2)).strip()
    m2 = re.search(r"^#+ (.+)$", raw_text, re.MULTILINE)
    return m2.group(1).strip() if m2 else "AI・副業実践ガイド"


def _sanitize_for_qiita(text: str) -> str:
    """Qiitaスパム判定を避けるための前処理"""
    # 過度な売り込み表現を緩和
    replacements = [
        ("コピペで今日から使える", "すぐ実践できる"),
        ("今すぐ手に入れる", "詳細はこちら"),
        ("コピペして使える", "参考にできる"),
        ("今すぐ使えるテンプレート", "実践テンプレート"),
        ("✅ コピペで", "・"),
        ("✅ ", "・"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    # 連続する空行を2行以下に
    import re
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _build_body(raw_text: str, products: list) -> str:
    # 有料マーカー以前のみ掲載
    body = raw_text
    for marker in ["## 🔒 ここから有料", "ここから有料", "【有料部分】"]:
        if marker in raw_text:
            body = raw_text[:raw_text.index(marker)].strip()
            break

    # スパム対策の前処理
    body = _sanitize_for_qiita(body)

    # Gumroad CTA（自然な文体で）
    if products:
        import random
        p = random.choice(products)
        url = f"https://springharu.gumroad.com/l/{p['short_url']}"
        price_j = int(p["price_usd"]) * 160
        body += f"""

---

## 関連リソース

この記事のテーマに関連して、実践で使えるテンプレートを公開しています。

[{p['name']}]({url})（¥{price_j}）

詳細な実践手順や事例は [note の記事](https://note.com/springharu) でも読めます。
"""
    return body


class QiitaPoster:
    def post(self, raw_text: str, topic: str = "default", products: list = None) -> dict:
        from config import QIITA_TOKEN
        if not QIITA_TOKEN:
            return {"status": "error", "error": "QIITA_TOKEN が未設定です。.env に追加してください。"}

        title = _extract_title(raw_text)
        body  = _build_body(raw_text, products or [])
        tags  = [{"name": t} for t in TOPIC_TAGS.get(topic, TOPIC_TAGS["default"])[:5]]

        payload = json.dumps({
            "title": title,
            "body": body,
            "tags": tags,
            "private": False,
            "tweet": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            QIITA_API,
            data=payload,
            headers={
                "Authorization": f"Bearer {QIITA_TOKEN}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
                url = data.get("url", "")
                print(f"[Qiita] 投稿完了: {url}")
                return {"status": "published", "url": url, "title": title}
        except HTTPError as e:
            err = e.read().decode(errors="replace")
            print(f"[Qiita] 投稿エラー {e.code}: {err}")
            return {"status": "error", "error": f"HTTP {e.code}: {err[:200]}"}
        except Exception as e:
            print(f"[Qiita] 投稿エラー: {e}")
            return {"status": "error", "error": str(e)}
