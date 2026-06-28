"""V67 vs V68 A/B 比較 — 同じ seeds で両エージェントを測定して公平比較"""
import sys, os, importlib.util, random, gc
from collections import defaultdict

sys.path.insert(0, r"C:\Users\admin\.gemini\antigravity\scratch\pokemon_ai_battle")
sys.stdout.reconfigure(encoding='utf-8')

import cg.game as game
from cg.api import to_observation_class


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_one(mod0, mod1, seed):
    random.seed(seed)
    try:
        deck0 = mod0.read_deck_csv()
        deck1 = mod1.read_deck_csv()
    except Exception:
        return None

    obs_dict, _ = game.battle_start(deck0, deck1)
    if obs_dict is None:
        return None

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
            if result != -1:
                game.battle_finish()
                return result
            if len(obs_obj.select.option) == 0:
                game.battle_finish()
                return 1
            player = curr.yourIndex
            try:
                action = mod0.agent(obs_dict) if player == 0 else mod1.agent(obs_dict)
            except Exception:
                game.battle_finish()
                return 1
            obs_dict = game.battle_select(action)

        game.battle_finish()
    except Exception:
        try:
            game.battle_finish()
        except Exception:
            pass
    return None


BASE = r"C:\Users\admin\.gemini\antigravity\scratch\pokemon_ai_battle"

v67 = load("v67", os.path.join(BASE, "v67_agent/main.py"))
v68 = load("v68", os.path.join(BASE, "v68_agent/main.py"))

meta_agents = [
    ("フーディン",   load("foodin",    os.path.join(BASE, "foodin_agent/main.py"))),
    ("ルカリオ",     load("lucario",   os.path.join(BASE, "meta_lucario_agent/main.py"))),
    ("イワパレス",   load("crustle",   os.path.join(BASE, "v15_agent/main.py"))),
    ("ユキノオー",   load("abomasnow", os.path.join(BASE, "meta_abomasnow_agent/main.py"))),
    ("ハラバリーex", load("bellibolt", os.path.join(BASE, "meta_bellibolt_agent/main.py"))),
    ("カビゴン",     load("snorlax",   os.path.join(BASE, "meta_snorlax_agent/main.py"))),
]

N = 20  # V67+V68 同じ seeds で測定（高速版）

print("=" * 65)
print(f"=== V67 vs V68 A/B 比較 (N={N} each) ===")
print("=" * 65)
print(f"  {'対面':12s}  V67   V68   差分  判定")
print("-" * 65)

total_v67_w = total_v68_w = total_g = 0

for meta_name, meta_mod in meta_agents:
    v67_wins = v68_wins = errors = 0

    for seed in range(N):
        r67 = run_one(v67, meta_mod, seed)
        r68 = run_one(v68, meta_mod, seed)
        if r67 is None or r68 is None:
            errors += 1
            continue
        if r67 == 0:
            v67_wins += 1
        if r68 == 0:
            v68_wins += 1
        gc.collect()

    valid = N - errors
    wr67 = v67_wins / valid * 100 if valid > 0 else 0
    wr68 = v68_wins / valid * 100 if valid > 0 else 0
    diff = wr68 - wr67
    mark = "↑" if diff > 2 else ("↓" if diff < -2 else "→")

    total_v67_w += v67_wins
    total_v68_w += v68_wins
    total_g += valid

    print(f"  {meta_name:12s}  {wr67:5.1f}%  {wr68:5.1f}%  {diff:+5.1f}%  {mark}")

print("-" * 65)
overall_v67 = total_v67_w / total_g * 100 if total_g > 0 else 0
overall_v68 = total_v68_w / total_g * 100 if total_g > 0 else 0
overall_diff = overall_v68 - overall_v67
verdict = "V68が上" if overall_diff > 1 else ("V67が上" if overall_diff < -1 else "ほぼ同等")

print(f"  {'総合':12s}  {overall_v67:5.1f}%  {overall_v68:5.1f}%  {overall_diff:+5.1f}%  {verdict}")
print()
print(f"V67: {total_v67_w}/{total_g}, V68: {total_v68_w}/{total_g}")
