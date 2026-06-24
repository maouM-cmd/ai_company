"""Meta deck: ナンジャモのハラバリーex - エレキストリーマー+サンダーボルト230"""
from cg.api import Observation, SelectContext, SelectType, OptionType, AreaType, to_observation_class, all_card_data
import os, sys
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
try:
    CARD_DB = {c.cardId: c for c in all_card_data()}
except Exception:
    CARD_DB = {}

ZUPIKA = 268; HARABARI_EX = 269; KAIDEN = 270; TAIKAID = 271
BASIC_LIGHTNING = 4
ULTRA_BALL = 1121; SWITCH = 1123; BOSS = 1182; LILLIE = 1227
CARMINE = 1192; JUDGE = 1213; STRETCHER = 1097; WAITRESS = 1235
CAPE = 1159; ENERGY_PRO = 1100

def read_deck_csv():
    return ([ZUPIKA]*4 + [HARABARI_EX]*4 + [KAIDEN]*4 + [TAIKAID]*3 +
            [BASIC_LIGHTNING]*14 + [ULTRA_BALL]*4 + [SWITCH]*4 + [BOSS]*4 +
            [LILLIE]*4 + [CARMINE]*4 + [JUDGE]*2 + [STRETCHER]*3 +
            [WAITRESS]*4 + [ENERGY_PRO]*1 + [JUDGE]*1)

def get_option_card_id(opt, obs):
    try:
        cid = getattr(opt, 'cardId', None) or getattr(opt, 'id', None)
        if cid is not None: return cid
        opt_idx = getattr(opt, 'index', None)
        if opt_idx is None: return -1
        state = obs.current; my_idx = state.yourIndex
        player_idx = getattr(opt, 'playerIndex', my_idx)
        p_state = state.players[player_idx]; area = getattr(opt, 'area', None)
        if area == AreaType.HAND and p_state.hand and 0 <= opt_idx < len(p_state.hand):
            return getattr(p_state.hand[opt_idx], 'id', -1)
        if area == AreaType.LOOKING and state.looking and 0 <= opt_idx < len(state.looking):
            return getattr(state.looking[opt_idx], 'id', -1)
        if area == AreaType.ACTIVE and p_state.active and 0 <= opt_idx < len(p_state.active):
            return getattr(p_state.active[opt_idx], 'id', -1) if p_state.active[opt_idx] else -1
        if area == AreaType.BENCH and p_state.bench and 0 <= opt_idx < len(p_state.bench):
            return getattr(p_state.bench[opt_idx], 'id', -1) if p_state.bench[opt_idx] else -1
        if state.looking and 0 <= opt_idx < len(state.looking):
            return getattr(state.looking[opt_idx], 'id', -1)
        if p_state.hand and 0 <= opt_idx < len(p_state.hand):
            return getattr(p_state.hand[opt_idx], 'id', -1)
    except: pass
    return -1

def select_main_action(obs):
    options = obs.select.option
    evolves, attacks, attaches, plays, retreats = [], [], [], [], []
    end_idx = None
    for i, opt in enumerate(options):
        try:
            t = opt.type
            if t == OptionType.EVOLVE: evolves.append(i)
            elif t == OptionType.ATTACK: attacks.append(i)
            elif t == OptionType.ATTACH: attaches.append(i)
            elif t == OptionType.PLAY: plays.append(i)
            elif t == OptionType.RETREAT: retreats.append(i)
            elif t == OptionType.END: end_idx = i
        except: pass
    state = obs.current; my_idx = state.yourIndex; my_state = state.players[my_idx]
    active = my_state.active[0] if my_state.active else None
    active_id = getattr(active, 'id', -1) if active else -1

    if evolves:
        for idx in evolves:
            cid = get_option_card_id(options[idx], obs)
            if cid == HARABARI_EX: return [idx]
            if cid == TAIKAID: return [idx]
        return [evolves[0]]

    if plays:
        bench_count = len([p for p in my_state.bench if p])
        allowed = []
        for idx in plays:
            cid = get_option_card_id(options[idx], obs)
            if cid in (ZUPIKA, KAIDEN):
                if bench_count < 5: allowed.append(idx)
            else: allowed.append(idx)
        prio = [ULTRA_BALL, WAITRESS, CAPE, BOSS, LILLIE, CARMINE, JUDGE, SWITCH, STRETCHER, ENERGY_PRO]
        for cid in prio:
            for idx in allowed:
                if get_option_card_id(options[idx], obs) == cid: return [idx]
        if allowed: return [allowed[0]]

    if attaches:
        for idx in attaches:
            if getattr(options[idx], 'inPlayArea', None) == AreaType.ACTIVE: return [idx]
        return [attaches[0]]

    if attacks: return [attacks[-1]]
    if retreats: return [retreats[0]]
    if end_idx is not None: return [end_idx]
    count = min(obs.select.maxCount, len(options))
    return list(range(count)) if count > 0 else []

def select_card(obs):
    select = obs.select; options = select.option
    context = select.context; max_count = select.maxCount; min_count = select.minCount
    state = obs.current; my_idx = state.yourIndex; my_state = state.players[my_idx]
    opp_idx = 1 - my_idx; opp_state = state.players[opp_idx]

    if context == SelectContext.SETUP_ACTIVE_POKEMON:
        for i, opt in enumerate(options):
            if get_option_card_id(opt, obs) in (ZUPIKA, KAIDEN): return [i]
        return [0] if options else []

    if context in (SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH):
        bench_count = len([p for p in my_state.bench if p])
        if bench_count >= 5 and min_count == 0: return []
        scored = [(100 if get_option_card_id(opt, obs) in (ZUPIKA, KAIDEN) else 50, i) for i, opt in enumerate(options)]
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    is_opp_bench = len(options) > 0 and all(
        getattr(opt, 'area', None) == AreaType.BENCH and getattr(opt, 'playerIndex', None) == opp_idx for opt in options)
    if is_opp_bench:
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs); opt_idx = getattr(opt, 'index', -1)
            poke = opp_state.bench[opt_idx] if opp_state.bench and 0 <= opt_idx < len(opp_state.bench) else None
            card = CARD_DB.get(cid); hp = getattr(card, 'hp', 100) if card else 100
            dmg = getattr(poke, 'damage', 0) if poke else 0
            scored.append((hp - dmg, i))
        scored.sort(key=lambda x: x[0])
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    if context == SelectContext.DISCARD:
        scored = [(0 if get_option_card_id(opt, obs) in (HARABARI_EX, ZUPIKA, KAIDEN, TAIKAID) else
                   40 if get_option_card_id(opt, obs) == BASIC_LIGHTNING else 70, i) for i, opt in enumerate(options)]
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    is_search = (getattr(obs.current, 'looking', None) is not None or getattr(obs.select, 'deck', None) is not None
                 or any(getattr(opt, 'area', None) == AreaType.DECK for opt in options))
    if is_search:
        scored = [(100 if get_option_card_id(opt, obs) == HARABARI_EX else
                   80 if get_option_card_id(opt, obs) in (ZUPIKA, KAIDEN) else
                   60 if get_option_card_id(opt, obs) == TAIKAID else
                   40 if get_option_card_id(opt, obs) == BASIC_LIGHTNING else 20, i) for i, opt in enumerate(options)]
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, 1); count = min(count, max_count, len(scored))
        return [x[1] for x in scored[:count]]

    count = max(min_count, 1); count = min(count, max_count, len(options))
    return list(range(count)) if count > 0 else []

def select_yes_no(obs):
    for i, opt in enumerate(obs.select.option):
        if opt.type == OptionType.YES: return [i]
    return [0] if obs.select.option else []

def agent(obs_dict):
    if obs_dict is None: return read_deck_csv()
    if hasattr(obs_dict, 'select'): obs = obs_dict
    else:
        if getattr(obs_dict, 'get', None) is None or obs_dict.get('select') is None: return read_deck_csv()
        try: obs = to_observation_class(obs_dict)
        except: return [0]
    if getattr(obs, 'select', None) is None or getattr(obs.select, 'option', None) is None: return read_deck_csv()
    if len(obs.select.option) == 0: return []
    if len(obs.select.option) == 1 and obs.select.maxCount == 1: return [0]
    sel_type = obs.select.type
    if sel_type == SelectType.MAIN: return select_main_action(obs)
    if sel_type == SelectType.YES_NO: return select_yes_no(obs)
    if sel_type == SelectType.CARD: return select_card(obs)
    count = min(obs.select.maxCount, len(obs.select.option))
    return list(range(count)) if count > 0 else []
