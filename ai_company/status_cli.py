"""
AI Company ターミナル ステータスダッシュボード
実行: python status_cli.py
3秒ごとに自動更新。Ctrl+C で終了。
"""
import sys
import subprocess
import urllib.request
import json
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.console import Console
from rich import box

BASE = "http://localhost:8002"
console = Console(force_terminal=True, emoji=True)


def _get(path: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _schtasks_ok() -> bool:
    try:
        r = subprocess.run(
            ["schtasks", "/Query", "/TN", "AI_Company_Server"],
            capture_output=True, timeout=3,
        )
        return r.returncode == 0
    except Exception:
        return False


def _bar(pct: int, width: int = 20) -> str:
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)


def _service_score(name: str, status: dict, logs: list[dict]) -> tuple[int, str]:
    """(完成度%, 状態絵文字)"""
    log_msgs = [l["msg"] for l in logs]

    if name == "LLM":
        # サーバーが応答していれば OK
        return (100, "✅") if status else (0, "❌")

    if name == "Zenn":
        d = _get("/zenn/status") or {}
        return (100, "✅") if d.get("configured") else (0, "❌")

    if name == "Qiita":
        d = _get("/qiita/status") or {}
        if not d.get("configured"):
            return (0, "❌")
        if any("403" in m and "Qiita" in m for m in log_msgs):
            return (50, "⚠️")
        return (100, "✅")  # token設定済み＆403なし → OK

    if name == "note":
        if any("✅ note投稿完了" in m for m in log_msgs):
            return (100, "✅")
        if any("❌ note投稿失敗" in m for m in log_msgs):
            return (50, "🔄")
        return (30, "🔧")

    if name == "Gumroad":
        d = _get("/gumroad/db/products") or []
        return (100, "✅") if d else (50, "⚠️")

    if name == "Task Scheduler":
        return (100, "✅") if _schtasks_ok() else (0, "❌")

    if name == "OpenClaw":
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:18789/health", timeout=2)
            return (100, "✅")
        except Exception:
            return (0, "❌")

    return (0, "❓")


def build_dashboard() -> Panel:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    auto = _get("/auto/status")

    server_ok = auto is not None
    running = auto.get("running", False) if auto else False
    logs = auto.get("recent_log", []) if auto else []
    next_topic = auto.get("next_note_topic", "-") if auto else "-"
    next_reddit = auto.get("next_reddit_sub", "-") if auto else "-"

    # ── ヘッダー ──────────────────────────────────────
    header_color = "green" if running else ("yellow" if server_ok else "red")
    server_label = "✅ 起動中" if running else ("⚠️ 停止中" if server_ok else "❌ オフライン")

    # ── サービス完成度テーブル ─────────────────────────
    svc_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    svc_table.add_column("サービス", style="bold", width=18)
    svc_table.add_column("バー", width=22)
    svc_table.add_column("完成度", width=6, justify="right")
    svc_table.add_column("状態", width=4)

    services = ["LLM", "Zenn", "Qiita", "note", "Gumroad", "Task Scheduler", "OpenClaw"]
    scores = []
    for svc in services:
        pct, icon = _service_score(svc, auto, logs)
        scores.append(pct)
        bar_color = "green" if pct == 100 else ("yellow" if pct >= 50 else "red")
        svc_table.add_row(
            svc,
            f"[{bar_color}]{_bar(pct)}[/{bar_color}]",
            f"{pct}%",
            icon,
        )

    total = int(sum(scores) / len(scores)) if scores else 0
    total_color = "green" if total >= 80 else ("yellow" if total >= 50 else "red")
    svc_table.add_row("─" * 18, "─" * 22, "─" * 6, "─" * 4)
    svc_table.add_row(
        "[bold]総合完成度[/bold]",
        f"[{total_color}]{_bar(total)}[/{total_color}]",
        f"[bold]{total}%[/bold]",
        "",
    )

    # ── ログテーブル ───────────────────────────────────
    log_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    log_table.add_column("時刻", style="dim", width=6)
    log_table.add_column("メッセージ", max_width=55)

    for entry in logs[-6:]:
        t = entry["time"][11:16]
        msg = entry["msg"].split("\n")[0][:60]
        if "✅" in msg:
            style = "green"
        elif "❌" in msg:
            style = "red"
        elif "⚠️" in msg:
            style = "yellow"
        else:
            style = "white"
        log_table.add_row(t, f"[{style}]{msg}[/{style}]")

    if not logs:
        log_table.add_row("-", "[dim]ログなし[/dim]")

    # ── 組み立て ──────────────────────────────────────
    content = (
        f"[{header_color} bold]AutoPublisher: {server_label}[/{header_color} bold]\n"
        f"[dim]次の投稿: note({next_topic}) | Reddit({next_reddit})[/dim]\n\n"
        "[bold]サービス完成度[/bold]\n"
    )

    from rich.console import Group
    group = Group(
        Text.from_markup(content),
        svc_table,
        Text.from_markup("\n[bold]最近のログ[/bold]"),
        log_table,
        Text.from_markup(f"\n[dim]3秒ごと自動更新 | {now} | Ctrl+C で終了[/dim]"),
    )

    return Panel(group, title="[bold cyan]🤖 AI Company ステータス[/bold cyan]", border_style="cyan")


def main():
    import os
    import time
    while True:
        os.system("cls")
        console.print(build_dashboard())
        time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]終了しました[/dim]")
