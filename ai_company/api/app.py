"""
AI企業 FastAPI サーバー
起動: uvicorn api.app:app --host 0.0.0.0 --port 8000
または: python main.py --server
"""
import asyncio
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Windows cp932対策: stdout/stderrをUTF-8に
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# .env 読み込み
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            import os as _os; _os.environ.setdefault(_k.strip(), _v.strip())

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from main import create_company
from core.memory import OrgMemory
from core.scheduler import SchedulerService
from services.fiverr_watcher import FiverrWatcher
from services.auto_publisher import AutoPublisher

app = FastAPI(title="AI企業 API", version="1.0.0")

# グローバル状態
_org = None
_agents = []
_bg_agent_tasks: list[asyncio.Task] = []
_task_results: dict[str, dict] = {}
_approval_futures: dict[str, dict] = {}
_scheduler: SchedulerService | None = None
_mem: OrgMemory | None = None
_fiverr_watcher: FiverrWatcher | None = None
_auto_publisher: AutoPublisher | None = None


# ─── 永続化ヘルパー ────────────────────────────────────────────

def _persist(task_id: str):
    if _mem and task_id in _task_results:
        _mem.save_task_record(task_id, _task_results[task_id])


# ─── 起動・終了 ───────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    global _org, _agents, _bg_agent_tasks, _scheduler, _mem, _fiverr_watcher, _auto_publisher
    _mem = OrgMemory()
    _org, _agents = create_company()
    _org.approval_handler = _approval_handler

    # 保存済みタスクを復元
    for record in _mem.load_task_records():
        _task_results[record["task_id"]] = record
    print(f"[API] タスク {len(_task_results)}件を復元しました")

    # 再起動前に処理中だったタスクをリセット
    STUCK_STATUSES = {"processing", "planning", "awaiting_approval"}
    reset_count = 0
    for tid, t in _task_results.items():
        if t.get("status") in STUCK_STATUSES:
            t["status"] = "failed"
            t["result"] = "サーバー再起動により中断されました。再度投入してください。"
            t["completed_at"] = datetime.now().isoformat()
            _persist(tid)
            reset_count += 1
    if reset_count:
        print(f"[API] 中断タスク {reset_count}件をリセットしました")

    # エージェントループ起動
    for agent in _agents:
        t = asyncio.create_task(agent.run())
        _bg_agent_tasks.append(t)

    # スケジューラー起動
    _scheduler = SchedulerService(_mem, _schedule_submit)
    _scheduler.start()

    # Fiverr自動監視起動
    _fiverr_watcher = FiverrWatcher(_mem)
    _fiverr_watcher.start()

    # 自動コンテンツ投稿起動
    _auto_publisher = AutoPublisher(_org, _task_results, _persist, _mem)
    _auto_publisher.start()

    print("[API] AI企業サーバー起動完了")


@app.on_event("shutdown")
async def shutdown():
    if _auto_publisher:
        _auto_publisher.stop()
    if _fiverr_watcher:
        _fiverr_watcher.stop()
    if _scheduler:
        _scheduler.stop()
    for t in _bg_agent_tasks:
        t.cancel()
    await asyncio.gather(*_bg_agent_tasks, return_exceptions=True)


# ─── スケジューラー用タスク投入 ───────────────────────────────

async def _schedule_submit(description: str) -> str:
    task_id = uuid.uuid4().hex[:8]
    base = {
        "task_id": task_id,
        "description": f"[自動] {description}",
        "plan": None,
        "result": None,
        "suggestions": [],
        "submitted_at": datetime.now().isoformat(),
        "completed_at": None,
        "status": "processing",
    }
    _task_results[task_id] = base
    _persist(task_id)
    asyncio.create_task(_run_task(task_id, description))
    return task_id


# ─── 承認ハンドラ ─────────────────────────────────────────────

async def _approval_handler(approval_id: str, task: str) -> bool:
    future: asyncio.Future = asyncio.get_event_loop().create_future()
    _approval_futures[approval_id] = {
        "approval_id": approval_id,
        "task": task,
        "requested_at": datetime.now().isoformat(),
        "future": future,
    }
    try:
        return await asyncio.wait_for(future, timeout=3600)
    except asyncio.TimeoutError:
        _approval_futures.pop(approval_id, None)
        return False


# ─── タスク実行 ───────────────────────────────────────────────

async def _plan_task(task_id: str, description: str):
    try:
        plan = await _org.plan_task(description)
        _task_results[task_id].update({"status": "awaiting_approval", "plan": plan})
        _persist(task_id)
    except Exception as e:
        _task_results[task_id].update({
            "status": "failed",
            "result": f"計画生成エラー: {e}",
            "completed_at": datetime.now().isoformat(),
        })
        _persist(task_id)


async def _run_task(task_id: str, description: str):
    try:
        result, suggestions = await _org.execute(description, task_id=task_id)
        _task_results[task_id].update({
            "status": "completed",
            "result": result,
            "suggestions": suggestions,
            "completed_at": datetime.now().isoformat(),
        })
    except Exception as e:
        _task_results[task_id].update({
            "status": "failed",
            "result": f"エラー: {e}",
            "suggestions": [],
            "completed_at": datetime.now().isoformat(),
        })
    _persist(task_id)


async def _run_task_refined(task_id: str, prompt: str):
    """草稿→批評→改稿の2段階生成（Fiverrギグ向け）"""
    try:
        async with asyncio.timeout(600):  # 10分タイムアウト
            await _run_task_refined_inner(task_id, prompt)
    except asyncio.TimeoutError:
        _task_results[task_id].update({
            "status": "failed",
            "result": "タイムアウト（10分超過）。再度投入してください。",
            "suggestions": [],
            "completed_at": datetime.now().isoformat(),
        })
        _persist(task_id)


async def _run_task_refined_inner(task_id: str, prompt: str):
    """草稿→批評→改稿の実処理"""
    try:
        # Step 1: 草稿生成
        _task_results[task_id]["result"] = "[1/3] 草稿生成中..."
        _persist(task_id)
        draft, _ = await _org.execute(prompt, task_id=task_id)

        # Step 2: 批評
        _task_results[task_id]["result"] = "[2/3] 品質チェック中..."
        _persist(task_id)
        critique_prompt = f"""You are a quality reviewer. Read this draft and identify exactly 3 specific weaknesses:
- Missing information or depth
- Unclear explanations
- Missing structure or sections

Draft:
{draft}

List 3 weaknesses concisely (1-2 sentences each)."""
        critique, _ = await _org.execute(critique_prompt, task_id=task_id)

        # Step 3: 改稿
        _task_results[task_id]["result"] = "[3/3] 改稿中..."
        _persist(task_id)
        refine_prompt = f"""Rewrite and improve the following draft by fixing these weaknesses:

WEAKNESSES TO FIX:
{critique}

ORIGINAL DRAFT:
{draft}

Write the improved version now. Make it significantly better, more detailed, and professional."""
        final, suggestions = await _org.execute(refine_prompt, task_id=task_id)

        _task_results[task_id].update({
            "status": "completed",
            "result": final,
            "suggestions": suggestions,
            "completed_at": datetime.now().isoformat(),
        })
    except Exception as e:
        _task_results[task_id].update({
            "status": "failed",
            "result": f"エラー: {e}",
            "suggestions": [],
            "completed_at": datetime.now().isoformat(),
        })
    _persist(task_id)


# ─── リクエストモデル ─────────────────────────────────────────

class TaskRequest(BaseModel):
    description: str
    priority: int = 5
    plan_mode: bool = True
    project_id: int | None = None

class ScheduleRequest(BaseModel):
    description: str
    time_hhmm: str  # "HH:MM" 形式

class ClientRequest(BaseModel):
    name: str
    company: str = ""
    industry: str = ""
    email: str = ""
    notes: str = ""

class ProjectRequest(BaseModel):
    client_id: int
    name: str
    budget_jpy: int = 0
    due_date: str = ""
    description: str = ""

class RevenueRequest(BaseModel):
    project_id: int | None = None
    type: str  # 'income' or 'expense'
    amount_jpy: int
    description: str
    date: str  # YYYY-MM-DD

class FiverrOrderRequest(BaseModel):
    gig_type: str   # market_research / seo_blog / business_proposal
    topic: str
    requirements: str = ""

FIVERR_TEMPLATES = {
    "market_research": {
        "label": "AI Market Research Report",
        "prompt": (
            "You are a senior market research analyst at a top consulting firm. "
            "Write a comprehensive, data-rich market research report that a business executive would find genuinely useful.\n\n"
            "Topic/Industry: {topic}\n"
            "Client requirements: {requirements}\n\n"
            "# {topic}: Market Analysis Report\n\n"
            "## Executive Summary\n"
            "Write 4-5 sentences covering: market size today, projected size in 5 years (with CAGR %), "
            "the #1 opportunity, and the #1 risk. Make this punchy and actionable.\n\n"
            "## Market Overview\n"
            "- Current global market size (USD, cite a realistic estimate)\n"
            "- 5-year CAGR projection (%)\n"
            "- Top 3 demand drivers (explain each in 2-3 sentences)\n"
            "- Top 2 headwinds or risks\n"
            "- Key geographic markets (which regions lead and why)\n\n"
            "## Competitive Landscape\n"
            "List the top 5 players. For each: company name, market position, "
            "one key strength, one weakness, approximate revenue/market share if known.\n\n"
            "## Emerging Trends (Top 4)\n"
            "For each trend: name it, explain the mechanism, quantify the opportunity where possible, "
            "and say what companies should do in response.\n\n"
            "## Customer Segmentation\n"
            "Identify 3 distinct customer segments. For each: who they are, what they need, "
            "how to reach them, approximate segment size.\n\n"
            "## Strategic Opportunities for New Entrants\n"
            "Give 3 concrete, specific recommendations with reasoning. Not generic advice — "
            "actual tactics this specific market rewards.\n\n"
            "## Conclusion & Recommendations\n"
            "5-7 bullet action items ranked by priority. Each bullet should be actionable within 90 days.\n\n"
            "Target: 1,200-1,500 words. Use tables where helpful. Professional, precise language. "
            "Every statistic should be plausible and specific."
        ),
    },
    "seo_blog": {
        "label": "SEO Blog Article",
        "prompt": (
            "You are an expert SEO content writer. Write a high-ranking, genuinely valuable blog article. "
            "Real readers should find this useful, not just optimized for search.\n\n"
            "Topic: {topic}\n"
            "Target keywords / client requirements: {requirements}\n\n"
            "STRUCTURE TO FOLLOW:\n\n"
            "**Title:** Write a compelling H1 (include the primary keyword naturally, under 60 chars)\n\n"
            "**Meta Description (160 chars max):** For SEO preview — include primary keyword, clear benefit, CTA word.\n\n"
            "**Introduction (150 words):**\n"
            "Open with a surprising stat or relatable pain point. Hook the reader in sentence 1. "
            "State the problem clearly. Promise what they'll learn. Include primary keyword in first 100 words.\n\n"
            "**Section 1 — [H2: Core concept or problem]:**\n"
            "Explain the 'what' and 'why'. Use a real example. 200-250 words.\n\n"
            "**Section 2 — [H2: The main solution/approach]:**\n"
            "Step-by-step or framework. Use H3 subsections if helpful. 250-300 words.\n\n"
            "**Section 3 — [H2: Advanced tips or common mistakes]:**\n"
            "3-5 specific, practical points. Include at least one counterintuitive insight. 200 words.\n\n"
            "**Section 4 — [H2: Real-world example or case study]:**\n"
            "Concrete scenario or mini case study showing the concept in action. 150 words.\n\n"
            "**FAQ (3 questions):**\n"
            "Answer questions people actually search for about this topic. Each answer 40-60 words.\n\n"
            "**Conclusion + CTA:**\n"
            "Summarize the key takeaway in 2 sentences. End with a clear call-to-action. 80 words.\n\n"
            "TARGET: 1,100-1,300 words total. Keyword density 1-2%. No keyword stuffing. "
            "Conversational but authoritative tone. Use bold for key terms."
        ),
    },
    "business_proposal": {
        "label": "Business Proposal",
        "prompt": (
            "You are a senior business consultant writing a proposal that will be read by investors or C-suite executives. "
            "Make it persuasive, specific, and backed by numbers.\n\n"
            "Company/Project: {topic}\n"
            "Client requirements: {requirements}\n\n"
            "# Business Proposal: {topic}\n\n"
            "## Executive Summary (1 paragraph, ~100 words)\n"
            "The single most important pitch. What problem, what solution, what market size, "
            "what you're asking for, and what the return looks like. Make every word count.\n\n"
            "## Problem Statement\n"
            "- Describe the pain point in concrete terms (who suffers, how much it costs them)\n"
            "- Quantify the problem (market data, survey stats, or industry benchmarks)\n"
            "- Why existing solutions fall short (2-3 specific gaps)\n\n"
            "## Our Solution\n"
            "- What it is (explain clearly in plain language)\n"
            "- How it works (3-4 key steps or features)\n"
            "- Why it's better than alternatives (specific differentiation, not generic claims)\n\n"
            "## Market Opportunity\n"
            "- Total Addressable Market (TAM): $X billion\n"
            "- Serviceable Addressable Market (SAM): $X million\n"
            "- Serviceable Obtainable Market (SOM): $X million (realistic 3-year target)\n"
            "- Why now? What macro trend makes this the right moment?\n\n"
            "## Business Model & Revenue Streams\n"
            "Explain how you make money. Be specific: pricing model, average contract value, "
            "margins, recurring vs. one-time revenue.\n\n"
            "## Competitive Advantage (Moat)\n"
            "List 3 defensible advantages. For each: what it is, why competitors can't easily copy it.\n\n"
            "## Financial Projections (3-Year)\n"
            "Create a simple table: Year 1 / Year 2 / Year 3 showing Revenue, Gross Profit, Customers.\n"
            "Add 2-3 key assumptions that drive these numbers.\n\n"
            "## The Ask\n"
            "What are you requesting? Amount, equity (if applicable), use of funds "
            "(break it down: 40% product, 30% marketing, etc.).\n\n"
            "## Next Steps\n"
            "3-4 concrete actions to move forward. Include a proposed timeline.\n\n"
            "TARGET: 900-1,100 words. Numbers everywhere possible. No vague claims — "
            "every assertion should be supported by data or logic."
        ),
    },
}


# ─── タスクエンドポイント ─────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = Path(__file__).parent / "dashboard.html"
    return html_path.read_text(encoding="utf-8")


@app.post("/tasks", status_code=202)
async def create_task(req: TaskRequest):
    if not req.description.strip():
        raise HTTPException(400, detail="タスクの説明が空です")
    task_id = uuid.uuid4().hex[:8]
    base = {
        "task_id": task_id,
        "description": req.description,
        "plan": None,
        "result": None,
        "suggestions": [],
        "submitted_at": datetime.now().isoformat(),
        "completed_at": None,
        "project_id": req.project_id,
    }
    if req.plan_mode:
        _task_results[task_id] = {**base, "status": "planning"}
        _persist(task_id)
        asyncio.create_task(_plan_task(task_id, req.description))
        return {"task_id": task_id, "status": "planning"}
    else:
        _task_results[task_id] = {**base, "status": "processing"}
        _persist(task_id)
        asyncio.create_task(_run_task(task_id, req.description))
        return {"task_id": task_id, "status": "accepted"}


@app.post("/tasks/{task_id}/approve")
async def approve_plan(task_id: str):
    if task_id not in _task_results:
        raise HTTPException(404, detail="タスクが見つかりません")
    task = _task_results[task_id]
    if task["status"] != "awaiting_approval":
        raise HTTPException(400, detail=f"承認待ち状態ではありません (status: {task['status']})")
    task["status"] = "processing"
    _persist(task_id)
    asyncio.create_task(_run_task(task_id, task["description"]))
    return {"status": "approved", "task_id": task_id}


@app.post("/tasks/{task_id}/reject")
async def reject_plan(task_id: str):
    if task_id not in _task_results:
        raise HTTPException(404, detail="タスクが見つかりません")
    task = _task_results[task_id]
    if task["status"] != "awaiting_approval":
        raise HTTPException(400, detail=f"承認待ち状態ではありません (status: {task['status']})")
    task["status"] = "rejected"
    task["completed_at"] = datetime.now().isoformat()
    _persist(task_id)
    return {"status": "rejected", "task_id": task_id}


@app.get("/tasks/{task_id}/export")
async def export_task(task_id: str):
    """タスク結果を Markdown ファイルとしてダウンロード"""
    if task_id not in _task_results:
        raise HTTPException(404, detail="タスクが見つかりません")
    t = _task_results[task_id]
    result_text = t.get("result") or "（結果なし）"
    suggestions = t.get("suggestions") or []
    submitted = t.get("submitted_at", "")[:19].replace("T", " ")
    completed = (t.get("completed_at") or "")[:19].replace("T", " ")

    lines = [
        f"# {t.get('description', 'タスク結果')}",
        f"",
        f"- **タスクID**: {task_id}",
        f"- **ステータス**: {t.get('status')}",
        f"- **投入日時**: {submitted}",
        f"- **完了日時**: {completed}",
        f"",
        f"## 結果",
        f"",
        result_text,
    ]
    if suggestions:
        lines += ["", "## AIからの提案", ""]
        for s in suggestions:
            lines.append(f"- {s}")

    content = "\n".join(lines)
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="task_{task_id}.md"'},
    )


@app.get("/tasks")
async def list_tasks():
    active_statuses = {"processing", "planning", "awaiting_approval"}
    return {
        "active": [t for t in _task_results.values() if t["status"] in active_statuses],
        "recent": list(reversed(list(_task_results.values())))[:100],
    }


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    if task_id not in _task_results:
        raise HTTPException(404, detail="タスクが見つかりません")
    return _task_results[task_id]


@app.get("/status")
async def company_status():
    return {
        "agents": [
            {"role": a.role, "model": a.model_name, "queue_size": a.inbox.qsize()}
            for a in _agents
        ],
        "active_tasks":      sum(1 for t in _task_results.values() if t["status"] == "processing"),
        "awaiting_approval": sum(1 for t in _task_results.values() if t["status"] == "awaiting_approval"),
        "completed_tasks":   sum(1 for t in _task_results.values() if t["status"] == "completed"),
        "failed_tasks":      sum(1 for t in _task_results.values() if t["status"] == "failed"),
        "pending_approvals": len(_approval_futures),
        "kpi": _mem.kpi_stats(),
    }


@app.get("/pending")
async def list_pending():
    return {
        "pending": [
            {"approval_id": v["approval_id"], "task": v["task"], "requested_at": v["requested_at"]}
            for v in _approval_futures.values()
        ]
    }


@app.post("/approve/{approval_id}")
async def approve_task(approval_id: str):
    if approval_id not in _approval_futures:
        raise HTTPException(404, detail="承認待ちタスクが見つかりません")
    entry = _approval_futures.pop(approval_id)
    if not entry["future"].done():
        entry["future"].set_result(True)
    return {"status": "approved", "approval_id": approval_id}


@app.post("/reject/{approval_id}")
async def reject_task(approval_id: str):
    if approval_id not in _approval_futures:
        raise HTTPException(404, detail="承認待ちタスクが見つかりません")
    entry = _approval_futures.pop(approval_id)
    if not entry["future"].done():
        entry["future"].set_result(False)
    return {"status": "rejected", "approval_id": approval_id}


# ─── スケジュールエンドポイント ───────────────────────────────

@app.get("/schedules")
async def list_schedules():
    return {"schedules": _mem.list_schedules()}


@app.post("/schedules", status_code=201)
async def create_schedule(req: ScheduleRequest):
    if not req.description.strip():
        raise HTTPException(400, detail="タスク説明が空です")
    import re
    if not re.match(r"^\d{2}:\d{2}$", req.time_hhmm):
        raise HTTPException(400, detail="時刻はHH:MM形式で入力してください")
    sid = _mem.save_schedule(req.description.strip(), req.time_hhmm)
    return {"id": sid, "description": req.description, "time_hhmm": req.time_hhmm}


@app.patch("/schedules/{schedule_id}")
async def toggle_schedule(schedule_id: int, enabled: bool):
    _mem.toggle_schedule(schedule_id, enabled)
    return {"status": "updated"}


@app.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: int):
    _mem.delete_schedule(schedule_id)
    return {"status": "deleted"}


# ─── クライアントエンドポイント ───────────────────────────────

@app.get("/clients")
async def list_clients():
    return {"clients": _mem.list_clients()}


@app.post("/clients", status_code=201)
async def create_client(req: ClientRequest):
    if not req.name.strip():
        raise HTTPException(400, detail="クライアント名が空です")
    cid = _mem.save_client(req.name.strip(), req.company, req.industry, req.email, req.notes)
    return {"id": cid, **req.model_dump()}


@app.get("/clients/{client_id}")
async def get_client(client_id: int):
    c = _mem.get_client(client_id)
    if not c:
        raise HTTPException(404, detail="クライアントが見つかりません")
    return c


@app.patch("/clients/{client_id}")
async def update_client(client_id: int, req: ClientRequest):
    if not _mem.get_client(client_id):
        raise HTTPException(404, detail="クライアントが見つかりません")
    _mem.update_client(client_id, **req.model_dump(exclude_unset=True))
    return {"status": "updated"}


# ─── プロジェクトエンドポイント ───────────────────────────────

@app.get("/projects")
async def list_projects(status: str | None = None):
    return {"projects": _mem.list_projects(status)}


@app.post("/projects", status_code=201)
async def create_project(req: ProjectRequest):
    if not req.name.strip():
        raise HTTPException(400, detail="プロジェクト名が空です")
    pid = _mem.save_project(req.client_id, req.name.strip(), req.budget_jpy, req.due_date, req.description)
    return {"id": pid, **req.model_dump()}


@app.patch("/projects/{project_id}/status")
async def update_project_status(project_id: int, status: str):
    allowed = {"active", "completed", "paused"}
    if status not in allowed:
        raise HTTPException(400, detail=f"statusは {allowed} のいずれかです")
    _mem.update_project_status(project_id, status)
    return {"status": "updated"}


# ─── 収益エンドポイント ───────────────────────────────────────

@app.get("/revenue")
async def list_revenue(project_id: int | None = None):
    return {"entries": _mem.list_revenue(project_id)}


@app.post("/revenue", status_code=201)
async def create_revenue(req: RevenueRequest):
    if req.type not in ("income", "expense"):
        raise HTTPException(400, detail="typeは 'income' または 'expense' です")
    if req.amount_jpy <= 0:
        raise HTTPException(400, detail="金額は1以上を入力してください")
    rid = _mem.save_revenue_entry(req.type, req.amount_jpy, req.description, req.date, req.project_id)
    return {"id": rid, **req.model_dump()}


@app.get("/revenue/summary")
async def revenue_summary():
    return _mem.revenue_summary()


# ─── Fiverr注文処理エンドポイント ────────────────────────────

@app.get("/fiverr/templates")
async def fiverr_templates():
    return {k: {"label": v["label"]} for k, v in FIVERR_TEMPLATES.items()}


@app.post("/fiverr/order", status_code=202)
async def fiverr_order(req: FiverrOrderRequest):
    if req.gig_type not in FIVERR_TEMPLATES:
        raise HTTPException(400, detail=f"gig_typeは {list(FIVERR_TEMPLATES.keys())} のいずれかです")
    if not req.topic.strip():
        raise HTTPException(400, detail="topicが空です")
    tmpl = FIVERR_TEMPLATES[req.gig_type]
    prompt = tmpl["prompt"].format(
        topic=req.topic.strip(),
        requirements=req.requirements.strip() or "None specified",
    )
    label = tmpl["label"]
    task_id = uuid.uuid4().hex[:8]
    description = f"[Fiverr] {label}: {req.topic.strip()}"
    _task_results[task_id] = {
        "task_id": task_id,
        "description": description,
        "plan": None,
        "result": None,
        "suggestions": [],
        "submitted_at": datetime.now().isoformat(),
        "completed_at": None,
        "status": "processing",
    }
    _persist(task_id)
    asyncio.create_task(_run_task_refined(task_id, prompt))
    return {"task_id": task_id, "status": "processing", "description": description}


# ─── Gumroad Webhook ─────────────────────────────────────────

@app.post("/webhook/gumroad")
async def gumroad_webhook(request: Request):
    """Gumroad売上通知を受け取ってDBに自動記録"""
    try:
        form = await request.form()
        data = dict(form)
    except Exception:
        data = await request.json()

    sale_id = data.get("sale_id", "")
    product_name = data.get("product_name", "Gumroad商品")
    price = data.get("price", "0")
    email = data.get("email", "")

    # 金額をJPY換算（Gumroadはセント単位でくる場合がある）
    try:
        amount_usd = float(price) / 100 if float(price) > 100 else float(price)
        amount_jpy = int(amount_usd * 150)  # 概算レート
    except Exception:
        amount_jpy = 0

    if _mem and amount_jpy > 0:
        from datetime import date
        _mem.save_revenue_entry(
            type_="income",
            amount_jpy=amount_jpy,
            description=f"[Gumroad] {product_name} ({email})",
            date=date.today().isoformat(),
        )
        print(f"[Webhook] Gumroad売上記録: {product_name} ¥{amount_jpy}")

    return {"status": "ok", "recorded": amount_jpy > 0}


# ─── Fiverr監視エンドポイント ─────────────────────────────────

# ─── SNSプロモ生成 ───────────────────────────────────────────

class PromoRequest(BaseModel):
    product: str        # "seo_pack" | "ai_bundle" | "pitch_deck"
    platform: str       # "twitter" | "reddit" | "linkedin"

PROMO_TEMPLATES = {
    "seo_pack": {
        "name": "SEO Blog Template Pack ($19)",
        "benefit": "5 ready-to-use blog templates + SEO checklist + keyword research guide",
        "url": "https://springharu.gumroad.com/l/hwzuj",
    },
    "ai_bundle": {
        "name": "AI Industry Reports Bundle ($29)",
        "benefit": "5 in-depth AI market research reports covering Healthcare, Fintech, E-Commerce, Education, Logistics",
        "url": "https://springharu.gumroad.com/l/wnnwcn",
    },
    "pitch_deck": {
        "name": "Startup Pitch Deck Script Templates ($29)",
        "benefit": "3 proven pitch scripts (B2B SaaS / Consumer App / AI Startup) + 8 investor Q&A answers",
        "url": "https://springharu.gumroad.com/l/cxuxz",
    },
}

PLATFORM_PROMPTS = {
    "twitter": "Write a compelling Twitter/X thread (3-5 tweets) to promote this digital product. Use hooks, emojis, and relevant hashtags like #SideHustle #PassiveIncome #AI. Keep each tweet under 280 chars.",
    "reddit": "Write a Reddit post for r/entrepreneur or r/SideProject promoting this product. Be authentic, provide value first, mention the product naturally. No hard sell. Include a title and body.",
    "linkedin": "Write a professional LinkedIn post promoting this digital product. Focus on business value and ROI. 150-250 words. Use line breaks for readability.",
}

@app.post("/promo/generate", status_code=202)
async def promo_generate(req: PromoRequest):
    if req.product not in PROMO_TEMPLATES:
        raise HTTPException(400, detail=f"productは {list(PROMO_TEMPLATES.keys())} のいずれか")
    if req.platform not in PLATFORM_PROMPTS:
        raise HTTPException(400, detail=f"platformは {list(PLATFORM_PROMPTS.keys())} のいずれか")

    p = PROMO_TEMPLATES[req.product]
    platform_inst = PLATFORM_PROMPTS[req.platform]
    prompt = f"""{platform_inst}

Product: {p['name']}
Key benefit: {p['benefit']}
Purchase link: {p['url']}

Write the post now. Make it engaging and authentic."""

    task_id = uuid.uuid4().hex[:8]
    description = f"[プロモ] {req.platform.upper()} × {p['name']}"
    _task_results[task_id] = {
        "task_id": task_id, "description": description, "plan": None, "result": None,
        "suggestions": [], "submitted_at": datetime.now().isoformat(),
        "completed_at": None, "status": "processing",
    }
    _persist(task_id)
    asyncio.create_task(_run_task(task_id, prompt))
    return {"task_id": task_id, "status": "processing", "description": description}


# ─── Fiverr返信生成 ──────────────────────────────────────────

class FiverrReplyRequest(BaseModel):
    buyer_message: str
    gig_type: str = "market_research"

@app.post("/fiverr/reply", status_code=202)
async def fiverr_reply(req: FiverrReplyRequest):
    if not req.buyer_message.strip():
        raise HTTPException(400, detail="buyer_messageが空です")
    prompt = f"""You are a professional Fiverr seller. A buyer sent you this message:

"{req.buyer_message.strip()}"

Write a friendly, professional reply that:
1. Thanks them for reaching out
2. Confirms you understand their needs
3. Briefly explains how you'll help
4. Asks 1-2 clarifying questions if needed
5. Mentions your delivery time (2-3 days)

Keep it concise (100-150 words). Sound human, not robotic."""

    task_id = uuid.uuid4().hex[:8]
    description = f"[Fiverr返信] バイヤーメッセージへの返信"
    _task_results[task_id] = {
        "task_id": task_id, "description": description, "plan": None, "result": None,
        "suggestions": [], "submitted_at": datetime.now().isoformat(),
        "completed_at": None, "status": "processing",
    }
    _persist(task_id)
    asyncio.create_task(_run_task_refined(task_id, prompt))
    return {"task_id": task_id, "status": "processing", "description": description}


@app.get("/fiverr/watch/status")
async def fiverr_watch_status():
    if not _fiverr_watcher:
        return {"running": False, "recent_orders": []}
    return _fiverr_watcher.status()


@app.post("/fiverr/watch/start")
async def fiverr_watch_start():
    if _fiverr_watcher:
        _fiverr_watcher.start()
    return {"status": "started"}


@app.post("/fiverr/watch/stop")
async def fiverr_watch_stop():
    if _fiverr_watcher:
        _fiverr_watcher.stop()
    return {"status": "stopped"}


@app.get("/fiverr/orders")
async def fiverr_orders():
    if not _mem:
        return {"orders": []}
    return {"orders": _mem.list_fiverr_orders()}


# ─── note.com 記事生成 ────────────────────────────────────────

NOTE_TEMPLATES = {
    "ai_productivity": {
        "label": "AI・ChatGPT活用術",
        "theme": "AIツール・ChatGPTを使って仕事・副業・日常生活を劇的に効率化する方法",
    },
    "side_hustle": {
        "label": "副業・フリーランス収入",
        "theme": "フリーランスや副業で月5万〜10万円を稼ぐための具体的な戦略とステップ",
    },
    "marketing": {
        "label": "SNS集客・マーケティング",
        "theme": "SNS（Twitter/Instagram/LinkedIn）を使って無料で集客し、収益に繋げる方法",
    },
    "investing": {
        "label": "資産運用・投資入門",
        "theme": "初心者が安全に資産を増やすための投資の基礎知識と具体的な始め方",
    },
    "programming": {
        "label": "プログラミング・IT副業",
        "theme": "プログラミングを学んでITフリーランスとして副収入を得るためのロードマップ",
    },
    "content_monetization": {
        "label": "コンテンツ収益化",
        "theme": "note・ブログ・YouTube・Substackでコンテンツを収益化して月収10万円を目指す方法",
    },
    "digital_products": {
        "label": "デジタル商品販売",
        "theme": "電子書籍・テンプレート・プロンプト集・動画コースをGumroad等で販売して不労所得を作る方法",
    },
    "chatgpt_business": {
        "label": "ChatGPT副業・ビジネス活用",
        "theme": "ChatGPTを使ってビジネスを自動化・効率化し、副業収入を3倍にする実践テクニック",
    },
}

class NoteRequest(BaseModel):
    topic_key: str       # NOTE_TEMPLATES のキー
    custom_topic: str = ""   # 空でなければこちらを優先
    price_yen: int = 500     # 有料設定金額（参考表示用）

@app.post("/note/generate", status_code=202)
async def note_generate(req: NoteRequest):
    if req.custom_topic.strip():
        theme = req.custom_topic.strip()
        label = theme[:20]
    elif req.topic_key in NOTE_TEMPLATES:
        t = NOTE_TEMPLATES[req.topic_key]
        theme = t["theme"]
        label = t["label"]
    else:
        raise HTTPException(400, detail=f"topic_keyは {list(NOTE_TEMPLATES.keys())} のいずれか、またはcustom_topicを入力")

    prompt = f"""あなたはnote.comで月100万円以上を稼ぐトップクリエイターです。
以下のテーマで、読者が思わず購入したくなる有料記事を書いてください。

テーマ: {theme}

【記事の構成（必ずこの順番で）】

## タイトル
「【完全ガイド】〜」「〜で月X万円稼ぐ方法」など、具体的な数字や結果が見えるタイトルを3案提示してください。

---

## ✅ 無料で読める部分（ここまで無料）

### はじめに（250字）
読者の悩みや痛みを具体的に描写し、「この記事を読めば解決できる」と思わせる書き出し。

### この記事で学べること（箇条書き5点）
読者が得られる具体的なメリット・成果を列挙。

### なぜ今これが重要なのか（300字）
背景・トレンド・機会損失を絡めて緊急性を演出。

---

## 🔒 ここから有料（{req.price_yen}円）

### 第1章: 全体像と考え方（400字）
テーマの本質的な考え方・マインドセット。初心者が陥りがちな誤解を正す。

### 第2章: ステップバイステップ実践法（600字）
具体的なやり方を3〜5ステップで。各ステップに「なぜそうするのか」の理由も添える。

### 第3章: 実際の成果・事例（400字）
具体的な数字・実例（架空でもリアリティがあるもの）を使って説得力を高める。

### 第4章: よくある失敗とその回避法（300字）
初心者が失敗しやすいポイント3つとその解決策。

### まとめ・次のアクション（200字）
今日からできる1つのアクションと、読んだ後の感謝・応援メッセージ。

---

【執筆ルール】
- 全文日本語で書く
- 口語調で親しみやすく（「〜ですよ」「〜してみましょう」）
- 具体的な数字・事例を必ず入れる（「約3割」「月5万円」など）
- 抽象的な精神論は避ける
- 合計2,000字以上"""

    task_id = uuid.uuid4().hex[:8]
    description = f"[note] {label}"
    _task_results[task_id] = {
        "task_id": task_id, "description": description, "plan": None, "result": None,
        "suggestions": [], "submitted_at": datetime.now().isoformat(),
        "completed_at": None, "status": "processing",
    }
    _persist(task_id)
    asyncio.create_task(_run_task_refined(task_id, prompt))
    return {"task_id": task_id, "status": "processing", "description": description}


# ─── 自動投稿ステータス・手動トリガー ─────────────────────────

@app.get("/auto/status")
async def auto_status():
    if not _auto_publisher:
        return {"running": False}
    return _auto_publisher.status()

@app.post("/auto/note/now")
async def auto_note_now():
    """手動でnote記事の自動生成→投稿を今すぐ実行"""
    if not _auto_publisher:
        raise HTTPException(500, detail="AutoPublisher未起動")
    asyncio.create_task(_auto_publisher._run_note_post())
    return {"status": "started", "message": "note記事の自動生成→投稿を開始しました"}

@app.post("/auto/reddit/now")
async def auto_reddit_now():
    """手動でReddit投稿を今すぐ実行"""
    if not _auto_publisher:
        raise HTTPException(500, detail="AutoPublisher未起動")
    asyncio.create_task(_auto_publisher._run_reddit_post())
    return {"status": "started", "message": "Reddit投稿を開始しました"}


@app.post("/auto/promo/now")
async def auto_promo_now():
    """手動でGumroadプロモ記事を今すぐ実行"""
    if not _auto_publisher:
        raise HTTPException(500, detail="AutoPublisher未起動")
    asyncio.create_task(_auto_publisher._run_promo_note_post())
    return {"status": "started", "message": "Gumroadプロモ記事生成→投稿を開始しました"}


@app.post("/auto/new-product/now")
async def auto_new_product_now():
    """手動でGumroad新商品自動生成を今すぐ実行"""
    if not _auto_publisher:
        raise HTTPException(500, detail="AutoPublisher未起動")
    asyncio.create_task(_auto_publisher._run_new_product())
    return {"status": "started", "message": "Gumroad新商品自動生成を開始しました"}


@app.post("/auto/x/morning/now")
async def auto_x_morning_now():
    """手動でX朝投稿を今すぐ実行"""
    if not _auto_publisher:
        raise HTTPException(500, detail="AutoPublisher未起動")
    asyncio.create_task(_auto_publisher._run_x_morning_post())
    return {"status": "started", "message": "X朝投稿を開始しました"}


@app.post("/auto/x/evening/now")
async def auto_x_evening_now():
    """手動でX夜投稿を今すぐ実行"""
    if not _auto_publisher:
        raise HTTPException(500, detail="AutoPublisher未起動")
    asyncio.create_task(_auto_publisher._run_x_evening_post())
    return {"status": "started", "message": "X夜投稿を開始しました"}


@app.get("/x/auth/status")
async def x_auth_status():
    from services.x_poster import is_logged_in
    return {"logged_in": is_logged_in()}


@app.get("/note/templates")
async def note_templates():
    return {k: {"label": v["label"]} for k, v in NOTE_TEMPLATES.items()}


# ─── Zenn.dev ─────────────────────────────────────────────────

@app.get("/zenn/status")
async def zenn_status():
    from services.zenn_poster import is_configured, ZENN_REPO_DIR
    return {
        "configured": is_configured(),
        "repo_dir": ZENN_REPO_DIR,
        "setup_url": "https://zenn.dev/dashboard/deploys",
    }

@app.post("/zenn/post")
async def zenn_post_article(req: dict = Body(...)):
    task_id = req.get("task_id", "")
    task = _task_results.get(task_id)
    if not task or task.get("status") != "completed":
        raise HTTPException(400, detail="完了済みタスクのtask_idを指定してください")
    from services.zenn_poster import ZennPoster
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: ZennPoster().post(task["result"]))
    return result


# ─── Qiita ────────────────────────────────────────────────────

@app.get("/qiita/status")
async def qiita_status():
    from services.qiita_poster import is_configured
    return {
        "configured": is_configured(),
        "setup_url": "https://qiita.com/settings/tokens/new",
        "required_scopes": ["read_qiita", "write_qiita"],
    }


# ─── note.com 自動投稿 ────────────────────────────────────────

from services.note_poster import NotePoster as _NotePoster
_note_poster = _NotePoster()

class NotePostRequest(BaseModel):
    task_id: str
    price_yen: int = 500

@app.post("/note/post")
async def note_post(req: NotePostRequest):
    task = _task_results.get(req.task_id)
    if not task:
        raise HTTPException(404, detail="タスクが見つかりません")
    if task.get("status") != "completed":
        raise HTTPException(400, detail=f"タスクがまだ完了していません（現在: {task.get('status')}）")
    raw_text = task.get("result", "")
    if not raw_text:
        raise HTTPException(400, detail="生成結果が空です")
    result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: asyncio.run(_note_poster.post(raw_text, req.price_yen))
    )
    return result

@app.get("/note/auth/status")
async def note_auth_status():
    from pathlib import Path
    data_dir = Path(__file__).parent.parent / "note_playwright_data"
    has_session = (data_dir / "Default" / "Cookies").exists() or \
                  (data_dir / "Default" / "Network" / "Cookies").exists()
    return {"logged_in": has_session, "data_dir": str(data_dir)}


# ─── Reddit 自動投稿 ──────────────────────────────────────────

from services.reddit_poster import RedditPoster as _RedditPoster
_reddit_poster = _RedditPoster()

class RedditPostRequest(BaseModel):
    task_id: str
    topic_key: str = "default"
    subreddit: str = ""

@app.get("/reddit/config/status")
async def reddit_config_status():
    return {"configured": _reddit_poster.is_configured()}

@app.post("/reddit/post")
async def reddit_post(req: RedditPostRequest):
    if not _reddit_poster.is_configured():
        raise HTTPException(400, detail="未ログイン — python services/reddit_auth.py を実行してください")
    task = _task_results.get(req.task_id)
    if not task:
        raise HTTPException(404, detail="タスクが見つかりません")
    if task.get("status") != "completed":
        raise HTTPException(400, detail=f"タスクがまだ完了していません（現在: {task.get('status')}）")
    raw_text = task.get("result", "")
    result = await _reddit_poster.post_async(raw_text, req.topic_key, req.subreddit)
    return result


# ─── Gumroad 商品作成 ─────────────────────────────────────────

GUMROAD_PRODUCT_TYPES = {
    "prompt_pack": {
        "name": "ChatGPT副業プロンプト厳選20選",
        "price_usd": 19,
        "prompt": """副業で稼ぐための最強ChatGPTプロンプト集を作成してください。

## 商品説明（200字）
Gumroadに掲載する商品説明文を書いてください。

## プロンプト集（各カテゴリ5個ずつ、計20個）

### フリーランス受注用プロンプト（5個）
Fiverr・Upworkの仕事を即納品できるプロンプト。

### SNS集客プロンプト（5個）
note・Twitter/X用の投稿文を生成するプロンプト。

### 市場調査プロンプト（5個）
業界分析・競合調査を自動化するプロンプト。

### ビジネス文書プロンプト（5個）
提案書・メール・報告書を作成するプロンプト。

【各プロンプトの形式】
番号. タイトル
用途: 一行で説明
プロンプト本文（コードブロック内に記述）
使い方のコツ: 一行
""",
    },
    "template": {
        "name": "AI Market Research テンプレート集",
        "price_usd": 29,
        "prompt": """Fiverrで即使えるマーケットリサーチテンプレート集を作成してください。

## 商品説明（200字）
Gumroadに掲載する商品説明文を書いてください。

## テンプレート集（3種類）

### テンプレート1: 基本市場調査レポート
{{CLIENT_NAME}}、{{INDUSTRY}}などの変数を使った完全なMarkdownテンプレート（見出し・表・箇条書き含む）。

### テンプレート2: 競合分析レポート
同様にMarkdown形式で完全版を記述。

### テンプレート3: Fiverr即納用クイックリサーチ（2ページ）
受注から1時間で納品できるシンプルなテンプレート。

各テンプレートには変数の使い方と納品時のメモを含めてください。
""",
    },
    "guide": {
        "name": "note収益化ガイド 月5万円への最短ルート",
        "price_usd": 15,
        "prompt": """note.comで月収5万円を達成するための実践ガイドを書いてください。

## 商品説明（200字）
Gumroadに掲載する商品説明文を書いてください。

## ガイド本文（2000字程度）

### 第1章: 全体像とロードマップ（300字）
### 第2章: 売れる記事テーマの選び方（400字）
### 第3章: 有料部分の設計法（400字）
### 第4章: AIを使った執筆ワークフロー（400字）
### 第5章: SNS集客とまとめ（300字）

具体的な数字と再現可能な手順を必ず含めてください。
""",
    },
}


@app.get("/gumroad/config/status")
async def gumroad_config_status():
    from services.gumroad_api import GumroadClient
    client = GumroadClient()
    return {"configured": client.is_configured()}


@app.get("/gumroad/products")
async def gumroad_list_products():
    from services.gumroad_api import GumroadClient
    client = GumroadClient()
    if not client.is_configured():
        return {"products": [], "error": "GUMROAD_TOKEN未設定"}
    try:
        products = client.list_products()
        return {"products": products}
    except Exception as e:
        return {"products": [], "error": str(e)}


@app.get("/gumroad/db/products")
async def gumroad_db_products():
    """DBに保存済みのGumroad商品一覧を返す"""
    if not _mem:
        return {"products": []}
    return {"products": _mem.get_gumroad_products()}


@app.post("/gumroad/db/register")
async def gumroad_db_register(req: Request):
    """既存Gumroad商品をDBに手動登録"""
    if not _mem:
        raise HTTPException(500, detail="memory未初期化")
    body = await req.json()
    short_url = body.get("short_url", "").strip()
    name = body.get("name", "").strip()
    price_usd = int(body.get("price_usd", 0))
    product_type = body.get("product_type", "")
    if not short_url or not name:
        raise HTTPException(400, detail="short_url と name は必須")
    _mem.save_gumroad_product(short_url, name, price_usd, product_type)
    return {"status": "registered", "short_url": short_url, "name": name}


@app.post("/gumroad/product/create", status_code=202)
async def gumroad_create_product(req: Request):
    body = await req.json()
    product_type = body.get("product_type", "prompt_pack")
    if product_type not in GUMROAD_PRODUCT_TYPES:
        raise HTTPException(400, detail=f"不明な商品タイプ: {product_type}")

    from services.gumroad_api import GumroadClient
    client = GumroadClient()
    if not client.is_configured():
        raise HTTPException(400, detail="GUMROAD_TOKEN が未設定です。.env ファイルに追加してください。")

    ptype = GUMROAD_PRODUCT_TYPES[product_type]
    task_id = uuid.uuid4().hex[:8]
    _task_results[task_id] = {
        "task_id": task_id,
        "description": f"[Gumroad] {ptype['name']}",
        "plan": None, "result": None, "suggestions": [],
        "submitted_at": datetime.now().isoformat(),
        "completed_at": None, "status": "processing",
        "gumroad_product_type": product_type,
    }
    _persist(task_id)

    asyncio.create_task(_run_gumroad_product(task_id, product_type))
    return {"task_id": task_id, "status": "processing"}


async def _run_gumroad_product(task_id: str, product_type: str):
    """コンテンツ生成（1段階） → PDF化 → Gumroad登録"""
    from services.gumroad_api import GumroadClient
    from services.pdf_generator import save_product_pdf

    ptype = GUMROAD_PRODUCT_TYPES[product_type]
    name = ptype["name"]
    price_usd = ptype["price_usd"]

    try:
        # Step 1: コンテンツ生成（LLM直接呼び出し・タイムアウト5分）
        _task_results[task_id]["result"] = "[1/4] 商品コンテンツ生成中..."
        _task_results[task_id]["status"] = "processing"
        _persist(task_id)
        try:
            from core.llm import call_llm
            async with asyncio.timeout(300):  # 5分
                raw_text = await call_llm(
                    ptype["prompt"],
                    system="あなたは日本語で高品質なデジタル商品コンテンツを作成する専門家です。指示に従い、具体的で実用的な内容を生成してください。",
                    tier="worker",
                )
        except asyncio.TimeoutError:
            _task_results[task_id].update({
                "status": "failed",
                "result": "タイムアウト（5分超過）。再度投入してください。",
                "completed_at": datetime.now().isoformat(),
            })
            _persist(task_id)
            return

        if not raw_text:
            _task_results[task_id].update({
                "status": "failed",
                "result": "コンテンツ生成に失敗しました",
                "completed_at": datetime.now().isoformat(),
            })
            _persist(task_id)
            return

        # Step 2: PDF生成
        _task_results[task_id]["result"] = "[2/3] PDF生成中..."
        _persist(task_id)
        loop = asyncio.get_event_loop()
        pdf_path = await loop.run_in_executor(
            None, save_product_pdf, product_type, name, raw_text
        )

        # Step 3: Gumroad商品登録
        _task_results[task_id]["result"] = "[3/4] Gumroadに商品登録中..."
        _persist(task_id)

        client = GumroadClient()
        description = f"{name}\n\n価格: ${price_usd}\n\nAIで自動生成した高品質デジタル商品です。"
        product = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.create_product(name, description, price_usd * 100)
        )

        product_url = product.get("short_url", "")
        product_id = product.get("id", "")
        # short_url 例: https://springharu.gumroad.com/l/tkdrf → "tkdrf"
        short_key = product_url.rstrip("/").split("/")[-1] if product_url else ""

        # Step 4: PDF自動アップロード（Playwrightセッションがあれば）
        upload_ok = False
        from pathlib import Path as _Path
        gumroad_session = _Path(__file__).parent.parent / "gumroad_playwright_data"
        if short_key and gumroad_session.exists():
            _task_results[task_id]["result"] = "[4/4] PDFをGumroadにアップロード中..."
            _persist(task_id)
            try:
                from services.gumroad_uploader import upload_pdf_to_product
                upload_ok = await upload_pdf_to_product(short_key, str(pdf_path))
            except Exception as ue:
                print(f"[Gumroad] PDFアップロード失敗: {ue}")

        suggestions = [
            f"Gumroad商品URL: {product_url}",
            f"PDF保存先: {pdf_path}",
        ]
        if upload_ok:
            suggestions.append("✅ PDFアップロード・公開完了！商品は今すぐ購入可能です。")
        else:
            suggestions.append(
                f"⚠️ PDFは手動でアップロードしてください: https://gumroad.com/products/{short_key}/edit/content"
                if short_key else
                "⚠️ GumroadダッシュボードでPDFをアップロードしてください"
            )
            if not gumroad_session.exists():
                suggestions.append("💡 自動アップロードを有効にする: python services/gumroad_auth.py")

        _task_results[task_id].update({
            "status": "completed",
            "result": raw_text,
            "completed_at": datetime.now().isoformat(),
            "gumroad_url": product_url,
            "gumroad_product_id": product_id,
            "pdf_path": str(pdf_path),
            "suggestions": suggestions,
        })
        _persist(task_id)
        if short_key and _mem:
            _mem.save_gumroad_product(short_key, name, price_usd, product_type)

    except Exception as e:
        _task_results[task_id].update({
            "status": "failed",
            "result": f"エラー: {e}",
            "completed_at": datetime.now().isoformat(),
        })
        _persist(task_id)
