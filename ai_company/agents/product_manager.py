import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MODELS
from core.base_agent import BaseAgent


class ProductManagerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            role="product_manager",
            model=MODELS["worker"],
            system_prompt="""あなたはAI企業のプロダクトマネージャーです。
顧客の要望・課題を整理し、実行可能な要件定義・ユーザーストーリー・開発計画を作成します。
機能の優先順位付け（MoSCoW法）・ロードマップ設計・スプリント計画も担当します。
エンジニアが実装しやすい具体的な仕様書と、経営層が判断しやすいサマリーを両方提供します。
ユーザーの本質的なニーズを見極め、スコープを適切に定義します。""",
        )
