# References

## ポケモン AI バトル

| リソース | パス / URL |
|---------|-----------|
| 現行エージェント | `.gemini/antigravity/scratch/pokemon_ai_battle/v54_agent/main.py` |
| MCTS 実装 | `.gemini/antigravity/scratch/pokemon_ai_battle/v54_agent/mcts.py` |
| 提出エージェント (fixed) | `Desktop/submission_fixed/main.py` |
| 提出エージェント (steel_fire) | `Desktop/submission_steel_fire/main.py` |
| テストスクリプト群 | `.gemini/antigravity/scratch/pokemon_ai_battle/` 直下 |
| 全メタ対戦シミュレーション | `.gemini/antigravity/scratch/pokemon_ai_battle/sim_all_vs_meta.py` |
| ポケモン AI CLAUDE.md | `.gemini/antigravity/scratch/pokemon_ai_battle/CLAUDE.md` |

### `cg` API 主要インポート
```python
from cg.api import (
    Observation, SelectContext, SelectType, OptionType, AreaType,
    to_observation_class, all_card_data
)
```

### カード ID 早見表（V54 デッキ）
| カード名 | ID |
|---------|-----|
| メガガーデボワールex | 747 |
| ラルトス | 745 |
| キルリア | 746 |
| ラティアスex | 184 |
| さけぶしっぽex | 969 |
| テレパシーサイキックエネルギー | 19 |
| ヒーローズケープ | 1159 |
| クラッシュハンマー | 1120 |
| ポケモンいれかえ | 1123 |
| スーパーポーション | 1112 |
| キズぐすり | 1117 |
| ボスの指令 | 1182 |
| リーリエの全力 | 1227 |
| レーシー | 1199 |
| ジャッジ | 1213 |
| ダークボール | 1102 |

## aliens.py (pygame ゲーム)

| リソース | 場所 |
|---------|------|
| ゲーム本体 | `aliens.py` |
| アセット (画像・サウンド) | `data/` |
| pygame ドキュメント | https://www.pygame.org/docs/ |
