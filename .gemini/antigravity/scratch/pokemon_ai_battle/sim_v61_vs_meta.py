"""V61 vs 6 meta decks — win rate measurement (20 games each)"""
import sys, os, importlib.util, random, gc
sys.path.insert(0, r"C:\Users\admin\.gemini\antigravity\scratch\pokemon_ai_battle")

import cg.game as game
import cg.api as api

# sys.stdout.reconfigure(encoding='utf-8')  # Bashから実行時は不要

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def run_one(mod0, mod1, seed):
    random.seed(seed)
    deck0 = mod0.read_deck_csv()
    deck1 = mod1.read_deck_csv()
    obs, _ = game.battle_start(deck0, deck1)
    if obs is None:
        return None
    turn = 0
    try:
        while turn < 2000:
            turn += 1
            obs_obj = api.to_observation_class(obs)
            if obs_obj is None or obs_obj.select is None:
                break
            if len(obs_obj.select.option) == 0:
                result = (obs.get('current') or {}).get('result', None)
                game.battle_finish()
                return result
            if obs_obj.current.result != -1:
                result = obs_obj.current.result
                game.battle_finish()
                return result
            player = obs_obj.current.yourIndex if obs_obj.current else 0
            action = mod0.agent(obs) if player == 0 else mod1.agent(obs)
            obs = game.battle_select(action)
        game.battle_finish()
    except Exception as e:
        try:
            game.battle_finish()
        except Exception:
            pass
    return None

BASE = r"C:\Users\admin\.gemini\antigravity\scratch\pokemon_ai_battle"

v60 = load("v61", os.path.join(BASE, "v61_agent/main.py"))

meta_agents = [
    ("フーディン",   load("foodin",     os.path.join(BASE, "foodin_agent/main.py"))),
    ("ルカリオ",     load("lucario",    os.path.join(BASE, "meta_lucario_agent/main.py"))),
    ("イワパレス",   load("crustle",    os.path.join(BASE, "v15_agent/main.py"))),
    ("ユキノオー",   load("abomasnow",  os.path.join(BASE, "meta_abomasnow_agent/main.py"))),
    ("ハラバリーex", load("bellibolt",  os.path.join(BASE, "meta_bellibolt_agent/main.py"))),
    ("カビゴン",     load("snorlax",    os.path.join(BASE, "meta_snorlax_agent/main.py"))),
]

N = 20
total_w = total_g = 0

print("=== V61 (エースバーン水) vs meta (N=20 each) ===", flush=True)
for name, meta in meta_agents:
    wins = invalid = 0
    for seed in range(N):
        r = run_one(v60, meta, seed)
        if r is None:
            invalid += 1
        elif r == 0:
            wins += 1
        gc.collect()
    valid = N - invalid
    wr = wins / valid * 100 if valid > 0 else 0
    total_w += wins
    total_g += valid
    print(f"  {name:12s}: {wins:2d}/{valid:2d} = {wr:5.1f}%", flush=True)

overall = total_w / total_g * 100 if total_g > 0 else 0
print(f"\n  総合: {total_w}/{total_g} = {overall:.1f}%", flush=True)
