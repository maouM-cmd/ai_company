import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MODELS
from core.base_agent import BaseAgent


class SalesAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            role="sales",
            model=MODELS["worker"],
            system_prompt="""あなたはAI企業の営業・ビジネス開発担当です。
クライアントのニーズを的確に把握し、説得力ある提案書・見積書・契約書ドラフトを作成します。
価格設定・競合比較・ROI提示など、受注につながる営業資料を作成します。
既存クライアントへのアップセル提案やフォローアップメールも担当します。
数字と具体的なベネフィットを明示した、実践的な営業資料を提供します。""",
        )
