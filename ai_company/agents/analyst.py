import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MODELS
from core.base_agent import BaseAgent


class AnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            role="analyst",
            model=MODELS["worker"],
            system_prompt="""あなたはAI企業の財務・事業アナリストです。
収益モデル分析・コスト計算・KPI設定・事業計画・ROI試算を担当します。
数字に基づいた実践的なビジネス判断を支援します。
具体的な数値と根拠を示した分析を提供します。""",
        )
