import asyncio
import sys
from pathlib import Path

from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GEMINI_API_KEY, MAX_TOKENS, MODELS
from core.llm import call_llm, is_using_ollama
from core.message import Message
from core.memory import OrgMemory

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


class BaseAgent:
    """全エージェントの基底クラス"""

    def __init__(self, role: str, model: str, system_prompt: str):
        self.role = role
        self.model_name = model
        self.system_prompt = system_prompt
        self.inbox: asyncio.Queue[Message] = asyncio.Queue()
        self.memory = OrgMemory()
        self._send_func = None

    def set_send_func(self, func):
        self._send_func = func

    async def run(self):
        print(f"  [{self.role}] 起動")
        while True:
            message = await self.inbox.get()
            try:
                result = await self._process(message)
                if result and self._send_func:
                    await self._send_func(result)
            except Exception as e:
                print(f"  [{self.role}] エラー: {e}")
                if self._send_func:
                    await self._send_func(Message(
                        from_agent=self.role,
                        to_agent=message.from_agent,
                        type="report",
                        content={"result": f"エラーが発生しました: {e}", "task_id": message.content.get("task_id")},
                        priority=message.priority,
                    ))
            finally:
                self.inbox.task_done()

    def _build_context(self, instruction: str) -> str:
        similar = self.memory.load_similar_cases(instruction[:30])
        if not similar:
            return instruction
        cases_text = "\n".join(
            f"- 過去タスク: {c['instruction'][:60]}\n  結果抜粋: {(c['result'] or '')[:120]}..."
            for c in similar
        )
        return f"【参考: 過去の類似ケース】\n{cases_text}\n\n【今回の指示】\n{instruction}"

    async def _process(self, message: Message) -> Message | None:
        instruction = message.content.get("instruction", "")
        task_id = message.content.get("task_id", "")
        print(f"  [{self.role}] 作業開始: {instruction[:60]}...")

        context = self._build_context(instruction)
        response = await self._call_llm(context)

        self.memory.complete_task(task_id, response)
        print(f"  [{self.role}] 完了")
        return Message(
            from_agent=self.role,
            to_agent=message.from_agent,
            type="report",
            content={"result": response, "task_id": task_id},
            priority=message.priority,
        )

    def _convert_tools(self, tools: list) -> list[types.Tool] | None:
        if not tools:
            return None
        declarations = [
            types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t["input_schema"],
            )
            for t in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    async def _call_llm(self, prompt: str) -> str:
        """Gemini（ツール対応）またはOllama（テキストのみ）で応答を生成"""
        if is_using_ollama():
            return await call_llm(prompt, self.system_prompt, "worker")
        return await self._call_gemini_with_tools(prompt)

    async def _call_gemini_with_tools(self, prompt: str) -> str:
        """Gemini SDK でツール付き呼び出し（Gemini専用）"""
        raw_tools = self._define_tools()
        gemini_tools = self._convert_tools(raw_tools)

        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            max_output_tokens=MAX_TOKENS.get("worker", 2048),
            tools=gemini_tools,
        )

        loop = asyncio.get_event_loop()

        # call_llm のフォールバック機構を使って Gemini を呼ぶ
        # （ツール付きなので直接 SDK を呼ぶが、失敗時は call_llm 経由でOllamaへ）
        try:
            response = await loop.run_in_executor(
                None,
                lambda: _get_client().models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config,
                )
            )
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                # フォールバック（ツールなし）
                return await call_llm(prompt, self.system_prompt, "worker")
            raise

        result_parts = []
        for part in response.candidates[0].content.parts:
            if part.text:
                result_parts.append(part.text)
            elif part.function_call:
                fn = part.function_call
                tool_out = await self._execute_tool(fn.name, dict(fn.args))
                result_parts.append(f"[{fn.name}]: {tool_out}")

                tool_result_part = types.Part.from_function_response(
                    name=fn.name,
                    response={"result": tool_out},
                )
                response2 = await loop.run_in_executor(
                    None,
                    lambda: _get_client().models.generate_content(
                        model=self.model_name,
                        contents=[
                            types.Content(role="user", parts=[types.Part.from_text(text=prompt)]),
                            response.candidates[0].content,
                            types.Content(role="user", parts=[tool_result_part]),
                        ],
                        config=config,
                    )
                )
                for part2 in response2.candidates[0].content.parts:
                    if part2.text:
                        result_parts.append(part2.text)

        return "\n".join(result_parts) if result_parts else "(応答なし)"

    def _define_tools(self) -> list:
        return []

    async def _execute_tool(self, name: str, inputs: dict) -> str:
        return f"ツール '{name}' は未実装"
