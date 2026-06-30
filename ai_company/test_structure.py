"""APIキーなしで動作確認できる構造テスト（google-genai対応版）"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    from core.message import Message
    from core.memory import OrgMemory
    from core.orchestrator import Orchestrator
    from agents.engineer import EngineerAgent
    from agents.writer import WriterAgent
    from agents.researcher import ResearcherAgent
    from agents.analyst import AnalystAgent
    print("✓ 全インポート成功")


def test_message():
    from core.message import Message
    msg = Message(
        from_agent="CEO",
        to_agent="engineer",
        type="task",
        content={"instruction": "テスト", "task_id": "t001"},
    )
    assert msg.from_agent == "CEO"
    assert msg.type == "task"
    print(f"✓ Message作成成功: {msg}")


def test_memory():
    from core.memory import OrgMemory
    mem = OrgMemory("memory/test.db")
    mem.save("test_agent", "test_key", {"data": "hello"})
    val = mem.load("test_agent", "test_key")
    assert val == {"data": "hello"}, f"Got: {val}"
    mem.log_task("t_struct_001", "engineer", "コードを書く")
    mem.complete_task("t_struct_001", "完了しました")
    tasks = mem.recent_tasks()
    assert len(tasks) >= 1
    stats = mem.kpi_stats()
    assert "total_tasks" in stats
    print("✓ Memory保存・取得・KPI成功")


def test_tool_conversion():
    """Anthropic形式→google-genai形式ツール変換テスト"""
    from agents.engineer import EngineerAgent
    agent = EngineerAgent()
    raw = agent._define_tools()
    converted = agent._convert_tools(raw)
    assert converted is not None
    assert len(converted) == 1
    assert converted[0].function_declarations[0].name == "write_file"
    print(f"✓ ツール変換成功: {[f.name for f in converted[0].function_declarations]}")


async def test_message_routing():
    """エージェント間のメッセージルーティングをモックでテスト"""
    from core.message import Message
    from google.genai import types

    # Gemini レスポンスのモック
    mock_part = MagicMock()
    mock_part.text = "モック結果です"
    mock_part.function_call = None

    mock_candidate = MagicMock()
    mock_candidate.content.parts = [mock_part]

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("core.base_agent._get_client", return_value=mock_client):
        from agents.writer import WriterAgent
        agent = WriterAgent()

        received = []
        async def capture(msg):
            received.append(msg)

        agent.set_send_func(capture)

        msg = Message(
            from_agent="CEO",
            to_agent="writer",
            type="task",
            content={"instruction": "記事を書いて", "task_id": "t_test_route"},
        )
        await agent.inbox.put(msg)

        task = asyncio.create_task(agent.run())
        await asyncio.sleep(0.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(received) == 1
        assert received[0].from_agent == "writer"
        assert received[0].type == "report"
        print(f"✓ メッセージルーティング成功: {received[0]}")


async def test_orchestrator_decompose():
    """オーケストレーターのタスク分解をモックでテスト"""
    from core.orchestrator import Orchestrator
    from agents.writer import WriterAgent

    mock_response = MagicMock()
    mock_response.text = '[{"role": "writer", "instruction": "記事を書く"}]'

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("core.orchestrator._get_client", return_value=mock_client):
        org = Orchestrator()
        writer = WriterAgent()
        org.register(writer)

        subtasks = await org._decompose_task("ブログ記事を書いてください")
        assert len(subtasks) >= 1
        assert subtasks[0]["role"] == "writer"
        print(f"✓ タスク分解成功: {subtasks}")


if __name__ == "__main__":
    print("=== 構造テスト開始（google-genai版）===\n")
    test_imports()
    test_message()
    test_memory()
    test_tool_conversion()
    asyncio.run(test_message_routing())
    asyncio.run(test_orchestrator_decompose())
    print("\n=== 全テスト合格 ✓ ===")
