import sys
import json
import time
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MODELS
from core.base_agent import BaseAgent

OPENCLAW_WORKSPACE = Path(r"C:\Users\admin\.openclaw-autoclaw\workspace")
TASKS_DIR = OPENCLAW_WORKSPACE / "tasks"
RESULTS_DIR = OPENCLAW_WORKSPACE / "results"

class OpenClawAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            role="openclaw_operator",
            model=MODELS["worker"],
            system_prompt="""あなたはAI企業のRPAオペレーター（OpenClaw Agent）です。
実際のWebブラウザの操作、画面のスクリーンショットの撮影、複雑なUIの自動化などを担当します。
ブラウザ操作や画面確認が必要なタスクが来た場合は、「delegate_to_openclaw」ツールを使って
バックグラウンドのOpenClawシステムに処理を委譲し、その結果を報告してください。""",
        )

    def _define_tools(self) -> list:
        return [
            {
                "name": "delegate_to_openclaw",
                "description": "OpenClawシステムにRPAやブラウザ操作タスクを委譲して結果を受け取る",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "一意のタスクID（例: task_001）"},
                        "description": {"type": "string", "description": "OpenClawに実行させたい操作の詳細"},
                    },
                    "required": ["task_id", "description"],
                },
            }
        ]

    async def _execute_tool(self, name: str, inputs: dict) -> str:
        if name == "delegate_to_openclaw":
            task_id = inputs["task_id"]
            description = inputs["description"]
            
            TASKS_DIR.mkdir(parents=True, exist_ok=True)
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            
            task_file = TASKS_DIR / f"{task_id}.json"
            result_file = RESULTS_DIR / f"{task_id}.json"
            
            # Write task to workspace
            task_data = {
                "task_id": task_id,
                "description": description,
                "timestamp": time.time()
            }
            try:
                task_file.write_text(json.dumps(task_data, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                return f"OpenClawへのタスク送信に失敗しました: {e}"
            
            # Poll for result
            timeout = 120  # wait up to 120 seconds
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if result_file.exists():
                    try:
                        res_data = json.loads(result_file.read_text(encoding="utf-8"))
                        result_file.unlink()  # Clean up
                        return f"OpenClaw 実行完了: {res_data.get('result', 'No result field')}"
                    except Exception as e:
                        return f"OpenClaw 結果読み取りエラー: {e}"
                await asyncio.sleep(2)
                
            return "OpenClawのタスク実行がタイムアウトしました。"
            
        return f"未知のツール: {name}"
