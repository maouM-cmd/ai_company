import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MODELS
from core.base_agent import BaseAgent


class EngineerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            role="engineer",
            model=MODELS["worker"],
            system_prompt="""あなたはAI企業のソフトウェアエンジニアです。
コードの設計・実装・デバッグを担当します。
実用的で動作するコードを書き、技術的な問題を解決します。
コードを書く場合は write_file ツールを使ってファイルに保存してください。""",
        )

    def _define_tools(self) -> list:
        return [
            {
                "name": "write_file",
                "description": "コードやテキストをファイルに書き込む",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "保存先ファイル名（output/以下に保存）"},
                        "content": {"type": "string", "description": "ファイルの内容"},
                    },
                    "required": ["filename", "content"],
                },
            }
        ]

    async def _execute_tool(self, name: str, inputs: dict) -> str:
        if name == "write_file":
            try:
                path = Path("output") / inputs["filename"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(inputs["content"], encoding="utf-8")
                return f"✓ {path} に書き込みました（{len(inputs['content'])}文字）"
            except Exception as e:
                return f"書き込みエラー: {e}"
        return f"未知のツール: {name}"
