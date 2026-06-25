"""
V61: エースバーン × Mega Starmie ex 水デッキ (V60改)
- PLAYフォールバック修正: カードID取れなくてもPLAYを選ぶ
- Staryu展開優先: ベンチ空時はStaryu/StarmieExを最優先で出す
- EVOLVE最優先: StarmieEx進化を最初に処理
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
CINDERACE       = 666   # HP160 Stage2 水 メインアタッカー
STARYU          = 1030  # HP70  Basic  進化前
MEGA_STARMIE_EX = 1031  # HP330 Stage1 水 サブアタッカー

WATER_ENERGY    = 3     # Basic {W}
IGNITION_ENERGY = 17    # Special Energy (Cinderace専用)

BUDDY_BUDDY_POFFIN  = 1086  # Item: Basicポケモン2枚サーチ
NIGHT_STRETCHER     = 1097  # Item: 山・捨て山からポケモン回収
CRUSHING_HAMMER     = 1120  # Item: 相手エネルギー破壊
ULTRA_BALL          = 1121  # Item: ポケモンサーチ
POKEGEAR            = 1122  # Item: サポーターサーチ
MEGA_SIGNAL         = 1145  # Item: メガポケモン展開
HEROS_CAPE          = 1159  # Tool: HP+50
BOSS_ORDERS         = 1182  # Supporter: 相手ベンチ指定
SALVATORE           = 1189  # Supporter: ドロー系
HARLEQUIN           = 1223  # Supporter
HILDA               = 1225  # Supporter: ドロー/サーチ
LILLIES             = 1227  # Supporter: 山札切れ防止
WALLYS_COMPASSION   = 1229  # Supporter: ドロー系

MY_POKEMON = {CINDERACE, STARYU, MEGA_STARMIE_EX}

HP_TABLE = {
    CINDERACE:       160,
    STARYU:           70,
    MEGA_STARMIE_EX: 330,
}

# 相手デッキ識別キャッシュ（MCTSコール高速化のため初回のみ計算）
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
    else:
        return "UNKNOWN"  # まだ識別できない（キャッシュしない）
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
        [IGNITION_ENERGY]    * 4  +  # 13
        [CINDERACE]          * 4  +  # 17
        [STARYU]             * 3  +  # 20
        [MEGA_STARMIE_EX]    * 3  +  # 23
        [BUDDY_BUDDY_POFFIN] * 4  +  # 27
        [NIGHT_STRETCHER]    * 2  +  # 29
        [CRUSHING_HAMMER]    * 4  +  # 33
        [ULTRA_BALL]         * 1  +  # 34
        [POKEGEAR]           * 4  +  # 38
        [MEGA_SIGNAL]        * 4  +  # 42
        [HEROS_CAPE]         * 1  +  # 43
        [BOSS_ORDERS]        * 1  +  # 44
        [SALVATORE]          * 4  +  # 48
        [HARLEQUIN]          * 2  +  # 50
        [HILDA]              * 2  +  # 52
        [LILLIES]            * 4  +  # 56
        [WALLYS_COMPASSION]  * 4     # 60
    )


def select_main_action(obs: Observation) -> list[int]:
    options = obs.select.option
    evolves, attacks, attaches, plays, retreats = [], [], [], [], []
    end_idx = None

    for i, opt in enumerate(options):
        try:
            t = opt.type
            if t == OptionType.EVOLVE:   evolves.append(i)
            elif t == OptionType.ATTACK: attacks.append(i)
            elif t == OptionType.ATTACH: attaches.append(i)
            elif t == OptionType.PLAY:   plays.append(i)
            elif t == OptionType.RETREAT: retreats.append(i)
            elif t == OptionType.END:    end_idx = i
            elif t == OptionType.CARD:
                cid = get_option_card_id(opt, obs)
                if cid in (WATER_ENERGY, IGNITION_ENERGY):
                    attaches.append(i)  # エネルギー付けとして処理
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
    # フーディン対策：ベンチを2匹以下に制限
    max_bench = 2 if opp_deck == "ALAKAZAM" else 3
    bench_count = len([p for p in my_state.bench if p is not None])

    # 1. 進化：Staryu → Mega Starmie ex (最優先)
    if evolves:
        for idx in evolves:
            if get_option_card_id(options[idx], obs) == MEGA_STARMIE_EX:
                return [idx]
        return [evolves[0]]

    # 2. Cinderaceのエネ0時: Ignition Energy最優先 (PLAY前に付ける)
    if attaches and active_id == CINDERACE and active_energy == 0:
        for idx in attaches:
            if get_option_card_id(options[idx], obs) == IGNITION_ENERGY:
                return [idx]
        return [attaches[0]]

    # 3. トレーナー使用
    if plays:
        allowed = []
        for idx in plays:
            cid = get_option_card_id(options[idx], obs)
            if cid in MY_POKEMON:
                if bench_count < max_bench:
                    allowed.append(idx)
            else:
                allowed.append(idx)

        # ベンチ展開優先（Staryuを優先してMega Starmie exの進化ルートを確保）
        if bench_count < max_bench:
            bench_ids = [getattr(p, 'id', -1) for p in (my_state.bench or []) if p]
            staryu_count = bench_ids.count(STARYU)
            starmie_count = bench_ids.count(MEGA_STARMIE_EX)
            # Staryuが2枚未満 かつ StarmieExの進化スロット不足 → Staryu追加
            if staryu_count + starmie_count < 2:
                for idx in allowed:
                    if get_option_card_id(options[idx], obs) == STARYU:
                        return [idx]
            # Cinderace展開（アクティブにいない場合）
            for cid_pref in (CINDERACE, STARYU):
                for idx in allowed:
                    if get_option_card_id(options[idx], obs) == cid_pref:
                        return [idx]

        opp_active = opp_state.active[0] if opp_state.active else None
        opp_active_rem = get_remaining_hp(opp_active)
        use_boss = (
            active_energy >= 1
            and any(get_remaining_hp(p) < opp_active_rem
                    for p in (opp_state.bench or []) if p)
        )

        # ユキノオー/ルカリオ対面：クラッシュハンマーとMegaシグナルを最優先
        if opp_deck in ("ABOMASNOW", "LUCARIO"):
            prio = [MEGA_SIGNAL, CRUSHING_HAMMER, POKEGEAR, BUDDY_BUDDY_POFFIN,
                    ULTRA_BALL, NIGHT_STRETCHER, SALVATORE, HILDA,
                    WALLYS_COMPASSION, HARLEQUIN, LILLIES, BOSS_ORDERS]
        elif active_remaining < active_hp * 0.4:
            prio = [NIGHT_STRETCHER, ULTRA_BALL, MEGA_SIGNAL,
                    BUDDY_BUDDY_POFFIN, POKEGEAR,
                    SALVATORE, HILDA, WALLYS_COMPASSION, HARLEQUIN,
                    LILLIES, BOSS_ORDERS, CRUSHING_HAMMER]
        else:
            prio = [MEGA_SIGNAL, POKEGEAR, BUDDY_BUDDY_POFFIN,
                    ULTRA_BALL, SALVATORE, HILDA, WALLYS_COMPASSION,
                    HARLEQUIN, LILLIES, BOSS_ORDERS,
                    CRUSHING_HAMMER, NIGHT_STRETCHER]

        if use_boss:
            if BOSS_ORDERS in prio:
                prio.remove(BOSS_ORDERS)
            prio.insert(0, BOSS_ORDERS)

        if my_state.deckCount > 5:
            for d in (LILLIES, SALVATORE):
                if d in prio:
                    prio.remove(d)
                    prio.insert(1, d)

        for cid in prio:
            for idx in allowed:
                if get_option_card_id(options[idx], obs) == cid:
                    return [idx]

        # フォールバック: カードID取得失敗時も何か使う（攻撃より優先）
        if allowed:
            return [allowed[0]]
        if plays:
            return [plays[0]]

    # 4. エネルギー付け
    if attaches:
        # アクティブがエネ0のとき: Ignition Energy優先 (Cinderace=Turbo Flare即撃ち, StarmieEx=Nebula Beam解禁)
        if active_id in (CINDERACE, MEGA_STARMIE_EX) and active_energy == 0:
            for idx in attaches:
                if get_option_card_id(options[idx], obs) == IGNITION_ENERGY:
                    return [idx]

        # アクティブへのATTACHオプションを選択
        for idx in attaches:
            if getattr(options[idx], 'inPlayArea', None) == AreaType.ACTIVE:
                return [idx]
        return [attaches[0]]

    # 4.5 退場 (ユキノオー/ルカリオ対面のみ: Starmie exに3エネ溜まったらCinderace退場)
    if retreats and active_id == CINDERACE and opp_deck in ("ABOMASNOW", "LUCARIO"):
        for poke in (my_state.bench or []):
            if poke and getattr(poke, 'id', -1) == MEGA_STARMIE_EX:
                if get_energies(poke) >= 3:
                    return [retreats[0]]

    # 5. 攻撃
    if attacks:
        # Staryu がアクティブ + エネ1以下 → 攻撃はせずENDで様子見
        if active_id == STARYU and active_energy <= 1 and end_idx is not None:
            return [end_idx]
        # Mega Starmie ex: Ignition Energy付き → Nebula Beam (210dmg)
        if active_id == MEGA_STARMIE_EX:
            has_ignition = any(
                getattr(e, 'id', -1) == IGNITION_ENERGY
                for e in (getattr(active, 'energies', []) or [])
            )
            if has_ignition and len(attacks) > 1:
                return [attacks[-1]]  # Nebula Beam (●●● 210dmg)
            return [attacks[0]]  # Jetting Blow ({W} or ●)
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

    # セットアップ：バトル場（Explosiveness特性でCinderaceを優先、なければStaryu）
    if context == SelectContext.SETUP_ACTIVE_POKEMON:
        for i, opt in enumerate(options):
            if get_option_card_id(opt, obs) == CINDERACE:
                return [i]
        for i, opt in enumerate(options):
            if get_option_card_id(opt, obs) == STARYU:
                return [i]
        return [0] if options else []

    # セットアップ／ベンチ展開
    if context in (SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH):
        opp_deck = identify_opponent_deck(obs)
        max_bench = 2 if opp_deck == "ALAKAZAM" else 3
        bench_count = len([p for p in my_state.bench if p])
        if bench_count >= max_bench and min_count == 0:
            return []
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            if cid == CINDERACE:         score = 100
            elif cid == STARYU:          score = 80
            elif cid == MEGA_STARMIE_EX: score = 60
            else:                        score = 0
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # 相手ベンチ選択（ボスの指令など）
    is_opp_bench = (len(options) > 0 and all(
        getattr(opt, 'area', None) == AreaType.BENCH
        and getattr(opt, 'playerIndex', None) == opp_idx
        for opt in options
    ))
    if is_opp_bench:
        scored = []
        for i, opt in enumerate(options):
            opt_idx = getattr(opt, 'index', -1)
            poke = (opp_state.bench[opt_idx]
                    if opp_state.bench and 0 <= opt_idx < len(opp_state.bench) else None)
            rem = get_remaining_hp(poke)
            scored.append((rem, i))
        scored.sort(key=lambda x: x[0])
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # 自分ベンチ選択
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
            if cid == MEGA_STARMIE_EX: score = 1000 + get_energies(poke) * 100
            elif cid == CINDERACE:     score = 800 + get_energies(poke) * 100
            elif cid == STARYU:        score = 300
            else:                      score = get_remaining_hp(poke)
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # 捨て選択
    if context == SelectContext.DISCARD:
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            if cid in MY_POKEMON:                    score = 0
            elif cid in (WATER_ENERGY, IGNITION_ENERGY): score = 50
            else:                                    score = 70
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # デッキサーチ・LOOKING系
    is_search = (
        getattr(obs.current, 'looking', None) is not None
        or any(getattr(opt, 'area', None) == AreaType.DECK for opt in options)
    )
    if is_search:
        opp_deck = identify_opponent_deck(obs)
        has_cinderace = any(getattr(p, 'id', -1) == CINDERACE
                            for p in (my_state.bench or []) + (my_state.active or []) if p)
        has_starmie = any(getattr(p, 'id', -1) == MEGA_STARMIE_EX
                          for p in (my_state.bench or []) + (my_state.active or []) if p)
        has_staryu = any(getattr(p, 'id', -1) == STARYU
                         for p in (my_state.bench or []) + (my_state.active or []) if p)
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            # ユキノオー/ルカリオ対面：Starmieex優先
            if opp_deck in ("ABOMASNOW", "LUCARIO"):
                if cid == MEGA_STARMIE_EX:                   score = 120
                elif cid == STARYU and not has_staryu:        score = 110
                elif cid == IGNITION_ENERGY:                  score = 90
                elif cid == WATER_ENERGY:                     score = 70
                elif cid == CINDERACE and not has_cinderace:  score = 60
                elif cid == CINDERACE:                        score = 40
                else:                                         score = 20
            else:
                if cid == CINDERACE and not has_cinderace:    score = 110
                elif cid == CINDERACE:                        score = 90
                elif cid == MEGA_STARMIE_EX:                  score = 85
                elif cid == STARYU and not has_starmie:       score = 80
                elif cid == IGNITION_ENERGY:                  score = 60
                elif cid == WATER_ENERGY:                     score = 40
                else:                                         score = 20
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, 1)
        count = min(count, max_count, len(scored))
        return [x[1] for x in scored[:count]]

    # エネルギー/ツール付け先選択
    if context in (SelectContext.ATTACH_TO, SelectContext.ATTACH_FROM):
        opp_deck_at = identify_opponent_deck(obs)
        is_choosing_pokemon = any(
            getattr(opt, 'area', None) in (AreaType.BENCH, AreaType.ACTIVE)
            for opt in options
        )
        if is_choosing_pokemon:
            scored = []
            for i, opt in enumerate(options):
                cid = get_option_card_id(opt, obs)
                area = getattr(opt, 'area', None)
                opt_idx = getattr(opt, 'index', -1)
                poke = None
                if area == AreaType.ACTIVE and my_state.active:
                    poke = my_state.active[opt_idx] if 0 <= opt_idx < len(my_state.active) else None
                elif area == AreaType.BENCH and my_state.bench:
                    poke = my_state.bench[opt_idx] if 0 <= opt_idx < len(my_state.bench) else None
                e = get_energies(poke)
                # エネルギー付け先スコア: アクティブ > ベンチ (BOSS/SWITCHで引き出された時も即攻撃できるよう)
                if opp_deck_at in ("ABOMASNOW", "LUCARIO"):
                    if area == AreaType.ACTIVE:
                        if cid == MEGA_STARMIE_EX: score = 1000 - e * 100
                        elif cid == CINDERACE:     score = 950 - e * 100
                        else:                      score = 50
                    else:  # bench
                        if cid == MEGA_STARMIE_EX: score = 700 - e * 50
                        elif cid == CINDERACE:     score = 500 - e * 50
                        else:                      score = 50
                else:
                    if cid == CINDERACE:         score = 900 - e * 50
                    elif cid == MEGA_STARMIE_EX: score = 800 - e * 50
                    elif cid == STARYU:          score = 200
                    else:                        score = 0
                scored.append((score, i))
            scored.sort(key=lambda x: x[0], reverse=True)
            count = min(max_count, len(scored))
            return [x[1] for x in scored[:count]]

    count = max(min_count, 1)
    count = min(count, max_count, len(options))
    return list(range(count)) if count > 0 else []


def select_yes_no(obs: Observation) -> list[int]:
    context = obs.select.context
    if context == SelectContext.IS_FIRST:
        for i, opt in enumerate(obs.select.option):
            if opt.type == OptionType.YES:
                return [i]
    for i, opt in enumerate(obs.select.option):
        if opt.type == OptionType.YES:
            return [i]
    return [0] if obs.select.option else []


def agent(obs_dict):
    global _opp_deck_cache, _opp_deck_identified
    if obs_dict is None:
        _opp_deck_cache = "UNKNOWN"
        _opp_deck_identified = False
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
    if len(obs.select.option) == 0:
        return []
    if len(obs.select.option) == 1 and obs.select.maxCount == 1:
        return [0]
    sel_type = obs.select.type
    if sel_type == SelectType.MAIN:
        return select_main_action(obs)
    if sel_type == SelectType.YES_NO:
        return select_yes_no(obs)
    if sel_type == SelectType.CARD:
        return select_card(obs)
    count = min(obs.select.maxCount, len(obs.select.option))
    return list(range(count)) if count > 0 else []
