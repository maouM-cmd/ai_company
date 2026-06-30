import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MODELS
from core.base_agent import BaseAgent


class ResearcherAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            role="researcher",
            model=MODELS["worker"],
            system_prompt="""あなたはAI企業のリサーチャー・アナリストです。
市場調査・競合分析・トレンド分析・データ解析・レポート作成を担当します。
web_search ツールが利用可能な場合は積極的に使用し、最新情報を取得してください。
ツールが使えない場合は知識の範囲で最善の調査を行い、不確かな部分は明記します。
論理的で根拠のある分析結果を提供します。""",
        )

    def _define_tools(self) -> list:
        return [
            {
                "name": "web_search",
                "description": "DuckDuckGoでWeb検索し、上位5件のタイトルと概要を返す",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "検索クエリ（日本語・英語可）"}
                    },
                    "required": ["query"],
                },
            }
        ]

    async def _execute_tool(self, name: str, inputs: dict) -> str:
        if name == "web_search":
            return await self._web_search(inputs.get("query", ""))
        return f"未知のツール: {name}"

    async def _web_search(self, query: str) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            def _search():
                from duckduckgo_search import DDGS
                results = DDGS().text(query, max_results=5)
                if not results:
                    return "検索結果が見つかりませんでした。"
                return "\n\n".join(
                    f"【{r.get('title', 'タイトルなし')}】\n{r.get('body', '')}"
                    for r in results
                )
            return await loop.run_in_executor(None, _search)
        except Exception as e:
            return f"Web検索エラー: {e}"
