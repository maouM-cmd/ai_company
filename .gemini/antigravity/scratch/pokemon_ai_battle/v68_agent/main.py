"""
V67: Mega Froslass ex × Mega Starmie ex 水デッキ (V66シミュレーション分析に基づく改善)
V66シミュレーション結果 (N=20): 42.9% (V65: 45.8%)
  フーディン 42.1%, ルカリオ 65.0%, イワパレス 35.0%, ユキノオー 15.0%, ハラバリー 65.0%, カビゴン 35.0%

V66敗因分析:
- 全敗戦の主因: BENCH_OUT（ベンチ切れ）
- BUDDY_BUDDY_POFFIN が優先度4位で出遅れ → 序盤ベンチ0のまま KO される
- ユキノオー/カビゴンに turn 4-6 で即負け（ベンチ補充できていない）

V67改善内容:
1. BUDDY_BUDDY_POFFIN をデフォルト優先度2位に引き上げ (MEGA_SIGNAL の次)
2. ベンチ=0 + 種ポケモン時の緊急ベンチ補充モード追加
3. デッキ: Ultra Ball 0→1枚 復活, Harlequin 2→1枚 (-1)
4. ABOMASNOW 専用優先度修正 (BUDDY_BUDDY_POFFIN 2位, 不要 Ultra Ball 削除)
5. SNORLAX (カビゴン) 専用優先度追加 (BUDDY_BUDDY_POFFIN 高優先)
6. サーチ時スコア: ベンチ0時 BUDDY_BUDDY_POFFIN スコア大幅UP
"""
from cg.api import (
    Observation, SelectContext, SelectType, OptionType, AreaType,
    to_observation_class, all_card_data
)
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

# --- Card IDs ---
SNORUNT          = 860   # HP70  Basic  進化前(Froslass)
MEGA_FROSLASS_EX = 861   # HP310 Stage1 水 メインアタッカー
STARYU           = 1030  # HP70  Basic  進化前(Starmie)
MEGA_STARMIE_EX  = 1031  # HP330 Stage1 水 サブアタッカー

WATER_ENERGY    = 3     # Basic {W}
MIST_ENERGY     = 11    # Special Energy
LEGACY_ENERGY   = 12    # Special Energy
IGNITION_ENERGY = 17    # Special Energy (1枚のみ採用)

# ドラパルトex進化ライン
DREEPY       = 119  # Basic
DRAKLOAK     = 120  # Stage1
DRAGAPULT_EX = 121  # Stage2 ex (Phantom Dive: ベンチに6個ダメカン分散)

BUDDY_BUDDY_POFFIN  = 1086  # Item: Basicポケモン2枚サーチ ★最重要
NIGHT_STRETCHER     = 1097  # Item: 山・捨て山からポケモン回収
ENERGY_SEARCH       = 1119  # Item: エネルギーサーチ
ULTRA_BALL          = 1121  # Item: ポケモンサーチ (V67: 1枚復活)
POKEGEAR            = 1122  # Item: サポーターサーチ
MEGA_SIGNAL         = 1145  # Item: メガポケモン展開
HEROS_CAPE          = 1159  # Tool: HP+50
BOSS_ORDERS         = 1182  # Supporter: 相手ベンチ指定 (2枚)
SALVATORE           = 1189  # Supporter: ドロー系
HARLEQUIN           = 1223  # Supporter (V67: 2→1枚)
HILDA               = 1225  # Supporter: ドロー/サーチ
LILLIES             = 1227  # Supporter: 山札切れ防止
WALLYS_COMPASSION   = 1229  # Supporter: ドロー系

MY_POKEMON = {SNORUNT, MEGA_FROSLASS_EX, STARYU, MEGA_STARMIE_EX}
SEED_POKEMON = {SNORUNT, STARYU}  # 種ポケモン

HP_TABLE = {
    SNORUNT:          70,
    MEGA_FROSLASS_EX: 310,
    STARYU:           70,
    MEGA_STARMIE_EX:  330,
}

_opp_deck_cache: str = "UNKNOWN"
_opp_deck_identified: bool = False


def identify_opponent_deck(obs: Observation) -> str:
    global _opp_deck_cache, _opp_deck_identified
    if _opp_deck_identified:
        return _opp_deck_cache
    state = getattr(obs, 'current', None)
    if not state:
        return "UNKNOWN"
    opp_idx = 1 - state.yourIndex
    opp_state = state.players[opp_idx]
    seen = set()
    for p in (opp_state.active or []) + (opp_state.bench or []):
        if p:
            seen.add(getattr(p, 'id', -1))
    if any(cid in seen for cid in [723, 722]):
        result = "ABOMASNOW"
    elif any(cid in seen for cid in [678, 677]):
        result = "LUCARIO"
    elif any(cid in seen for cid in [743, 742, 741]):
        result = "ALAKAZAM"
    elif any(cid in seen for cid in [345, 344, 532]):
        result = "CRUSTLE"
    elif any(cid in seen for cid in [1072, 878, 879]):
        result = "SNORLAX"
    elif any(cid in seen for cid in [DRAGAPULT_EX, DRAKLOAK, DREEPY]):
        result = "DRAGAPULT"
    elif any(cid in seen for cid in [666]):
        result = "ACERBURN"
    else:
        return "UNKNOWN"
    _opp_deck_cache = result
    _opp_deck_identified = True
    return result


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
        state = obs.current
        my_idx = state.yourIndex
        player_idx = getattr(opt, 'playerIndex', my_idx)
        p_state = state.players[player_idx]
        area = getattr(opt, 'area', None)
        if area == AreaType.HAND and p_state.hand and 0 <= opt_idx < len(p_state.hand):
            return getattr(p_state.hand[opt_idx], 'id', -1)
        if area == AreaType.LOOKING and state.looking and 0 <= opt_idx < len(state.looking):
            return getattr(state.looking[opt_idx], 'id', -1)
        if area == AreaType.ACTIVE and p_state.active and 0 <= opt_idx < len(p_state.active):
            poke = p_state.active[opt_idx]
            return getattr(poke, 'id', -1) if poke else -1
        if area == AreaType.BENCH and p_state.bench and 0 <= opt_idx < len(p_state.bench):
            poke = p_state.bench[opt_idx]
            return getattr(poke, 'id', -1) if poke else -1
        if area == AreaType.DISCARD and p_state.discard and 0 <= opt_idx < len(p_state.discard):
            return getattr(p_state.discard[opt_idx], 'id', -1)
        if state.looking and 0 <= opt_idx < len(state.looking):
            return getattr(state.looking[opt_idx], 'id', -1)
        if p_state.hand and 0 <= opt_idx < len(p_state.hand):
            return getattr(p_state.hand[opt_idx], 'id', -1)
    except Exception:
        pass
    return -1


def get_energies(poke) -> int:
    try:
        e = getattr(poke, 'energies', [])
        return len(e) if e else 0
    except Exception:
        return 0


def get_remaining_hp(poke) -> int:
    if not poke:
        return 9999
    cid = getattr(poke, 'id', -1)
    card = CARD_DB.get(cid)
    hp = getattr(card, 'hp', HP_TABLE.get(cid, 200)) if card else HP_TABLE.get(cid, 200)
    dmg = getattr(poke, 'damage', 0)
    return max(0, hp - dmg)


def read_deck_csv() -> list[int]:
    global _opp_deck_cache, _opp_deck_identified
    _opp_deck_cache = "UNKNOWN"
    _opp_deck_identified = False
    return (
        [WATER_ENERGY]       * 9  +  # 9
        [MIST_ENERGY]        * 1  +  # 10
        [LEGACY_ENERGY]      * 1  +  # 11
        [IGNITION_ENERGY]    * 1  +  # 12
        [SNORUNT]            * 4  +  # 16
        [MEGA_FROSLASS_EX]   * 3  +  # 19
        [STARYU]             * 4  +  # 23
        [MEGA_STARMIE_EX]    * 3  +  # 26
        [BUDDY_BUDDY_POFFIN] * 4  +  # 30
        [ENERGY_SEARCH]      * 4  +  # 34
        [MEGA_SIGNAL]        * 4  +  # 38
        [SALVATORE]          * 4  +  # 42
        [LILLIES]            * 4  +  # 46
        [WALLYS_COMPASSION]  * 3  +  # 49
        [POKEGEAR]           * 3  +  # 52
        [NIGHT_STRETCHER]    * 2  +  # 54
        [BOSS_ORDERS]        * 2  +  # 56
        [HILDA]              * 2  +  # 58
        [ULTRA_BALL]         * 1  +  # 59 (V67: 0→1枚復活)
        [HARLEQUIN]          * 1     # 60 (V67: 2→1枚)
    )


def select_main_action(obs: Observation) -> list[int]:
    options = obs.select.option
    evolves, attacks, attaches, plays, retreats = [], [], [], [], []
    end_idx = None

    for i, opt in enumerate(options):
        try:
            t = opt.type
            if t == OptionType.EVOLVE:    evolves.append(i)
            elif t == OptionType.ATTACK:  attacks.append(i)
            elif t == OptionType.ATTACH:  attaches.append(i)
            elif t == OptionType.PLAY:    plays.append(i)
            elif t == OptionType.RETREAT: retreats.append(i)
            elif t == OptionType.END:     end_idx = i
            elif t == OptionType.CARD:
                cid = get_option_card_id(opt, obs)
                if cid in (WATER_ENERGY, MIST_ENERGY, LEGACY_ENERGY, IGNITION_ENERGY):
                    attaches.append(i)
                else:
                    plays.append(i)
        except Exception:
            pass

    state = obs.current
    my_idx = state.yourIndex
    my_state = state.players[my_idx]
    opp_idx = 1 - my_idx
    opp_state = state.players[opp_idx]

    active = my_state.active[0] if my_state.active else None
    active_id = getattr(active, 'id', -1) if active else -1
    active_dmg = getattr(active, 'damage', 0) if active else 0
    active_hp = HP_TABLE.get(active_id, 200)
    active_remaining = active_hp - active_dmg
    active_energy = get_energies(active)

    opp_deck = identify_opponent_deck(obs)

    # ベンチ上限: アラカザム・ドラパルト対面は2（ベンチダメージ分散対策）
    max_bench = 2 if opp_deck in ("ALAKAZAM", "DRAGAPULT") else 3
    bench_count = len([p for p in my_state.bench if p is not None])

    # 1. 進化最優先
    if evolves:
        active_evolves = [i for i in evolves
                         if getattr(options[i], 'inPlayArea', None) == AreaType.ACTIVE]
        bench_evolves  = [i for i in evolves
                         if getattr(options[i], 'inPlayArea', None) == AreaType.BENCH]
        if active_evolves:
            return [active_evolves[0]]
        if bench_evolves:
            return [bench_evolves[0]]
        return [evolves[0]]

    # 2. トレーナー使用
    if plays:
        allowed = []
        for idx in plays:
            cid = get_option_card_id(options[idx], obs)
            if cid in MY_POKEMON:
                if bench_count < max_bench:
                    allowed.append(idx)
            else:
                allowed.append(idx)

        # ベンチ展開優先（SnoruntとStaryuを均等に）
        if bench_count < max_bench:
            bench_ids = [getattr(p, 'id', -1) for p in (my_state.bench or []) if p]
            snorunt_cnt = bench_ids.count(SNORUNT) + bench_ids.count(MEGA_FROSLASS_EX)
            staryu_cnt  = bench_ids.count(STARYU)  + bench_ids.count(MEGA_STARMIE_EX)
            if snorunt_cnt <= staryu_cnt:
                for idx in allowed:
                    if get_option_card_id(options[idx], obs) == SNORUNT:
                        return [idx]
            if staryu_cnt <= snorunt_cnt:
                for idx in allowed:
                    if get_option_card_id(options[idx], obs) == STARYU:
                        return [idx]
            for cid_pref in (SNORUNT, STARYU, MEGA_FROSLASS_EX, MEGA_STARMIE_EX):
                for idx in allowed:
                    if get_option_card_id(options[idx], obs) == cid_pref:
                        return [idx]

        # === V67追加: 緊急ベンチ補充モード ===
        # bench=0 かつ種ポケモンがアクティブ → BUDDY_BUDDY_POFFIN を最優先でベンチ補充
        if bench_count == 0 and active_id in SEED_POKEMON:
            emergency_prio = [
                BUDDY_BUDDY_POFFIN, NIGHT_STRETCHER, MEGA_SIGNAL, ULTRA_BALL,
                POKEGEAR, SALVATORE, HILDA, WALLYS_COMPASSION,
                ENERGY_SEARCH, HARLEQUIN, LILLIES, BOSS_ORDERS
            ]
            for cid in emergency_prio:
                for idx in allowed:
                    if get_option_card_id(options[idx], obs) == cid:
                        return [idx]

        opp_active = opp_state.active[0] if opp_state.active else None
        opp_active_rem = get_remaining_hp(opp_active)

        # 通常のBoss判定（HPが低いベンチポケモンを前に引きずり出す）
        use_boss = (
            active_energy >= 1
            and any(get_remaining_hp(p) < opp_active_rem
                    for p in (opp_state.bench or []) if p)
        )

        # ルカリオ対策: Rioluがベンチに見えたらBoss最優先でKO（進化阻止）
        if opp_deck == "LUCARIO" and active_energy >= 1:
            riolu_on_bench = any(
                getattr(p, 'id', -1) == 677
                for p in (opp_state.bench or []) if p
            )
            if riolu_on_bench:
                use_boss = True

        # === V67: 対面別優先度 (BUDDY_BUDDY_POFFINを各優先度で2位に) ===
        if opp_deck == "LUCARIO":
            # ルカリオ対面: Boss最優先→高速展開でMegaを立てて攻撃
            prio = [BOSS_ORDERS, MEGA_SIGNAL, BUDDY_BUDDY_POFFIN, ENERGY_SEARCH,
                    POKEGEAR, NIGHT_STRETCHER, SALVATORE, HILDA,
                    WALLYS_COMPASSION, ULTRA_BALL, HARLEQUIN, LILLIES]
        elif opp_deck == "ACERBURN":
            # エースバーン対面: 高速展開・攻撃優先
            prio = [MEGA_SIGNAL, BUDDY_BUDDY_POFFIN, ENERGY_SEARCH, POKEGEAR,
                    SALVATORE, HILDA, WALLYS_COMPASSION,
                    BOSS_ORDERS, ULTRA_BALL, NIGHT_STRETCHER, HARLEQUIN, LILLIES]
        elif opp_deck == "ABOMASNOW":
            # ユキノオー対面: ベンチ補充最優先 (V66の Ultra Ball 参照を修正)
            prio = [MEGA_SIGNAL, BUDDY_BUDDY_POFFIN, POKEGEAR, ENERGY_SEARCH,
                    ULTRA_BALL, NIGHT_STRETCHER, SALVATORE, HILDA,
                    WALLYS_COMPASSION, HARLEQUIN, LILLIES, BOSS_ORDERS]
        elif opp_deck == "SNORLAX":
            # カビゴン対面: ベンチ補充 + Lillies (ミル対策)
            prio = [MEGA_SIGNAL, BUDDY_BUDDY_POFFIN, POKEGEAR, ENERGY_SEARCH,
                    ULTRA_BALL, NIGHT_STRETCHER, SALVATORE, HILDA,
                    WALLYS_COMPASSION, HARLEQUIN, BOSS_ORDERS, LILLIES]
        elif active_remaining < active_hp * 0.4:
            prio = [NIGHT_STRETCHER, ULTRA_BALL, MEGA_SIGNAL, BUDDY_BUDDY_POFFIN,
                    ENERGY_SEARCH, POKEGEAR,
                    SALVATORE, HILDA, WALLYS_COMPASSION, HARLEQUIN,
                    LILLIES, BOSS_ORDERS]
        else:
            # デフォルト: BUDDY_BUDDY_POFFIN を2位に (V66の4位から昇格)
            prio = [MEGA_SIGNAL, BUDDY_BUDDY_POFFIN, ENERGY_SEARCH, POKEGEAR,
                    ULTRA_BALL, SALVATORE, HILDA, WALLYS_COMPASSION,
                    HARLEQUIN, LILLIES, BOSS_ORDERS, NIGHT_STRETCHER]

        if use_boss and opp_deck != "LUCARIO":
            if BOSS_ORDERS in prio:
                prio.remove(BOSS_ORDERS)
            prio.insert(0, BOSS_ORDERS)

        # デッキ残少時: Lilliesを最優先（デッキ切れ防止）
        if my_state.deckCount < 15:
            if LILLIES in prio:
                prio.remove(LILLIES)
            prio.insert(0, LILLIES)

        for cid in prio:
            for idx in allowed:
                if get_option_card_id(options[idx], obs) == cid:
                    return [idx]

    # 3. 退場優先: 種ポケモンがアクティブ + Megaがベンチにいる場合
    if retreats and active_id in (SNORUNT, STARYU):
        for poke in (my_state.bench or []):
            if poke and getattr(poke, 'id', -1) in (MEGA_FROSLASS_EX, MEGA_STARMIE_EX):
                return [retreats[0]]

    # 4. エネルギー付け（アクティブ優先）
    if attaches:
        # ユキノオー対面: アバランチハンマー(水エネ×100)対策でエネ2枚以上はスキップ
        if opp_deck == "ABOMASNOW" and active_energy >= 2:
            pass
        else:
            return [attaches[0]]

    # 5. 攻撃
    if attacks:
        return [attacks[-1]]

    if end_idx is not None:
        return [end_idx]
    if retreats:
        return [retreats[0]]
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

    if context == SelectContext.SETUP_ACTIVE_POKEMON:
        for cid_pref in (SNORUNT, STARYU):
            for i, opt in enumerate(options):
                if get_option_card_id(opt, obs) == cid_pref:
                    return [i]
        return [0] if options else []

    if context in (SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH):
        opp_deck = identify_opponent_deck(obs)
        max_bench = 2 if opp_deck in ("ALAKAZAM", "DRAGAPULT") else 3
        bench_count = len([p for p in my_state.bench if p])
        if bench_count >= max_bench and min_count == 0:
            return []
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            if cid == SNORUNT:            score = 100
            elif cid == STARYU:           score = 90
            elif cid == MEGA_FROSLASS_EX: score = 60
            elif cid == MEGA_STARMIE_EX:  score = 50
            else:                         score = 0
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    is_opp_bench = (len(options) > 0 and all(
        getattr(opt, 'area', None) == AreaType.BENCH
        and getattr(opt, 'playerIndex', None) == opp_idx
        for opt in options
    ))
    if is_opp_bench:
        opp_deck = identify_opponent_deck(obs)
        scored = []
        for i, opt in enumerate(options):
            opt_idx = getattr(opt, 'index', -1)
            poke = (opp_state.bench[opt_idx]
                    if opp_state.bench and 0 <= opt_idx < len(opp_state.bench) else None)
            cid = getattr(poke, 'id', -1) if poke else -1
            rem = get_remaining_hp(poke)
            # ルカリオ対面: Rioluを最優先で引きずり出す
            if opp_deck == "LUCARIO" and cid == 677:
                score = -1  # 最小値=最優先
            else:
                score = rem
            scored.append((score, i))
        scored.sort(key=lambda x: x[0])
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    is_my_bench = (len(options) > 0 and all(
        getattr(opt, 'area', None) == AreaType.BENCH
        and getattr(opt, 'playerIndex', my_idx) == my_idx
        for opt in options
    ))
    if is_my_bench:
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            opt_idx = getattr(opt, 'index', -1)
            poke = (my_state.bench[opt_idx]
                    if my_state.bench and 0 <= opt_idx < len(my_state.bench) else None)
            if cid == MEGA_FROSLASS_EX:  score = 1000 + get_energies(poke) * 100
            elif cid == MEGA_STARMIE_EX: score = 900  + get_energies(poke) * 100
            elif cid == SNORUNT:         score = 300
            elif cid == STARYU:          score = 290
            else:                        score = get_remaining_hp(poke)
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    if context == SelectContext.DISCARD:
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            if cid in MY_POKEMON:                                     score = 0
            elif cid in (WATER_ENERGY, MIST_ENERGY, LEGACY_ENERGY):  score = 30
            elif cid == IGNITION_ENERGY:                              score = 40
            else:                                                     score = 70
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    is_search = (
        getattr(obs.current, 'looking', None) is not None
        or any(getattr(opt, 'area', None) == AreaType.DECK for opt in options)
    )
    if is_search:
        opp_deck = identify_opponent_deck(obs)
        bench_ids = [getattr(p, 'id', -1) for p in (my_state.bench or []) if p]
        active_id_cur = getattr(my_state.active[0], 'id', -1) if my_state.active else -1

        has_froslass = MEGA_FROSLASS_EX in bench_ids or active_id_cur == MEGA_FROSLASS_EX
        has_starmie  = MEGA_STARMIE_EX  in bench_ids or active_id_cur == MEGA_STARMIE_EX
        has_snorunt  = SNORUNT in bench_ids or active_id_cur == SNORUNT
        has_staryu   = STARYU  in bench_ids or active_id_cur == STARYU

        # V67: ベンチ0 + 種ポケモンがアクティブの場合、ベンチ補充カードを大幅UP
        bench_count_now = len([p for p in (my_state.bench or []) if p])
        bench_emergency = (bench_count_now == 0 and active_id_cur in SEED_POKEMON)

        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            if cid == MEGA_FROSLASS_EX:
                score = 1000 if not has_froslass else 200
            elif cid == MEGA_STARMIE_EX:
                score = 900  if not has_starmie  else 190
            elif cid == SNORUNT:
                score = 700  if not has_snorunt  else 150
            elif cid == STARYU:
                score = 650  if not has_staryu   else 140
            elif cid == BUDDY_BUDDY_POFFIN:
                # V67: ベンチ緊急時は最高スコア
                score = 980 if bench_emergency else 480
            elif cid == NIGHT_STRETCHER:
                score = 950 if bench_emergency else 340
            elif cid == WATER_ENERGY:       score = 500
            elif cid == MIST_ENERGY:        score = 490
            elif cid == LEGACY_ENERGY:      score = 470
            elif cid == IGNITION_ENERGY:    score = 450
            elif cid == MEGA_SIGNAL:        score = 420
            elif cid == ULTRA_BALL:         score = 400
            elif cid == ENERGY_SEARCH:      score = 380
            # ルカリオ対面ではBoss Ordersの価値を上げる
            elif cid == BOSS_ORDERS:
                score = 430 if opp_deck == "LUCARIO" else 300
            else:                           score = 100
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    count = max(min_count, min(max_count, len(options)))
    return list(range(count)) if count > 0 else []


def agent(obs_dict):
    global _opp_deck_cache, _opp_deck_identified
    if obs_dict is None:
        _opp_deck_cache = "UNKNOWN"
        _opp_deck_identified = False
        return read_deck_csv()
    try:
        if hasattr(obs_dict, 'select'):
            obs = obs_dict
        else:
            if getattr(obs_dict, 'get', None) is None or obs_dict.get('select') is None:
                return read_deck_csv()
            obs = to_observation_class(obs_dict)
        if getattr(obs, 'select', None) is None or getattr(obs.select, 'option', None) is None:
            return read_deck_csv()
        if len(obs.select.option) == 0:
            return []
        select = obs.select
        if select.type == SelectType.CARD:
            return select_card(obs)
        elif select.type == SelectType.MAIN:
            return select_main_action(obs)
        elif select.type == SelectType.YES_NO:
            return [0]
        else:
            count = min(select.maxCount, len(select.option))
            return list(range(count)) if count > 0 else []
    except Exception:
        return []
