"""
SEOエージェント — KeyBERT で記事から関連キーワードを選出し Qiita タグに使う

日本語はスペース区切りがないため、候補リスト方式を採用:
- CANDIDATE_KEYWORDS リストから記事と意味的に近いものを KeyBERT が上位選出
- 候補にないキーワードは出ない（短くて検索されやすいもののみ）
"""
from __future__ import annotations

_kw_model = None  # 遅延ロード（起動時間節約）

# Qiita で検索される可能性の高いキーワード候補
CANDIDATE_KEYWORDS = [
    "AI", "ChatGPT", "Gemini", "Claude", "LLM", "生成AI",
    "副業", "フリーランス", "収入", "月収", "稼ぐ", "副収入",
    "プログラミング", "Python", "JavaScript", "自動化",
    "マーケティング", "SNS", "X", "Instagram", "note", "Zenn",
    "生産性向上", "業務効率化", "時短", "仕事術",
    "資産運用", "投資", "NISA", "積立",
    "プロンプト", "プロンプトエンジニアリング",
    "ブログ", "ライティング", "SEO", "コンテンツ",
    "Gumroad", "情報商材", "デジタルコンテンツ",
    "ChatGPT活用", "AI活用", "副業初心者", "在宅ワーク",
    "転職", "キャリア", "スキルアップ", "独立",
]

FALLBACK_TAGS = {
    "ai_productivity": ["AI", "ChatGPT", "生産性向上", "副業", "自動化"],
    "side_hustle":     ["副業", "フリーランス", "収入", "AI", "ChatGPT"],
    "marketing":       ["マーケティング", "SNS", "集客", "AI", "副業"],
    "investing":       ["資産運用", "投資", "初心者", "お金", "副業"],
    "programming":     ["プログラミング", "IT副業", "フリーランス", "Python", "AI"],
    "default":         ["AI", "ChatGPT", "副業", "生産性向上"],
}


def _get_model():
    global _kw_model
    if _kw_model is None:
        from keybert import KeyBERT
        _kw_model = KeyBERT(model="paraphrase-multilingual-MiniLM-L12-v2")
    return _kw_model


def extract_keywords(text: str, top_n: int = 5) -> list[str]:
    """
    記事テキストに含まれる候補キーワードをBERT埋め込みでランク付けして返す。
    KeyBERTのCountVectorizer（英大文字/日本語非対応）を回避し、
    sentence-transformers の cosine_similarity を直接使う。
    失敗時は空リストを返す。
    """
    try:
        # 記事に含まれる候補だけに絞る
        present = [c for c in CANDIDATE_KEYWORDS if c in text]
        if not present:
            return []

        model = _get_model()
        from sklearn.metrics.pairwise import cosine_similarity
        # SentenceTransformerBackend では embedding_model が実体
        encoder = model.model.embedding_model

        sample = text[:3000]
        text_emb = encoder.encode([sample])
        cand_emb = encoder.encode(present)
        scores = cosine_similarity(text_emb, cand_emb)[0]

        ranked = sorted(zip(present, scores), key=lambda x: x[1], reverse=True)
        keywords = [kw for kw, _score in ranked[:top_n]]
        print(f"[SEO] キーワード抽出: {keywords}")
        return keywords
    except Exception as e:
        print(f"[SEO] キーワード抽出エラー（フォールバックへ）: {e}")
        return []


def get_qiita_tags(raw_text: str, topic: str = "default") -> list[dict]:
    """
    Qiita タグ形式 [{"name": "..."}, ...] を返す。
    KeyBERT 成功時は動的タグ、失敗時は固定テーマタグにフォールバック。
    """
    keywords = extract_keywords(raw_text, top_n=5)
    if keywords:
        return [{"name": kw} for kw in keywords[:5]]
    fallback = FALLBACK_TAGS.get(topic, FALLBACK_TAGS["default"])
    return [{"name": t} for t in fallback[:5]]
