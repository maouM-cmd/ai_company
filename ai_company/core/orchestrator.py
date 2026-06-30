"""
Orchestrator: CEOレベルのタスク分解・割当・統合
ポケモンAIの「フェーズ順序実行 + コンテキストルーティング」パターンを転用
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import TASK_TIMEOUT_SEC
from core.llm import call_llm
from core.memory import OrgMemory
from core.message import Message

_CEO_SYSTEM = "あなたはAI企業のCEOです。"


class Orchestrator:
    """CEO: タスクを受け取り、分解し、各エージェントに割り当て、結果を統合"""

    _APPROVAL_KEYWORDS = ["公開", "送信", "削除", "決定", "契約", "支払", "リリース", "deploy", "publish"]

    def __init__(self):
        self.agents: dict[str, object] = {}
        self._pending: dict[str, asyncio.Future] = {}
        self.memory = OrgMemory()
        self.approval_handler = None  # API層から設定: async (task_id, task) -> bool

    def register(self, agent):
        self.agents[agent.role] = agent
        agent.set_send_func(self._receive_report)

    async def _receive_report(self, message: Message):
        task_id = message.content.get("task_id")
        if task_id and task_id in self._pending:
            future = self._pending[task_id]
            if not future.done():
                future.set_result(message)

    def _requires_approval(self, task: str) -> bool:
        return any(kw in task for kw in self._APPROVAL_KEYWORDS)

    def _parse_json(self, text: str, fallback):
        """JSONを安全に抽出・パース。失敗時は fallback を返す"""
        text = text.strip()
        if "```" in text:
            for part in text.split("```"):
                part = part.strip().lstrip("json").strip()
                if part.startswith(("{", "[")):
                    text = part
                    break
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return fallback

    async def plan_task(self, task: str) -> dict:
        """タスクを実行せず計画書だけ生成（プランモード用）"""
        print(f"\n[CEO] ━━━ プラン作成 ━━━")
        print(f"[CEO] {task}")

        subtasks = await self._decompose_task(task)

        available = list(self.agents.keys())
        agent_desc = {r: getattr(self.agents[r], 'system_prompt', '')[:80] for r in available}

        prompt = f"""タスク: {task}
実行予定の担当者: {json.dumps(subtasks, ensure_ascii=False)}

このタスクを実行する前に確認すべき懸念点・質問があればJSONで返してください。
なければ空リスト。マークダウンなし、JSONのみ:
{{"concerns": ["懸念点があれば"], "questions": ["確認事項があれば"]}}"""

        text = await call_llm(prompt, _CEO_SYSTEM, "ceo")
        cq = self._parse_json(text, {"concerns": [], "questions": []})

        plan = {
            "summary": task,
            "subtasks": subtasks,
            "concerns": cq.get("concerns", []),
            "questions": cq.get("questions", []),
        }
        print(f"[CEO] プラン完成: {len(subtasks)}件のサブタスク")
        return plan

    async def _generate_suggestions(self, task: str, result: str) -> list[str]:
        """タスク完了後、改善点・懸念・確認事項を能動的に生成"""
        prompt = f"""タスク: {task}

実行結果（抜粋）:
{result[:600]}

この結果について、以下の観点で気づいた点を日本語で3つ以内にリストアップしてください。
- 品質改善できる点
- 潜在的なリスクや懸念
- ユーザーに確認すべきこと
気づきがなければ空リスト。マークダウンなし、JSONのみ:
["提案1", "提案2"]"""

        text = await call_llm(prompt, _CEO_SYSTEM, "ceo")
        result_list = self._parse_json(text, [])
        return result_list if isinstance(result_list, list) else []

    async def execute(self, task: str, task_id: str = "") -> tuple[str, list[str]]:
        """タスクを実行し (結果文字列, 提案リスト) を返す"""
        print(f"\n[CEO] ━━━ タスク実行 ━━━")
        print(f"[CEO] {task}")

        if self._requires_approval(task) and self.approval_handler:
            print(f"[CEO] 人間承認待ち...")
            approved = await self.approval_handler(task_id or task[:20], task)
            if not approved:
                return "このタスクは人間によって却下されました。", []
            print(f"[CEO] 承認済み。実行開始。")

        subtasks = await self._decompose_task(task)
        print(f"[CEO] サブタスク: {[s['role'] for s in subtasks]}")

        results = await asyncio.gather(*[self._assign_task(task, st) for st in subtasks])

        final = await self._synthesize(task, results)
        suggestions = await self._generate_suggestions(task, final)
        if suggestions:
            print(f"[CEO] 提案 {len(suggestions)}件生成")

        return final, suggestions

    async def _decompose_task(self, task: str) -> list[dict]:
        available = list(self.agents.keys())
        agent_desc = {r: getattr(self.agents[r], 'system_prompt', '')[:100] for r in available}

        prompt = f"""以下のタスクを適切な担当者に割り振ります。

タスク: {task}

利用可能な担当者:
{json.dumps(agent_desc, ensure_ascii=False, indent=2)}

マークダウンなし、JSONのみで返答してください:
[{{"role": "担当者名", "instruction": "具体的な指示文"}}]

注意: 同じ担当者を複数回使わない。不要な担当者は含めない。"""

        text = await call_llm(prompt, _CEO_SYSTEM, "ceo")
        subtasks = self._parse_json(text, [])
        if not isinstance(subtasks, list):
            subtasks = []
        valid = [s for s in subtasks if s.get("role") in available]
        if not valid:
            print(f"[CEO] JSON解析失敗、フォールバック実行")
            return [{"role": available[0], "instruction": task}]
        return valid

    async def _assign_task(self, parent_task: str, subtask: dict) -> str:
        role = subtask["role"]
        instruction = subtask["instruction"]
        task_id = f"{role}_{datetime.now().timestamp():.0f}"

        self.memory.log_task(task_id, role, instruction)

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[task_id] = future

        await self.agents[role].inbox.put(Message(
            from_agent="CEO",
            to_agent=role,
            type="task",
            content={"instruction": instruction, "task_id": task_id, "parent_task": parent_task},
            priority=7,
        ))

        try:
            result_msg = await asyncio.wait_for(future, timeout=TASK_TIMEOUT_SEC)
            return result_msg.content.get("result", "（結果なし）")
        except asyncio.TimeoutError:
            return f"[タイムアウト] {role} からの応答がありませんでした"
        finally:
            self._pending.pop(task_id, None)

    async def _synthesize(self, original_task: str, results: list[str]) -> str:
        combined = "\n\n---\n\n".join(f"【{i+1}】\n{r}" for i, r in enumerate(results))
        prompt = f"""元のタスク: {original_task}

各担当者の成果物:
{combined}

上記をまとめ、最終的な回答を作成してください。"""

        return await call_llm(prompt, _CEO_SYSTEM, "ceo")
