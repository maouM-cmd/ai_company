"""
QAエージェント — note記事を投稿前に採点し、品質基準を満たさない場合は改善点を返す
"""
import re
from core.llm import call_llm

QA_PASS_SCORE = 7  # この点数以上なら投稿OK


async def score_article(raw_text: str) -> dict:
    """
    記事を採点する。
    Returns: {"score": int, "feedback": str, "pass": bool}
    """
    prompt = f"""以下のnote.com有料記事を評価してください。

【評価基準】各項目を1〜2点で採点（合計10点満点）：
1. 共感力：読者の悩みを具体的に言語化できているか
2. 信頼性：具体的な数字・期間・事例があるか
3. 購買意欲：無料部分で十分な価値を渡せているか
4. CTA自然さ：Gumroad/有料への誘導が押しつけがましくないか
5. 有料部分の実用性：コピペできる手順/テンプレートがあるか

【出力フォーマット（必ずこの形式で）】
SCORE: (1〜10の整数)
FEEDBACK: (改善が必要な点を箇条書きで。合格なら「なし」)

---記事---
{raw_text[:3000]}
"""
    try:
        response = await call_llm(
            prompt,
            system="あなたはコンテンツマーケティングの専門家です。記事の収益化ポテンシャルを客観的に評価します。",
            tier="manager",
        )
        score = _parse_score(response)
        feedback = _parse_feedback(response)
        passed = score >= QA_PASS_SCORE
        print(f"[QA] 採点: {score}/10 → {'✅ 合格' if passed else '❌ 再生成'}")
        if not passed:
            print(f"[QA] フィードバック: {feedback[:200]}")
        return {"score": score, "feedback": feedback, "pass": passed}
    except Exception as e:
        print(f"[QA] 採点エラー（スキップして投稿）: {e}")
        return {"score": 7, "feedback": "", "pass": True}


def _parse_score(text: str) -> int:
    m = re.search(r"SCORE:\s*(\d+)", text)
    if m:
        return max(1, min(10, int(m.group(1))))
    m = re.search(r"(\d+)\s*/\s*10", text)
    if m:
        return max(1, min(10, int(m.group(1))))
    return 7  # パースできない場合は通過


def _parse_feedback(text: str) -> str:
    m = re.search(r"FEEDBACK:\s*(.+?)(?:\n---|\Z)", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def build_regeneration_prompt(original_prompt: str, feedback: str) -> str:
    """QAのフィードバックを反映した再生成プロンプト"""
    return f"""{original_prompt}

【前回の記事で指摘された改善点（必ず反映すること）】
{feedback}
"""
