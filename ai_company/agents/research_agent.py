"""
リサーチエージェント — 投稿前にトレンド情報を収集して記事の具体性を上げる
- feedparser (agent-reachの依存として導入済み) でRSSを取得
- Hatena Hot Entry / Qiita トレンド / TechCrunch JP
"""
import feedparser
import urllib.request
import re
from datetime import datetime

RSS_SOURCES = {
    "ai_productivity": [
        "https://b.hatena.ne.jp/hotentry/it.rss",
        "https://qiita.com/popular-items/feed",
    ],
    "side_hustle": [
        "https://b.hatena.ne.jp/hotentry/general.rss",
        "https://b.hatena.ne.jp/search/tag?q=%E5%89%AF%E6%A5%AD&mode=rss",
    ],
    "marketing": [
        "https://b.hatena.ne.jp/hotentry/it.rss",
        "https://b.hatena.ne.jp/search/tag?q=SNS&mode=rss",
    ],
    "investing": [
        "https://b.hatena.ne.jp/hotentry/general.rss",
        "https://b.hatena.ne.jp/search/tag?q=%E6%8A%95%E8%B3%87&mode=rss",
    ],
    "programming": [
        "https://b.hatena.ne.jp/hotentry/it.rss",
        "https://qiita.com/popular-items/feed",
    ],
}

_NOISE = re.compile(
    r"(はてなブックマーク|はてな|ホットエントリー|Qiita|TechCrunch|PR|広告|掲載)", re.I
)


def _fetch_entries(url: str, limit: int = 5) -> list[str]:
    try:
        feed = feedparser.parse(url)
        titles = []
        for entry in feed.entries[:limit]:
            t = entry.get("title", "").strip()
            if t and not _NOISE.search(t) and len(t) > 10:
                titles.append(t)
        return titles
    except Exception:
        return []


def get_trending_context(topic: str) -> str:
    """
    トピックに関連するRSSトレンドを取得し、記事プロンプトに挿入できる文字列で返す。
    取得失敗時は空文字列を返す（後続処理をブロックしない）。
    """
    urls = RSS_SOURCES.get(topic, RSS_SOURCES["ai_productivity"])
    all_titles: list[str] = []
    for url in urls:
        all_titles.extend(_fetch_entries(url, limit=5))

    if not all_titles:
        return ""

    # 重複除去・先頭10件
    seen = set()
    unique = []
    for t in all_titles:
        if t not in seen:
            seen.add(t)
            unique.append(t)
        if len(unique) >= 10:
            break

    date_str = datetime.now().strftime("%Y年%m月%d日")
    lines = "\n".join(f"- {t}" for t in unique)
    return (
        f"【{date_str}時点のトレンド記事（参考にして鮮度のある内容にすること）】\n"
        f"{lines}\n"
        f"上記のトレンドを踏まえ、今まさに読者が関心を持つ具体的な事例・数字を記事に盛り込んでください。"
    )
