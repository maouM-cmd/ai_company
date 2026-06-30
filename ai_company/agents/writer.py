import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MODELS
from core.base_agent import BaseAgent


class WriterAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            role="writer",
            model=MODELS["worker"],
            system_prompt="""あなたはAI企業のライター・コンテンツクリエイターです。
ブログ記事・ドキュメント・マーケティング文章・SNS投稿などの制作を担当します。
読みやすく、魅力的で、目的に合ったコンテンツを作成します。
日本語・英語どちらでも対応可能です。""",
        )
