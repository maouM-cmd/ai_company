import os
from pathlib import Path

# .envファイルがあれば読み込む（python-dotenv不要の軽量実装）
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
QIITA_TOKEN    = os.environ.get("QIITA_TOKEN",    "")

# 全モデル無料枠対応（Google AI Studio 無料ティア）
MODELS = {
    "ceo":     "models/gemini-2.0-flash",  # 1500 RPD 無料枠
    "manager": "models/gemini-2.0-flash",  # 1500 RPD 無料枠
    "worker":  "models/gemini-2.0-flash",  # 1500 RPD 無料枠
}

# Gemini のmax_output_tokens
MAX_TOKENS = {
    "ceo":     4096,
    "manager": 4096,
    "worker":  8192,   # 2048 → 8192（記事途中切断を防ぐ）
}

TASK_TIMEOUT_SEC = 300  # エージェント応答タイムアウト（Ollama対応で延長）

# Ollama（ローカルLLM）設定
OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
