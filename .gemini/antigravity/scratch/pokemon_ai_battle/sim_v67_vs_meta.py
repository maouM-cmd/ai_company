"""v67 vs 6 meta decks — win rate + detailed loss analysis (v65_loss_analysis.txt 形式)"""
import sys, os, importlib.util, random, gc
from collections import defaultdict

sys.path.insert(0, r"C:\Users\admin\.gemini\antigravity\scratch\pokemon_ai_battle")
sys.stdout.reconfigure(encoding='utf-8')

import cg.game as game
import cg.api as api
from cg.api import to_observation_class

CARD_NAMES = {
    860:  "Snorunt",
    861:  "MegaFroslassEx",
    1030: "Staryu",
    1031: "MegaStarmieEx",
    3:    "WaterE",
    11:   "MistE",
    12:   "LegacyE",
    17:   "IgnitionE",
    677:  "Riolu",
    678:  "LucarioEx",
    673:  "Lucario",
    675:  "Lucario675",
    743:  "AlakazamEx",
    742:  "Kadabra",
    741:  "Abra",
    345:  "Crustle",
    344:  "Dwebble",
    532:  "Crustle532",
    1072: "Snorlax",
    878:  "Cufant",
    879:  "Copperajah",
    723:  "Abomasnow",
    722:  "Snover",
    119:  "Dreepy",
    120:  "Drakloak",
    121:  "DragapultEx",
    666:  "Cinderace",
    140:  "Omastar",
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def card_name(cid):
    return CARD_NAMES.get(cid, f"#{cid}")


def run_one_detailed(mod0, mod1, seed):
    """1試合実行。戻り値: (result, history, final_state)"""
    random.seed(seed)
    try:
        deck0 = mod0.read_deck_csv()
        deck1 = mod1.read_deck_csv()
    except Exception as e:
        return None, [], {}

    obs_dict, _ = game.battle_start(deck0, deck1)
    if obs_dict is None:
        return None, [], {}

    history = []
    last_state = {}
    turn = 0

    try:
        while turn < 2000:
            turn += 1
            obs_obj = to_observation_class(obs_dict)
            if obs_obj is None or obs_obj.select is None:
                break

            curr = obs_obj.current
            if curr is None:
                break

            result = curr.result
            my_idx = curr.yourIndex
            opp_idx = 1 - my_idx
            my_s   = curr.players[my_idx]  if curr.players and len(curr.players) > my_idx  else None
            opp_s  = curr.players[opp_idx] if curr.players and len(curr.players) > opp_idx else None

            if my_s:
                active     = my_s.active[0] if my_s.active else None
                bench_list = [p for p in (my_s.bench or []) if p]
                active_id  = getattr(active, 'id', -1)  if active else -1
                active_ene = len(getattr(active, 'energies', []) or []) if active else 0
                active_dmg = getattr(active, 'damage', 0) if active else 0
                deck_cnt   = getattr(my_s, 'deckCount', 0)
                prizes     = len(my_s.prize) if my_s.prize else 0
                bench_ids  = [getattr(p, 'id', -1) for p in bench_list]
                bench_ene  = [len(getattr(p, 'energies', []) or []) for p in bench_list]

                opp_active    = opp_s.active[0] if opp_s and opp_s.active else None
                opp_active_id = getattr(opp_active, 'id', -1) if opp_active else -1
                opp_active_dmg= getattr(opp_active, 'damage', 0) if opp_active else 0

                t = getattr(curr, 'turn', turn)
                snap = {
                    'turn':           t,
                    'my_active_id':   active_id,
                    'my_active_ene':  active_ene,
                    'my_active_dmg':  active_dmg,
                    'my_bench_cnt':   len(bench_list),
                    'my_bench_ids':   bench_ids,
                    'my_bench_ene':   bench_ene,
                    'my_deck':        deck_cnt,
                    'my_prizes':      prizes,
                    'opp_active_id':  opp_active_id,
                    'opp_active_dmg': opp_active_dmg,
                }
                history.append(snap)
                last_state = snap

            if result != -1:
                game.battle_finish()
                return result, history, last_state

            if len(obs_obj.select.option) == 0:
                res = (obs_dict.get('current') or {}).get('result', -1) if isinstance(obs_dict, dict) else -1
                game.battle_finish()
                return (0 if res == 0 else 1), history, last_state

            player = curr.yourIndex if curr else 0
            try:
                action = mod0.agent(obs_dict) if player == 0 else mod1.agent(obs_dict)
            except Exception:
                game.battle_finish()
                return 1, history, last_state

            obs_dict = game.battle_select(action)

        game.battle_finish()
    except Exception:
        try:
            game.battle_finish()
        except Exception:
            pass

    return None, history, last_state


def defeat_reason(last_state, history):
    if not last_state:
        return "UNKNOWN"
    bench  = last_state.get('my_bench_cnt', 0)
    deck   = last_state.get('my_deck', 99)
    active = last_state.get('my_active_id', -1)
    t      = last_state.get('turn', 0)
    if deck == 0:
        return "DECK_OUT"
    if bench == 0 and active == -1:
        return "BENCH_OUT"
    if bench == 0:
        return "BENCH_OUT"
    return f"OTHER(t={t},bench={bench})"


def format_loss(meta_name, seed, last_state, history):
    reason = defeat_reason(last_state, history)
    t      = last_state.get('turn', 0)
    lines  = []
    lines.append(f"[{meta_name}] seed={seed} 敗因={reason} (turn={t})")

    active_id  = last_state.get('my_active_id', -1)
    active_ene = last_state.get('my_active_ene', 0)
    active_dmg = last_state.get('my_active_dmg', 0)
    bench_cnt  = last_state.get('my_bench_cnt', 0)
    bench_ids  = last_state.get('my_bench_ids', [])
    bench_ene  = last_state.get('my_bench_ene', [])
    deck_cnt   = last_state.get('my_deck', 0)
    prizes     = last_state.get('my_prizes', 0)
    opp_id     = last_state.get('opp_active_id', -1)
    opp_dmg    = last_state.get('opp_active_dmg', 0)

    bench_str = "[" + ",".join(f"{card_name(b)}(e={bench_ene[i] if i<len(bench_ene) else 0})" for i,b in enumerate(bench_ids)) + "]"
    lines.append(f"  自: {card_name(active_id)}(ene={active_ene},dmg={active_dmg})  bench={bench_cnt}{bench_str}")
    lines.append(f"  自: deck={deck_cnt} prizes_left={prizes}")
    lines.append(f"  相手: {card_name(opp_id)}(dmg={opp_dmg})")
    lines.append("  最後6ターン:")

    tail = history[-6:] if len(history) >= 6 else history
    for s in tail:
        my_n  = card_name(s['my_active_id'])
        opp_n = card_name(s['opp_active_id'])
        lines.append(
            f"    t={s['turn']:3d} 自:{my_n}(ene={s['my_active_ene']},dmg={s['my_active_dmg']}) "
            f"bench={s['my_bench_cnt']} vs 相手:{opp_n}(dmg={s['opp_active_dmg']})"
        )
    lines.append("")
    return "\n".join(lines)


BASE = r"C:\Users\admin\.gemini\antigravity\scratch\pokemon_ai_battle"

v67 = load("v67", os.path.join(BASE, "v67_agent/main.py"))

meta_agents = [
    ("フーディン",   load("foodin",    os.path.join(BASE, "foodin_agent/main.py"))),
    ("ルカリオ",     load("lucario",   os.path.join(BASE, "meta_lucario_agent/main.py"))),
    ("イワパレス",   load("crustle",   os.path.join(BASE, "v15_agent/main.py"))),
    ("ユキノオー",   load("abomasnow", os.path.join(BASE, "meta_abomasnow_agent/main.py"))),
    ("ハラバリーex", load("bellibolt", os.path.join(BASE, "meta_bellibolt_agent/main.py"))),
    ("カビゴン",     load("snorlax",   os.path.join(BASE, "meta_snorlax_agent/main.py"))),
]

N = 20

OUTPUT_PATH = os.path.join(BASE, "v67_loss_analysis.txt")

out_lines = []
out_lines.append("=" * 60)
out_lines.append("=== v67 (フロストラスex水) vs meta (N=20 each) ===")
out_lines.append("=" * 60)

total_w = total_g = 0

for meta_name, meta_mod in meta_agents:
    wins = errors = 0
    loss_records = []

    for seed in range(N):
        result, history, last_state = run_one_detailed(v67, meta_mod, seed)
        if result is None:
            errors += 1
        elif result == 0:
            wins += 1
        else:
            loss_records.append((seed, last_state, history))
        gc.collect()

    valid = N - errors
    losses = valid - wins
    wr = wins / valid * 100 if valid > 0 else 0
    total_w += wins
    total_g += valid

    reason_counts = defaultdict(int)
    for _, ls, hist in loss_records:
        r = defeat_reason(ls, hist)
        key = r.split("(")[0]
        reason_counts[key] += 1

    reason_str = "  [" + " ".join(f"{k}:{v}" for k, v in reason_counts.items()) + "]"
    out_lines.append(f"  {meta_name:12s}: {wins:2d}/{valid:2d} = {wr:5.1f}%  損:{losses}{reason_str}")
    print(f"  {meta_name:12s}: {wins:2d}/{valid:2d} = {wr:5.1f}%  損:{losses}{reason_str}", flush=True)

overall = total_w / total_g * 100 if total_g > 0 else 0
out_lines.append("")
out_lines.append(f"  v67 総合: {total_w}/{total_g} = {overall:.1f}%")
print(f"\n  v67 総合: {total_w}/{total_g} = {overall:.1f}%", flush=True)

out_lines.append("")
out_lines.append("=" * 60)
out_lines.append("=== V65 比較 ===")
out_lines.append("=" * 60)
v65_data = {
    "フーディン":   (10, 20),
    "ルカリオ":     (10, 20),
    "イワパレス":   (7,  20),
    "ユキノオー":   (6,  20),
    "ハラバリーex": (16, 20),
    "カビゴン":     (6,  20),
}
out_lines.append("  対面          V65勝率  v67勝率  差分")
for meta_name, meta_mod in meta_agents:
    if meta_name in v65_data:
        w65, g65 = v65_data[meta_name]
        wr65 = w65 / g65 * 100

out_lines.append("")
out_lines.append("=" * 60)
out_lines.append("=== v67 負け試合 詳細ログ ===")
out_lines.append("=" * 60)
out_lines.append("")

# 再度走らせてログを収集済みなのでもう一度 meta_agents をループ
# (loss_records は前のループでスコープ外なので再計算)
total_w2 = total_g2 = 0
per_meta_losses = {}

print("\n詳細ログ収集中...", flush=True)

for meta_name, meta_mod in meta_agents:
    wins2 = errors2 = 0
    loss_recs = []
    for seed in range(N):
        result, history, last_state = run_one_detailed(v67, meta_mod, seed)
        if result is None:
            errors2 += 1
        elif result == 0:
            wins2 += 1
        else:
            loss_recs.append((seed, last_state, history))
        gc.collect()
    per_meta_losses[meta_name] = loss_recs
    total_w2 += wins2
    total_g2 += (N - errors2)
    print(f"  {meta_name} 詳細収集完了", flush=True)

for meta_name, _ in meta_agents:
    for seed, last_state, history in per_meta_losses.get(meta_name, []):
        out_lines.append(format_loss(meta_name, seed, last_state, history))

# ファイル書き出し
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))
    f.write("\n")

print(f"\n結果を {OUTPUT_PATH} に保存しました", flush=True)

