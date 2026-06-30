import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class OrgMemory:
    """組織全体で共有する長期記憶（SQLiteバックエンド）"""

    def __init__(self, db_path: str = "memory/company.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._setup()

    def _setup(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                assigned_to TEXT NOT NULL,
                instruction TEXT NOT NULL,
                result TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_records (
                task_id TEXT PRIMARY KEY,
                description TEXT,
                status TEXT,
                plan_json TEXT,
                result TEXT,
                suggestions_json TEXT,
                submitted_at TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                time_hhmm TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                last_run_date TEXT
            );
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                company TEXT DEFAULT '',
                industry TEXT DEFAULT '',
                email TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER REFERENCES clients(id),
                name TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                budget_jpy INTEGER DEFAULT 0,
                due_date TEXT DEFAULT '',
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS revenue_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                type TEXT NOT NULL,
                amount_jpy INTEGER NOT NULL,
                description TEXT DEFAULT '',
                date TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fiverr_orders (
                order_id TEXT PRIMARY KEY,
                buyer TEXT DEFAULT '',
                gig_type TEXT DEFAULT '',
                requirements TEXT DEFAULT '',
                status TEXT DEFAULT 'detected',
                task_id TEXT DEFAULT '',
                detected_at TEXT,
                delivered_at TEXT
            );
            CREATE TABLE IF NOT EXISTS gumroad_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                short_url TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                price_usd INTEGER DEFAULT 0,
                product_type TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        # 既存DBへのカラム追加（ALTER TABLEはIF NOT EXISTSが使えないため試行）
        for col_sql in [
            "ALTER TABLE task_records ADD COLUMN project_id TEXT",
        ]:
            try:
                self.conn.execute(col_sql)
            except Exception:
                pass
        self.conn.commit()

    def save(self, agent: str, key: str, value: Any):
        self.conn.execute(
            "INSERT INTO memories (agent, key, value, created_at) VALUES (?, ?, ?, ?)",
            (agent, key, json.dumps(value, ensure_ascii=False), datetime.now().isoformat()),
        )
        self.conn.commit()

    def load(self, agent: str, key: str) -> Any | None:
        cur = self.conn.execute(
            "SELECT value FROM memories WHERE agent=? AND key=? ORDER BY created_at DESC LIMIT 1",
            (agent, key),
        )
        row = cur.fetchone()
        return json.loads(row[0]) if row else None

    def log_task(self, task_id: str, assigned_to: str, instruction: str):
        self.conn.execute(
            "INSERT INTO task_log (task_id, assigned_to, instruction, created_at) VALUES (?, ?, ?, ?)",
            (task_id, assigned_to, instruction, datetime.now().isoformat()),
        )
        self.conn.commit()

    def complete_task(self, task_id: str, result: str):
        self.conn.execute(
            "UPDATE task_log SET result=?, status='completed', completed_at=? WHERE task_id=?",
            (result, datetime.now().isoformat(), task_id),
        )
        self.conn.commit()

    def recent_tasks(self, limit: int = 20) -> list[dict]:
        cur = self.conn.execute(
            "SELECT task_id, assigned_to, instruction, status, created_at, completed_at FROM task_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        cols = ["task_id", "assigned_to", "instruction", "status", "created_at", "completed_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def load_similar_cases(self, query: str, limit: int = 3) -> list[dict]:
        """過去の完了済み類似タスクを取得（簡易キーワード検索）"""
        keyword = query[:30].replace("%", "")
        cur = self.conn.execute(
            """SELECT instruction, result, assigned_to, completed_at
               FROM task_log
               WHERE status='completed' AND result IS NOT NULL AND instruction LIKE ?
               ORDER BY completed_at DESC LIMIT ?""",
            (f"%{keyword}%", limit),
        )
        cols = ["instruction", "result", "assigned_to", "completed_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def save_knowledge(self, category: str, content: str):
        """組織知識ベースに知識を保存"""
        self.conn.execute(
            "INSERT INTO knowledge_base (category, content, created_at) VALUES (?, ?, ?)",
            (category, content, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_knowledge(self, category: str, limit: int = 5) -> list[str]:
        """カテゴリの知識を取得"""
        cur = self.conn.execute(
            "SELECT content FROM knowledge_base WHERE category=? ORDER BY created_at DESC LIMIT ?",
            (category, limit),
        )
        return [row[0] for row in cur.fetchall()]

    def save_task_record(self, task_id: str, data: dict):
        """タスク全体の状態を永続化（upsert）"""
        self.conn.execute(
            """INSERT INTO task_records
               (task_id, description, status, plan_json, result, suggestions_json, submitted_at, completed_at, project_id)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(task_id) DO UPDATE SET
               status=excluded.status, plan_json=excluded.plan_json,
               result=excluded.result, suggestions_json=excluded.suggestions_json,
               completed_at=excluded.completed_at, project_id=excluded.project_id""",
            (
                task_id,
                data.get("description"),
                data.get("status"),
                json.dumps(data.get("plan"), ensure_ascii=False) if data.get("plan") else None,
                data.get("result"),
                json.dumps(data.get("suggestions", []), ensure_ascii=False),
                data.get("submitted_at"),
                data.get("completed_at"),
                data.get("project_id"),
            ),
        )
        self.conn.commit()

    def load_task_records(self) -> list[dict]:
        """保存済みタスクを全件読み込む"""
        cur = self.conn.execute(
            "SELECT task_id, description, status, plan_json, result, suggestions_json, submitted_at, completed_at, project_id"
            " FROM task_records ORDER BY submitted_at DESC LIMIT 200"
        )
        rows = []
        for row in cur.fetchall():
            rows.append({
                "task_id": row[0],
                "description": row[1],
                "status": row[2],
                "plan": json.loads(row[3]) if row[3] else None,
                "result": row[4],
                "suggestions": json.loads(row[5]) if row[5] else [],
                "submitted_at": row[6],
                "completed_at": row[7],
                "project_id": row[8],
            })
        return rows

    # ── クライアント管理 ──────────────────────────────────────────

    def save_client(self, name: str, company: str = "", industry: str = "",
                    email: str = "", notes: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO clients (name, company, industry, email, notes, created_at) VALUES (?,?,?,?,?,?)",
            (name, company, industry, email, notes, datetime.now().isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_clients(self) -> list[dict]:
        cur = self.conn.execute(
            """SELECT c.id, c.name, c.company, c.industry, c.email, c.notes, c.created_at,
                      COUNT(p.id) as project_count
               FROM clients c
               LEFT JOIN projects p ON p.client_id = c.id
               GROUP BY c.id ORDER BY c.created_at DESC"""
        )
        cols = ["id", "name", "company", "industry", "email", "notes", "created_at", "project_count"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_client(self, client_id: int) -> dict | None:
        cur = self.conn.execute(
            "SELECT id, name, company, industry, email, notes, created_at FROM clients WHERE id=?",
            (client_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip(["id", "name", "company", "industry", "email", "notes", "created_at"], row))

    def update_client(self, client_id: int, **kwargs):
        allowed = {"name", "company", "industry", "email", "notes"}
        sets = ", ".join(f"{k}=?" for k in kwargs if k in allowed)
        vals = [v for k, v in kwargs.items() if k in allowed]
        if not sets:
            return
        self.conn.execute(f"UPDATE clients SET {sets} WHERE id=?", (*vals, client_id))
        self.conn.commit()

    # ── プロジェクト管理 ──────────────────────────────────────────

    def save_project(self, client_id: int, name: str, budget_jpy: int = 0,
                     due_date: str = "", description: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO projects (client_id, name, status, budget_jpy, due_date, description, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (client_id, name, "active", budget_jpy, due_date, description, datetime.now().isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_projects(self, status: str | None = None) -> list[dict]:
        query = """SELECT p.id, p.client_id, p.name, p.status, p.budget_jpy, p.due_date,
                          p.description, p.created_at, c.company, c.name as client_name
                   FROM projects p
                   LEFT JOIN clients c ON c.id = p.client_id"""
        if status:
            cur = self.conn.execute(query + " WHERE p.status=? ORDER BY p.created_at DESC", (status,))
        else:
            cur = self.conn.execute(query + " ORDER BY p.created_at DESC")
        cols = ["id", "client_id", "name", "status", "budget_jpy", "due_date",
                "description", "created_at", "client_company", "client_name"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def update_project_status(self, project_id: int, status: str):
        self.conn.execute("UPDATE projects SET status=? WHERE id=?", (status, project_id))
        self.conn.commit()

    # ── 収益管理 ──────────────────────────────────────────────────

    def save_revenue_entry(self, type_: str, amount_jpy: int, description: str,
                           date: str, project_id: int | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO revenue_entries (project_id, type, amount_jpy, description, date) VALUES (?,?,?,?,?)",
            (project_id, type_, amount_jpy, description, date),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_revenue(self, project_id: int | None = None, limit: int = 50) -> list[dict]:
        if project_id is not None:
            cur = self.conn.execute(
                "SELECT id, project_id, type, amount_jpy, description, date FROM revenue_entries"
                " WHERE project_id=? ORDER BY date DESC LIMIT ?",
                (project_id, limit),
            )
        else:
            cur = self.conn.execute(
                "SELECT id, project_id, type, amount_jpy, description, date FROM revenue_entries"
                " ORDER BY date DESC LIMIT ?",
                (limit,),
            )
        cols = ["id", "project_id", "type", "amount_jpy", "description", "date"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def revenue_summary(self) -> dict:
        income_row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_jpy),0) FROM revenue_entries WHERE type='income'"
        ).fetchone()
        expense_row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_jpy),0) FROM revenue_entries WHERE type='expense'"
        ).fetchone()
        active_projects = self.conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status='active'"
        ).fetchone()[0]
        total_clients = self.conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        income = income_row[0] or 0
        expense = expense_row[0] or 0
        return {
            "total_income": income,
            "total_expense": expense,
            "profit": income - expense,
            "active_projects": active_projects,
            "total_clients": total_clients,
        }

    # ── スケジュール ──────────────────────────────────────────

    def save_schedule(self, description: str, time_hhmm: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO schedules (description, time_hhmm, enabled) VALUES (?, ?, 1)",
            (description, time_hhmm),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_schedules(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT id, description, time_hhmm, enabled, last_run_date FROM schedules ORDER BY id"
        )
        cols = ["id", "description", "time_hhmm", "enabled", "last_run_date"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def toggle_schedule(self, schedule_id: int, enabled: bool):
        self.conn.execute(
            "UPDATE schedules SET enabled=? WHERE id=?", (1 if enabled else 0, schedule_id)
        )
        self.conn.commit()

    def delete_schedule(self, schedule_id: int):
        self.conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
        self.conn.commit()

    def mark_schedule_run(self, schedule_id: int, date_str: str):
        self.conn.execute(
            "UPDATE schedules SET last_run_date=? WHERE id=?", (date_str, schedule_id)
        )
        self.conn.commit()

    # ── Fiverr注文管理 ───────────────────────────────────────────

    def save_fiverr_order(self, order_id: str, gig_type: str, requirements: str, status: str = "detected"):
        self.conn.execute(
            """INSERT INTO fiverr_orders (order_id, gig_type, requirements, status, detected_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(order_id) DO NOTHING""",
            (order_id, gig_type, requirements[:2000], status, datetime.now().isoformat()),
        )
        self.conn.commit()

    def fiverr_order_exists(self, order_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM fiverr_orders WHERE order_id=?", (order_id,)
        ).fetchone()
        return row is not None

    def update_fiverr_order(self, order_id: str, status: str, task_id: str = ""):
        delivered_at = datetime.now().isoformat() if status == "delivered" else None
        self.conn.execute(
            "UPDATE fiverr_orders SET status=?, task_id=?, delivered_at=? WHERE order_id=?",
            (status, task_id, delivered_at, order_id),
        )
        self.conn.commit()

    def list_fiverr_orders(self, limit: int = 20) -> list[dict]:
        cur = self.conn.execute(
            "SELECT order_id, buyer, gig_type, requirements, status, task_id, detected_at, delivered_at"
            " FROM fiverr_orders ORDER BY detected_at DESC LIMIT ?",
            (limit,),
        )
        cols = ["order_id", "buyer", "gig_type", "requirements", "status", "task_id", "detected_at", "delivered_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def kpi_stats(self) -> dict:
        """KPI統計を返す（task_records テーブルから取得）"""
        total = self.conn.execute("SELECT COUNT(*) FROM task_records").fetchone()[0]
        completed = self.conn.execute("SELECT COUNT(*) FROM task_records WHERE status='completed'").fetchone()[0]

        # 平均処理時間（秒）
        avg_time_row = self.conn.execute(
            """SELECT AVG((julianday(completed_at) - julianday(submitted_at)) * 86400)
               FROM task_records WHERE status='completed' AND completed_at IS NOT NULL"""
        ).fetchone()
        avg_time = round(avg_time_row[0] or 0, 1)

        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "avg_processing_sec": avg_time,
            "by_agent": {},
        }

    # ── Gumroad商品管理 ──────────────────────────────────────────────

    def save_gumroad_product(self, short_url: str, name: str, price_usd: int = 0, product_type: str = ""):
        self.conn.execute(
            """INSERT INTO gumroad_products (short_url, name, price_usd, product_type, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(short_url) DO UPDATE SET name=excluded.name, price_usd=excluded.price_usd""",
            (short_url, name, price_usd, product_type, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_gumroad_products(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT short_url, name, price_usd, product_type, created_at FROM gumroad_products ORDER BY created_at DESC"
        )
        cols = ["short_url", "name", "price_usd", "product_type", "created_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # ── アプリ設定 ──────────────────────────────────────────────────

    def get_config(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM app_config WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_config(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()
