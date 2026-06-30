"""
定期実行スケジューラー
毎分チェックし、登録時刻に一致するタスクを自動投入する
"""
import asyncio
from datetime import datetime


class SchedulerService:
    def __init__(self, memory, submit_callback):
        """
        memory: OrgMemory インスタンス
        submit_callback: async (description: str) -> str  (task_idを返す)
        """
        self._mem = memory
        self._submit = submit_callback
        self._task: asyncio.Task | None = None

    def start(self):
        self._task = asyncio.create_task(self._loop())
        print("[Scheduler] 起動 - 1分ごとにスケジュールを確認します")

    def stop(self):
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while True:
            await asyncio.sleep(30)  # 30秒ごとにチェック
            try:
                await self._check()
            except Exception as e:
                print(f"[Scheduler] エラー: {e}")

    async def _check(self):
        now = datetime.now()
        current_time  = now.strftime("%H:%M")
        current_date  = now.strftime("%Y-%m-%d")

        for sch in self._mem.list_schedules():
            if not sch["enabled"]:
                continue
            if sch["time_hhmm"] != current_time:
                continue
            if sch["last_run_date"] == current_date:
                continue  # 今日はすでに実行済み

            print(f"[Scheduler] 定期タスク実行: {sch['description'][:60]}")
            await self._submit(sch["description"])
            self._mem.mark_schedule_run(sch["id"], current_date)
