"""
V57: イイネイヌex + モモワロウex「毒260デスマシン」
- ポイズンマッスル(1エネ): 山札から悪エネ2枚付けて自毒
- クレイジーチェーン(悪悪●): 130 + 毒中+130 = 260ダメ!
- モモワロウex特性しはいのくさり: ベンチの悪ポケを入れ替えて毒に
- vsフーディン(弱点:悪) → 260×2=520 瞬殺
- vsルカリオ/ユキノオー/ハラバリーex → 260で2ターン
- vsカビゴン → 260 > 160 一撃KO
- vsイワパレス → 非exのゾロアーク(マインドジャック) で対処
"""
from cg.api import (
    Observation, SelectContext, SelectType, OptionType, AreaType,
    to_observation_class, all_card_data
)
import os
import sys

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

try:
    from mcts import run_mcts
    MCTS_AVAILABLE = True
except ImportError:
    MCTS_AVAILABLE = False

# --- Card IDs ---
IINEEINU_EX = 138       # HP250, ポイズンマッスル(●) / クレイジーチェーン(悪悪● 130+毒130)
MOMOWARO_EX = 141       # HP190, 特性しはいのくさり(ベンチ悪交代+毒) / イライラバースト(悪悪 60×サイド)
ZORUA = 614             # HP70, 非ex進化前(イワパレス対策)
ZOROARK = 615           # HP120, 非ex, マインドジャック(悪 ベンチ数×30) / イカサマ
BASIC_DARK = 7

ULTRA_BALL = 1121
SWITCH = 1123
BOSS_ORDERS = 1182
LILLIES_DETERMINATION = 1227
JUDGE = 1213
CARMINE = 1192
NIGHT_STRETCHER = 1097
DARK_BALL = 1102        # 山札下7枚からポケモン1枚サーチ
MAXIMUM_BELT = 1158     # ACE SPEC: +50 vs ex
GIIMA = 1230            # 山札上7枚から悪ポケをベンチに出す
HEROS_CAPE = 1159

HP_TABLE = {
    IINEEINU_EX: 250,
    MOMOWARO_EX: 190,
    ZOROARK: 120,
    ZORUA: 70,
}

MY_POKEMON = {IINEEINU_EX, MOMOWARO_EX, ZORUA, ZOROARK}

# --- Opponent memory ---
_opp_seen_ids: set = set()
_my_last_prize_count: int = 6


def _update_opp_memory(obs: Observation):
    global _opp_seen_ids, _my_last_prize_count
    state = getattr(obs, 'current', None)
    if not state:
        return
    my_idx = state.yourIndex
    my_prizes = len(state.players[my_idx].prize)
    if my_prizes == 6 and _my_last_prize_count < 6:
        _opp_seen_ids = set()
    _my_last_prize_count = my_prizes
    opp_idx = 1 - my_idx
    opp_state = state.players[opp_idx]
    for p in (opp_state.active or []) + (opp_state.bench or []):
        if p:
            cid = getattr(p, 'id', None)
            if cid:
                _opp_seen_ids.add(cid)
    for c in (opp_state.discard or []):
        if c:
            cid = getattr(c, 'id', None)
            if cid:
                _opp_seen_ids.add(cid)


def read_deck_csv() -> list[int]:
    return (
        [IINEEINU_EX] * 4 +         # 4  メインアタッカー (たね, 進化不要!)
        [MOMOWARO_EX] * 3 +         # 7  特性で入れ替え+毒付与
        [ZORUA] * 2 +               # 9  進化前(イワパレス対策)
        [ZOROARK] * 2 +             # 11 非ex, マインドジャックでイワパレスを倒す
        [BASIC_DARK] * 12 +         # 23 悪エネ
        [ULTRA_BALL] * 4 +          # 27
        [SWITCH] * 4 +              # 31 にげるコスト3対策
        [BOSS_ORDERS] * 4 +         # 35
        [LILLIES_DETERMINATION] * 4 +# 39
        [JUDGE] * 2 +               # 41
        [CARMINE] * 4 +             # 45
        [NIGHT_STRETCHER] * 3 +     # 48
        [DARK_BALL] * 4 +           # 52
        [MAXIMUM_BELT] * 1 +        # 53 ACE SPEC (+50 vs ex)
        [GIIMA] * 4 +               # 57
        [JUDGE] * 2 +               # 59
        [BASIC_DARK] * 1            # 60
    )


def get_option_card_id(opt, obs: Observation) -> int:
    try:
        cid = getattr(opt, 'cardId', None)
        if cid is not None:
            return cid
        cid = getattr(opt, 'id', None)
        if cid is not None:
            return cid
        opt_idx = getattr(opt, 'index', None)
        if opt_idx is None:
            return -1
        state = getattr(obs, 'current', None)
        if not state:
            return -1
        my_idx = state.yourIndex
        player_idx = getattr(opt, 'playerIndex', my_idx)
        p_state = state.players[player_idx]
        area = getattr(opt, 'area', None)
        resolved_id = -1
        if area == AreaType.HAND:
            if p_state.hand and 0 <= opt_idx < len(p_state.hand):
                resolved_id = getattr(p_state.hand[opt_idx], 'id', -1)
        elif area == AreaType.LOOKING:
            if state.looking and 0 <= opt_idx < len(state.looking):
                resolved_id = getattr(state.looking[opt_idx], 'id', -1)
        elif area == AreaType.ACTIVE:
            if p_state.active and 0 <= opt_idx < len(p_state.active) and p_state.active[opt_idx]:
                resolved_id = getattr(p_state.active[opt_idx], 'id', -1)
        elif area == AreaType.BENCH:
            if p_state.bench and 0 <= opt_idx < len(p_state.bench) and p_state.bench[opt_idx]:
                resolved_id = getattr(p_state.bench[opt_idx], 'id', -1)
        elif area == AreaType.DISCARD:
            if p_state.discard and 0 <= opt_idx < len(p_state.discard):
                resolved_id = getattr(p_state.discard[opt_idx], 'id', -1)
        elif area == AreaType.DECK:
            if getattr(obs.select, 'deck', None) and 0 <= opt_idx < len(obs.select.deck):
                resolved_id = getattr(obs.select.deck[opt_idx], 'id', -1)
        if resolved_id != -1:
            return resolved_id
        if state.looking and 0 <= opt_idx < len(state.looking):
            resolved_id = getattr(state.looking[opt_idx], 'id', -1)
        if resolved_id == -1 and getattr(obs.select, 'deck', None) and 0 <= opt_idx < len(obs.select.deck):
            resolved_id = getattr(obs.select.deck[opt_idx], 'id', -1)
        if resolved_id == -1 and p_state.hand and 0 <= opt_idx < len(p_state.hand):
            resolved_id = getattr(p_state.hand[opt_idx], 'id', -1)
        return resolved_id
    except Exception:
        return -1


def get_energies(poke) -> int:
    if not poke:
        return 0
    try:
        energies = getattr(poke, 'energies', [])
        return len(energies) if energies else 0
    except Exception:
        return 0


def get_dark_energies(poke) -> int:
    if not poke:
        return 0
    try:
        energies = getattr(poke, 'energies', [])
        return sum(1 for e in energies if getattr(e, 'id', -1) == BASIC_DARK) if energies else 0
    except Exception:
        return 0


def is_poisoned(poke) -> bool:
    if not poke:
        return False
    try:
        status = getattr(poke, 'status', None)
        if status is None:
            return False
        status_str = str(status).lower()
        return 'poison' in status_str or 'どく' in status_str or status == 2
    except Exception:
        return False


def get_remaining_hp(poke) -> int:
    if not poke:
        return 9999
    cid = getattr(poke, 'id', -1)
    card = CARD_DB.get(cid)
    hp = getattr(card, 'hp', 200) if card else 200
    damage = getattr(poke, 'damage', 0)
    return max(0, hp - damage)


def identify_opponent_deck(obs: Observation) -> str:
    seen = set(_opp_seen_ids)
    state = getattr(obs, 'current', None)
    if state:
        opp_idx = 1 - state.yourIndex
        opp_state = state.players[opp_idx]
        for p in (opp_state.active or []) + (opp_state.bench or []):
            if p:
                seen.add(getattr(p, 'id', -1))
    if any(cid in seen for cid in [743, 742, 741, 245, 109]):
        return "ALAKAZAM"
    if any(cid in seen for cid in [678, 677]):
        return "LUCARIO"
    if any(cid in seen for cid in [345, 344, 532]):
        return "CRUSTLE"
    if any(cid in seen for cid in [723, 722]):
        return "ABOMASNOW"
    if any(cid in seen for cid in [269, 268, 271, 270]):
        return "BELLIBOLT"
    if any(cid in seen for cid in [1072]):
        return "SNORLAX"
    return "UNKNOWN"


def _should_retreat(obs: Observation) -> bool:
    state = obs.current
    if not state:
        return False
    my_idx = state.yourIndex
    my_state = state.players[my_idx]
    active = my_state.active[0] if my_state.active else None
    if not active:
        return False
    a_id = getattr(active, 'id', -1)

    # Retreat non-attacker to bring イイネイヌex active
    iineeinu_bench = [
        p for p in my_state.bench
        if p and getattr(p, 'id', -1) == IINEEINU_EX
        and getattr(p, 'damage', 0) < 200
    ]
    if a_id not in (IINEEINU_EX, ZOROARK) and iineeinu_bench:
        return True

    a_dmg = getattr(active, 'damage', 0)
    max_hp = HP_TABLE.get(a_id, 200)
    remaining = max_hp - a_dmg
    if remaining >= max_hp * 0.35:
        return False
    healthy = [
        p for p in my_state.bench
        if p and getattr(p, 'id', -1) in (IINEEINU_EX, MOMOWARO_EX)
        and getattr(p, 'damage', 0) < 50
    ]
    return len(healthy) > 0


def select_main_action(obs: Observation) -> list[int]:
    options = obs.select.option
    evolves, attacks, attaches, plays, retreats = [], [], [], [], []
    end_idx = None
    for i, opt in enumerate(options):
        try:
            otype = opt.type
            if otype == OptionType.EVOLVE:
                evolves.append(i)
            elif otype == OptionType.ATTACK:
                attacks.append(i)
            elif otype == OptionType.ATTACH:
                attaches.append(i)
            elif otype == OptionType.PLAY:
                plays.append(i)
            elif otype == OptionType.RETREAT:
                retreats.append(i)
            elif otype == OptionType.END:
                end_idx = i
        except Exception:
            pass

    state = obs.current
    my_idx = state.yourIndex
    my_state = state.players[my_idx]
    opp_idx = 1 - my_idx
    opp_state = state.players[opp_idx]
    active_poke = my_state.active[0] if my_state.active else None
    active_id = getattr(active_poke, 'id', -1) if active_poke else -1
    active_damage = getattr(active_poke, 'damage', 0) if active_poke else 0
    active_poisoned = is_poisoned(active_poke)
    active_dark = get_dark_energies(active_poke)
    active_total = get_energies(active_poke)

    opp_deck = identify_opponent_deck(obs)
    is_crustle = (opp_deck == "CRUSTLE")
    max_bench = 2 if opp_deck == "ALAKAZAM" else 5

    if retreats and _should_retreat(obs):
        return [retreats[0]]

    # 1. EVOLVE: ゾロア→ゾロアーク (イワパレス対策)
    if evolves:
        for idx in evolves:
            if get_option_card_id(options[idx], obs) == ZOROARK:
                return [idx]
        return [evolves[0]]

    # 2. PLAYS
    if plays:
        bench_count = len([p for p in my_state.bench if p is not None])
        has_iineeinu = any(getattr(p, 'id', -1) == IINEEINU_EX for p in my_state.bench if p)
        has_momowaro = any(getattr(p, 'id', -1) == MOMOWARO_EX for p in my_state.bench if p)
        has_zoroark = any(getattr(p, 'id', -1) in (ZORUA, ZOROARK) for p in my_state.bench if p)

        allowed = []
        for idx in plays:
            cid = get_option_card_id(options[idx], obs)
            if cid in (IINEEINU_EX, MOMOWARO_EX, ZORUA):
                if bench_count < max_bench:
                    allowed.append(idx)
            else:
                allowed.append(idx)

        # Bench priority: バックアップ確保
        if bench_count < max_bench:
            if not has_iineeinu and active_id == IINEEINU_EX:
                for idx in allowed:
                    if get_option_card_id(options[idx], obs) == IINEEINU_EX:
                        return [idx]
            if not has_momowaro:
                for idx in allowed:
                    if get_option_card_id(options[idx], obs) == MOMOWARO_EX:
                        return [idx]
            if is_crustle and not has_zoroark:
                for idx in allowed:
                    if get_option_card_id(options[idx], obs) in (ZORUA, ZOROARK):
                        return [idx]
            for idx in allowed:
                cid = get_option_card_id(options[idx], obs)
                if cid == IINEEINU_EX:
                    return [idx]

        active_hp = HP_TABLE.get(active_id, 200)
        active_remaining = active_hp - active_damage

        # When active is non-attacker, urgently search for イイネイヌex
        active_is_attacker = active_id in (IINEEINU_EX, ZOROARK)
        iineeinu_in_play = any(
            getattr(p, 'id', -1) == IINEEINU_EX
            for p in (my_state.bench or []) + (my_state.active or [])
            if p
        )

        if not active_is_attacker and not iineeinu_in_play:
            priority = [ULTRA_BALL, DARK_BALL, GIIMA, SWITCH, NIGHT_STRETCHER,
                        BOSS_ORDERS, LILLIES_DETERMINATION, CARMINE, JUDGE]
        elif active_remaining <= active_hp * 0.35:
            priority = [SWITCH, NIGHT_STRETCHER, ULTRA_BALL, BOSS_ORDERS,
                        LILLIES_DETERMINATION, CARMINE, JUDGE, GIIMA, DARK_BALL]
        else:
            priority = [ULTRA_BALL, DARK_BALL, GIIMA, BOSS_ORDERS,
                        LILLIES_DETERMINATION, CARMINE, SWITCH, JUDGE, NIGHT_STRETCHER]

        if opp_deck == "SNORLAX":
            for d in (LILLIES_DETERMINATION, CARMINE, JUDGE):
                if d in priority:
                    priority.remove(d)
        elif my_state.deckCount > 5:
            priority.insert(2, LILLIES_DETERMINATION)
            priority.insert(3, CARMINE)
            priority.insert(4, JUDGE)

        # Boss: pull target for 260 KO
        opp_active = opp_state.active[0] if opp_state.active else None
        opp_remaining = get_remaining_hp(opp_active)
        use_boss = False
        if active_id in (IINEEINU_EX, ZOROARK) and active_dark >= 2:
            for p in opp_state.bench:
                if p and get_remaining_hp(p) <= 260:
                    use_boss = True
                    break

        if use_boss:
            if BOSS_ORDERS in priority:
                priority.remove(BOSS_ORDERS)
            priority.insert(0, BOSS_ORDERS)

        for card_id in priority:
            for idx in allowed:
                if get_option_card_id(options[idx], obs) == card_id:
                    return [idx]

    # 3. ATTACHES
    if attaches:
        if active_id == IINEEINU_EX:
            if active_dark < 2:
                for idx in attaches:
                    if getattr(options[idx], 'inPlayArea', None) == AreaType.ACTIVE:
                        return [idx]
            else:
                bench_need = [
                    (i, p) for i, p in enumerate(my_state.bench)
                    if p and getattr(p, 'id', -1) == IINEEINU_EX and get_dark_energies(p) < 2
                ]
                if bench_need:
                    bi = bench_need[0][0]
                    for idx in attaches:
                        opt = options[idx]
                        if (getattr(opt, 'inPlayArea', None) == AreaType.BENCH
                                and getattr(opt, 'index', -1) == bi):
                            return [idx]
        for idx in attaches:
            if getattr(options[idx], 'inPlayArea', None) == AreaType.ACTIVE:
                return [idx]
        return [attaches[0]]

    # 4. ATTACKS
    if attacks:
        opp_active = opp_state.active[0] if opp_state.active else None
        opp_cid = getattr(opp_active, 'id', -1) if opp_active else -1
        opp_card = CARD_DB.get(opp_cid)
        opp_is_ex = (getattr(opp_card, 'ex', False) or getattr(opp_card, 'megaEx', False)
                     or 'ex' in (getattr(opp_card, 'name', '') or '').lower()) if opp_card else False

        if active_id == IINEEINU_EX:
            # ポイズンマッスルでエネ補充+毒化 → 次ターンクレイジーチェーン260
            if active_dark < 2 and not active_poisoned:
                return [attacks[0]]  # ポイズンマッスル (●)
            if active_dark >= 2 and active_total >= 3:
                return [attacks[-1]]  # クレイジーチェーン 260
            if active_dark < 2:
                return [attacks[0]]  # まずエネ確保
            return [attacks[-1]]

        elif active_id == ZOROARK:
            # イカサマで相手の技をコピー or マインドジャック
            if len(attacks) > 1 and is_crustle:
                return [attacks[1]]  # イカサマでグレートシザーコピー
            return [attacks[-1]]

        return [attacks[-1]]

    if retreats:
        return [retreats[0]]

    if end_idx is not None:
        return [end_idx]

    count = min(obs.select.maxCount, len(options))
    return list(range(count)) if count > 0 else []


def select_card(obs: Observation) -> list[int]:
    select = obs.select
    options = select.option
    context = select.context
    max_count = select.maxCount
    min_count = select.minCount
    state = obs.current
    my_idx = state.yourIndex
    my_state = state.players[my_idx]
    opp_idx = 1 - my_idx
    opp_state = state.players[opp_idx]

    # "My bench to active" selection (retreat target / KO replacement)
    is_my_bench = len(options) > 0 and all(
        getattr(opt, 'area', None) == AreaType.BENCH
        and getattr(opt, 'playerIndex', my_idx) == my_idx
        for opt in options
    ) and all(
        getattr(opt, 'playerIndex', my_idx) == my_idx for opt in options
    )
    if is_my_bench:
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            opt_idx = getattr(opt, 'index', -1)
            poke = my_state.bench[opt_idx] if my_state.bench and 0 <= opt_idx < len(my_state.bench) else None
            dark_e = get_dark_energies(poke)
            hp = HP_TABLE.get(cid, 200)
            dmg = getattr(poke, 'damage', 0) if poke else 0
            remaining = hp - dmg
            if cid == IINEEINU_EX:
                score = 1000 + dark_e * 100
            elif cid == ZOROARK:
                score = 600
            elif cid == MOMOWARO_EX:
                score = 400
            elif cid == ZORUA:
                score = 200
            else:
                score = remaining
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # BOSS target: pull weakest opponent bench
    is_opp_bench = len(options) > 0 and all(
        getattr(opt, 'area', None) == AreaType.BENCH
        and getattr(opt, 'playerIndex', None) == opp_idx
        for opt in options
    )
    if is_opp_bench:
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            opt_idx = getattr(opt, 'index', -1)
            poke = opp_state.bench[opt_idx] if opp_state.bench and 0 <= opt_idx < len(opp_state.bench) else None
            remaining = get_remaining_hp(poke)
            card = CARD_DB.get(cid)
            is_ex = (getattr(card, 'ex', False) or getattr(card, 'megaEx', False)
                     or 'ex' in (getattr(card, 'name', '') or '').lower()) if card else False
            if remaining <= 260:
                score = 2000 - remaining
                if is_ex:
                    score += 500
            else:
                score = 1000 - remaining
                if is_ex:
                    score += 200
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # Tool attach: prioritize イイネイヌex
    is_tool = (
        context in (SelectContext.ATTACH_TO,)
        and max_count == 1
        and any(getattr(opt, 'area', None) in (AreaType.BENCH, AreaType.ACTIVE) for opt in options)
        and not any(get_option_card_id(opt, obs) == BASIC_DARK for opt in options)
    )
    if is_tool:
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            area = getattr(opt, 'area', None)
            score = 0
            if cid == IINEEINU_EX:
                score = 1000 if area == AreaType.ACTIVE else 800
            elif cid == MOMOWARO_EX:
                score = 400
            elif cid == ZOROARK:
                score = 200
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # ATTACH_TO / FROM
    if context in (SelectContext.ATTACH_TO, SelectContext.ATTACH_FROM):
        is_choosing_pokemon = any(
            getattr(opt, 'area', None) in (AreaType.BENCH, AreaType.ACTIVE) for opt in options
        )
        if is_choosing_pokemon:
            scored = []
            for i, opt in enumerate(options):
                cid = get_option_card_id(opt, obs)
                opt_idx = getattr(opt, 'index', -1)
                area = getattr(opt, 'area', None)
                poke = None
                if area == AreaType.BENCH and my_state.bench and 0 <= opt_idx < len(my_state.bench):
                    poke = my_state.bench[opt_idx]
                elif area == AreaType.ACTIVE and my_state.active and 0 <= opt_idx < len(my_state.active):
                    poke = my_state.active[opt_idx]
                dark_e = get_dark_energies(poke)
                score = 0
                if cid == IINEEINU_EX:
                    score = 900 - dark_e * 100
                elif cid == MOMOWARO_EX:
                    score = 500 - dark_e * 100
                elif cid == ZOROARK:
                    score = 300
                scored.append((score, i))
            scored.sort(key=lambda x: x[0], reverse=True)
            count = min(max_count, len(scored))
            return [x[1] for x in scored[:count]]

    # SETUP ACTIVE
    if context == SelectContext.SETUP_ACTIVE_POKEMON:
        if not options:
            return []
        for i, opt in enumerate(options):
            if get_option_card_id(opt, obs) == IINEEINU_EX:
                return [i]
        for i, opt in enumerate(options):
            if get_option_card_id(opt, obs) == ZORUA:
                return [i]
        return [0]

    # SETUP BENCH / TO BENCH
    if context in (SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH):
        opp_deck = identify_opponent_deck(obs)
        max_bench = 2 if opp_deck == "ALAKAZAM" else 5
        bench_count = len([p for p in my_state.bench if p is not None])
        if bench_count >= max_bench and min_count == 0:
            return []
        has_momowaro = any(getattr(p, 'id', -1) == MOMOWARO_EX for p in my_state.bench if p)
        is_crustle = (opp_deck == "CRUSTLE")
        scored = []
        has_iineeinu_bench = any(getattr(p, 'id', -1) == IINEEINU_EX for p in my_state.bench if p)
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            score = 0
            if cid == IINEEINU_EX and not has_iineeinu_bench:
                score = 110
            elif cid == IINEEINU_EX:
                score = 90
            elif cid == MOMOWARO_EX and not has_momowaro:
                score = 80
            elif cid == ZORUA and is_crustle:
                score = 70
            elif cid == ZORUA:
                score = 40
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # DISCARD
    if context == SelectContext.DISCARD:
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            if cid in (IINEEINU_EX, MOMOWARO_EX, ZOROARK, ZORUA):
                score = 0
            elif cid == BASIC_DARK:
                score = 40
            elif cid in (SWITCH, NIGHT_STRETCHER):
                score = 70
            else:
                score = 60
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # DECK/LOOKING search
    is_search = (
        (hasattr(obs, 'current') and getattr(obs.current, 'looking', None) is not None)
        or (getattr(obs.select, 'deck', None) is not None)
        or any(getattr(opt, 'area', None) == AreaType.DECK for opt in options)
    )
    if is_search:
        opp_deck = identify_opponent_deck(obs)
        is_crustle = (opp_deck == "CRUSTLE")
        has_iineeinu = any(getattr(p, 'id', -1) == IINEEINU_EX for p in (my_state.bench + (my_state.active or [])) if p)
        has_momowaro = any(getattr(p, 'id', -1) == MOMOWARO_EX for p in my_state.bench if p)
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            score = 0
            if cid == IINEEINU_EX and not has_iineeinu:
                score = 100
            elif cid == MOMOWARO_EX and not has_momowaro:
                score = 95
            elif cid == IINEEINU_EX:
                score = 80
            elif cid == MOMOWARO_EX:
                score = 70
            elif cid == ZOROARK and is_crustle:
                score = 85
            elif cid == ZORUA and is_crustle:
                score = 65
            elif cid == BASIC_DARK:
                score = 40
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, 1)
        count = min(count, max_count, len(scored))
        return [x[1] for x in scored[:count]]

    count = max(min_count, 1)
    count = min(count, max_count, len(options))
    return list(range(count)) if count > 0 else []


def select_yes_no(obs: Observation) -> list[int]:
    options = obs.select.option
    context = obs.select.context
    if context == SelectContext.IS_FIRST:
        for i, opt in enumerate(options):
            if opt.type == OptionType.YES:
                return [i]
    for i, opt in enumerate(options):
        if opt.type == OptionType.YES:
            return [i]
    return [0] if options else []


def agent(obs_dict):
    if obs_dict is None:
        return read_deck_csv()
    if hasattr(obs_dict, 'select'):
        obs = obs_dict
    else:
        if getattr(obs_dict, 'get', None) is None or obs_dict.get('select') is None:
            return read_deck_csv()
        try:
            obs = to_observation_class(obs_dict)
        except Exception:
            return [0]
    if getattr(obs, 'select', None) is None or getattr(obs.select, 'option', None) is None:
        return read_deck_csv()
    try:
        _update_opp_memory(obs)
    except Exception:
        pass
    if len(obs.select.option) == 0:
        return []
    if len(obs.select.option) == 1 and obs.select.maxCount == 1:
        return [0]
    sel_type = obs.select.type
    if sel_type == SelectType.MAIN:
        if MCTS_AVAILABLE:
            try:
                mcts_action = run_mcts(obs, my_deck=read_deck_csv(), time_limit_sec=0.20)
                if mcts_action is not None:
                    return mcts_action
            except Exception:
                pass
        return select_main_action(obs)
    if sel_type == SelectType.YES_NO:
        return select_yes_no(obs)
    if sel_type == SelectType.CARD:
        return select_card(obs)
    count = min(obs.select.maxCount, len(obs.select.option))
    return list(range(count)) if count > 0 else []
