"""AI企業 動作確認スクリプト"""
import sys
import time
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8001"
PASS = "[OK]"
FAIL = "[NG]"


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as r:
        return json.loads(r.read())


def post(path: str, data: dict) -> dict:
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def check(label: str, ok: bool, detail: str = ""):
    mark = PASS if ok else FAIL
    suffix = f" ({detail})" if detail else ""
    print(f"  {mark} {label}{suffix}")
    return ok


def run():
    print("\n=== AI企業 動作確認 ===\n")
    results = []

    # [1] サーバー応答
    try:
        data = get("/status")
        results.append(check("[1] サーバー応答", True, "200 OK"))
    except Exception as e:
        results.append(check("[1] サーバー応答", False, str(e)[:60]))
        print("\nサーバーが起動していません。先に起動してください。")
        print("コマンド: python main.py --server 8001")
        sys.exit(1)

    # [2] エージェント起動確認
    agents = data.get("agents", [])
    n = len(agents)
    results.append(check("[2] エージェント起動", n > 0, f"{n}体稼働中: {[a['role'] for a in agents]}"))

    # [3] タスク投入・処理
    print("\n  タスクを投入中（最大90秒待機）...")
    try:
        resp = post("/tasks", {"description": "「AIエージェント」を一文で説明してください"})
        task_id = resp["task_id"]
        print(f"  投入完了 (ID: {task_id})")

        result_text = None
        for i in range(90):
            time.sleep(1)
            try:
                t = get(f"/tasks/{task_id}")
                if t["status"] == "completed":
                    result_text = t.get("result", "")
                    break
                elif t["status"] == "failed":
                    result_text = "FAILED"
                    break
            except Exception:
                pass
            if i % 10 == 9:
                print(f"  待機中... ({i+1}s)")

        ok = result_text is not None and len(result_text) > 0
        if ok:
            preview = result_text[:60].replace("\n", " ")
            results.append(check("[3] タスク処理", True, f'"{preview}..."'))
        elif result_text == "FAILED":
            results.append(check("[3] タスク処理", False, "タスクが失敗しました"))
        else:
            results.append(check("[3] タスク処理", False, "90秒タイムアウト"))
    except Exception as e:
        results.append(check("[3] タスク処理", False, str(e)[:60]))

    # [4] メモリ(DB)記録確認
    try:
        tasks_data = get("/tasks")
        history = tasks_data.get("history", [])
        results.append(check("[4] メモリ(DB)記録", len(history) > 0, f"{len(history)}件記録済み"))
    except Exception as e:
        results.append(check("[4] メモリ(DB)記録", False, str(e)[:60]))

    # [5] KPI集計確認
    try:
        status = get("/status")
        kpi = status.get("kpi", {})
        completed = kpi.get("completed_tasks", 0)
        avg = kpi.get("avg_processing_sec", 0)
        ok = completed > 0
        results.append(check("[5] KPI集計", ok, f"完了{completed}件 / 平均{avg}秒"))
    except Exception as e:
        results.append(check("[5] KPI集計", False, str(e)[:60]))

    # 結果サマリー
    passed = sum(results)
    total = len(results)
    print(f"\n{'='*40}")
    if passed == total:
        print(f"全チェック合格 ({passed}/{total}) ✓")
    else:
        print(f"一部失敗 ({passed}/{total}) — 上記のNGを確認してください")
    print("=" * 40 + "\n")


if __name__ == "__main__":
    run()
