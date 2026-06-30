"""
サーバー起動スクリプト（Windows Task Scheduler / 手動起動用）
- uvicorn サーバーをバックグラウンドで起動
- ステータスダッシュボードを別ウィンドウで自動表示
"""
import subprocess
import sys
import os
import time

os.chdir(r"C:\Users\admin\ai_company")
python = r"C:\Users\admin\AppData\Local\Programs\Python\Python311\python.exe"
base   = r"C:\Users\admin\ai_company"

# サーバーをバックグラウンドで起動
server = subprocess.Popen(
    [python, "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8002"],
    cwd=base,
    stdout=open(rf"{base}\server.log", "a"),
    stderr=open(rf"{base}\server_err.log", "a"),
    creationflags=0x00000008,  # DETACHED_PROCESS
)
print(f"サーバー起動: PID={server.pid}")

# 3秒待ってからステータス画面を別ウィンドウで開く
time.sleep(3)
subprocess.Popen(
    [
        "powershell", "-NoExit", "-Command",
        f'$env:PYTHONIOENCODING="utf-8"; & "{python}" "{base}\\status_cli.py"',
    ],
    creationflags=0x00000010,  # CREATE_NEW_CONSOLE（新しいウィンドウ）
    cwd=base,
)
print("ステータス画面を起動しました")
