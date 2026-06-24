"""V54 and V58 vs 6 meta decks — win rate comparison"""
import sys, os, importlib.util, random
sys.path.insert(0, ".")

import cg.game as game
import cg.api as api

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
    try:
        while True:
            obs_obj = api.to_observation_class(obs)
            if obs_obj is None or obs_obj.select is None:
                break
            if len(obs_obj.select.option) == 0:
                return (obs.get('current') or {}).get('result', None)
            player = obs_obj.current.yourIndex if obs_obj.current else 0
            action = mod0.agent(obs) if player == 0 else mod1.agent(obs)
            obs = game.battle_select(action)
    except Exception:
        return None
    finally:
        try:
            game.battle_finish()
        except Exception:
            pass
    return None

BASE = os.path.dirname(os.path.abspath(__file__))

meta_agents = [
    ("フーディン",   load("foodin",     os.path.join(BASE, "foodin_agent/main.py"))),
    ("ルカリオ",     load("lucario",    os.path.join(BASE, "meta_lucario_agent/main.py"))),
    ("イワパレス",   load("crustle",    os.path.join(BASE, "v15_agent/main.py"))),
    ("ユキノオー",   load("abomasnow",  os.path.join(BASE, "meta_abomasnow_agent/main.py"))),
    ("ハラバリーex", load("bellibolt",  os.path.join(BASE, "meta_bellibolt_agent/main.py"))),
    ("カビゴン",     load("snorlax",    os.path.join(BASE, "meta_snorlax_agent/main.py"))),
]

agents_to_test = [
    ("V54", load("v54", os.path.join(BASE, "v54_agent/main.py"))),
    ("V58", load("v58", os.path.join(BASE, "v58_agent/main.py"))),
]
for _, ag in agents_to_test:
    ag.MCTS_AVAILABLE = False

N = 20

for ag_name, ag in agents_to_test:
    print(f"\n=== {ag_name} vs meta (N={N}) ===")
    total_w = total_g = 0
    for name, meta in meta_agents:
        wins = invalid = 0
        for seed in range(N):
            r = run_one(ag, meta, seed)
            if r is None:
                invalid += 1
            elif r == 0:
                wins += 1
        valid = N - invalid
        wr = wins/valid*100 if valid > 0 else 0
        total_w += wins; total_g += valid
        print(f"  {name:12s}: {wins:2d}/{valid:2d} = {wr:5.1f}%")
    overall = total_w/total_g*100 if total_g > 0 else 0
    print(f"  {'総合':12s}: {total_w}/{total_g} = {overall:.1f}%")
