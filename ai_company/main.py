"""
AI企業 メインエントリーポイント
使い方:
    python main.py                        # 対話モード
    python main.py "タスク内容"           # 単発タスク実行
    python main.py --demo                 # デモタスク実行
"""
import asyncio
import sys
from pathlib import Path

from core.orchestrator import Orchestrator
from agents.engineer import EngineerAgent
from agents.writer import WriterAgent
from agents.researcher import ResearcherAgent
from agents.analyst import AnalystAgent
from agents.sales import SalesAgent
from agents.product_manager import ProductManagerAgent


def create_company() -> tuple[Orchestrator, list]:
    """AI企業を組織する"""
    org = Orchestrator()

    # 採用
    engineer        = EngineerAgent()
    writer          = WriterAgent()
    researcher      = ResearcherAgent()
    analyst         = AnalystAgent()
    sales           = SalesAgent()
    product_manager = ProductManagerAgent()

    org.register(engineer)
    org.register(writer)
    org.register(researcher)
    org.register(analyst)
    org.register(sales)
    org.register(product_manager)

    agent_list = [engineer, writer, researcher, analyst, sales, product_manager]
    return org, agent_list


async def run_task(task: str):
    print("\n=== AI企業 起動 ===")
    org, agents = create_company()

    # エージェントのバックグラウンドループを起動
    bg_tasks = [asyncio.create_task(a.run()) for a in agents]

    try:
        result = await org.execute(task)
        print(f"\n{'='*60}")
        print("【最終成果物】")
        print('='*60)
        print(result)
        print('='*60)
        return result
    finally:
        for t in bg_tasks:
            t.cancel()
        await asyncio.gather(*bg_tasks, return_exceptions=True)


async def demo():
    tasks = [
        "Pythonでシンプルなタスク管理CLIアプリを設計・実装してください",
        "2026年の生成AIビジネスの主要トレンドを調査し、AI企業が参入すべき市場を提案してください",
        "AI企業（エンジニアリング・コンテンツ制作）の月次収益モデルを設計してください。初期コスト・損益分岐点・目標売上を含めてください",
    ]
    org, agents = create_company()
    bg_tasks = [asyncio.create_task(a.run()) for a in agents]

    try:
        for task in tasks:
            result = await org.execute(task)
            print(f"\n{'='*60}")
            print("【成果物】")
            print(result)
            print('='*60)
            print("\n3秒待機...\n")
            await asyncio.sleep(3)
    finally:
        for t in bg_tasks:
            t.cancel()
        await asyncio.gather(*bg_tasks, return_exceptions=True)


async def interactive():
    print("\n=== AI企業 対話モード ===")
    print("タスクを入力してください（'quit'で終了）\n")
    org, agents = create_company()
    bg_tasks = [asyncio.create_task(a.run()) for a in agents]

    try:
        while True:
            task = input("タスク> ").strip()
            if task.lower() in ("quit", "exit", "終了"):
                break
            if not task:
                continue
            result = await org.execute(task)
            print(f"\n{'='*60}")
            print(result)
            print('='*60 + "\n")
    except KeyboardInterrupt:
        pass
    finally:
        for t in bg_tasks:
            t.cancel()
        await asyncio.gather(*bg_tasks, return_exceptions=True)
    print("\nシャットダウン完了")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        asyncio.run(interactive())
    elif args[0] == "--demo":
        asyncio.run(demo())
    elif args[0] == "--server":
        import uvicorn
        port = int(args[1]) if len(args) > 1 else 8000
        print(f"[SERVER] http://localhost:{port} でダッシュボードを起動します")
        uvicorn.run("api.app:app", host="0.0.0.0", port=port, reload=False)
    else:
        task = " ".join(args)
        asyncio.run(run_task(task))
