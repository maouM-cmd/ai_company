"""
V56: フーディン × イベルタルex「デスソウル全体KO」
Strategy:
  1. フーディン(743) ハンドパワー: 手札×2ダメカン → 大量ダメカンを相手のアクティブに集中
  2. フーディン(245) ストレンジハック: ダメカンを全体に再配置 → 全ポケモンをHP50以下に
  3. イベルタルex デスソウル: HP50以下の相手のポケモン全員を同時KO → サイド複数枚獲得!
  - vsフーディン: 悪タイプでフーディン(弱点:悪)を2倍撃
  - vsカビゴン/ハラバリーex: ダークストライク210で対処
  - ワンダーパッチで超エネ加速、エネルギー転送PROで両タイプ確保
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
# フーディン(743) ライン [ハンドパワー: 手札×2ダメカン]
ABRA_M1S = 741
KADABRA = 742          # サイコドロー: 進化時2ドロー
ALAKAZAM_HAND = 743    # サイコドロー: 進化時3ドロー + ハンドパワー

# フーディン(245) ライン [ストレンジハック: ダメカン再配置]
ABRA_SV8A = 109        # テレポーター特性: バトル場から山札に戻る
ALAKAZAM_HACK = 245    # ストレンジハック + サイコキネシス

# フィニッシャー
YVELTAL_EX = 1062      # デスソウル: HP50以下全員KO / ダークストライク: 210

# エネルギー
BASIC_PSYCHIC = 5
BASIC_DARK = 7

# グッズ
ULTRA_BALL = 1121
SWITCH = 1123
WONDER_PATCH = 1146    # トラッシュから超エネを超ポケベンチにつける
NIGHT_STRETCHER = 1097
ENERGY_TRANSFER_PRO = 1100  # ACE SPEC: 異なるタイプの基本エネを好きなだけサーチ
WEIRD_CLOCK = 1144     # 超ポケモンを退化させる (緊急用)

# サポート
BOSS_ORDERS = 1182
LILLIES_DETERMINATION = 1227
JUDGE = 1213
CARMINE = 1192

# HP reference
HP_TABLE = {
    ALAKAZAM_HAND: 140,
    ALAKAZAM_HACK: 140,
    YVELTAL_EX: 210,
    KADABRA: 80,
    ABRA_M1S: 50,
    ABRA_SV8A: 40,
}

MY_POKEMON_IDS = {ABRA_M1S, ABRA_SV8A, KADABRA, ALAKAZAM_HAND, ALAKAZAM_HACK, YVELTAL_EX}

# HP50以下でデスソウルが発動するしきい値
DEATH_SOUL_THRESHOLD = 50

# --- Opponent memory ---
_opp_seen_ids: set = set()
_my_last_prize_count: int = 6
_dark_strike_used_last_turn: bool = False


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

    def collect(poke):
        if not poke:
            return
        cid = getattr(poke, 'id', None)
        if cid is not None:
            _opp_seen_ids.add(cid)
        for pre in getattr(poke, 'preEvolution', []):
            pid = getattr(pre, 'id', None)
            if pid is not None:
                _opp_seen_ids.add(pid)

    for p in (opp_state.active or []):
        collect(p)
    for p in (opp_state.bench or []):
        collect(p)
    for c in (opp_state.discard or []):
        if c:
            cid = getattr(c, 'id', None)
            if cid is not None:
                _opp_seen_ids.add(cid)


def read_deck_csv() -> list[int]:
    return (
        [ABRA_M1S] * 4 +           # 4  進化前(743ライン)
        [KADABRA] * 4 +            # 8  中間進化(サイコドロー2ドロー)
        [ALAKAZAM_HAND] * 2 +      # 10 ハンドパワーアタッカー
        [ALAKAZAM_HACK] * 2 +      # 12 ストレンジハック再配置
        [ABRA_SV8A] * 2 +          # 14 テレポーター緊急脱出
        [YVELTAL_EX] * 2 +         # 16 デスソウルフィニッシャー
        [BASIC_PSYCHIC] * 8 +      # 24 超エネ(フーディン用)
        [BASIC_DARK] * 6 +         # 30 悪エネ(イベルタルex用)
        [ULTRA_BALL] * 4 +         # 34
        [SWITCH] * 4 +             # 38
        [WONDER_PATCH] * 4 +       # 42 超エネ加速
        [NIGHT_STRETCHER] * 3 +    # 45
        [ENERGY_TRANSFER_PRO] * 1 +# 46 ACE SPEC
        [WEIRD_CLOCK] * 2 +        # 48 退化(緊急用)
        [BOSS_ORDERS] * 4 +        # 52
        [LILLIES_DETERMINATION] * 4 +  # 56
        [JUDGE] * 2 +              # 58
        [CARMINE] * 2              # 60
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


def get_opp_pokemon_remaining_hp(poke) -> int:
    if not poke:
        return 9999
    cid = getattr(poke, 'id', -1)
    card = CARD_DB.get(cid)
    hp = getattr(card, 'hp', 200) if card else 200
    damage = getattr(poke, 'damage', 0)
    return max(0, hp - damage)


def any_opp_pokemon_at_threshold(obs: Observation, threshold: int) -> bool:
    state = obs.current
    if not state:
        return False
    opp_idx = 1 - state.yourIndex
    opp_state = state.players[opp_idx]
    for p in (opp_state.active or []):
        if p and get_opp_pokemon_remaining_hp(p) <= threshold:
            return True
    for p in (opp_state.bench or []):
        if p and get_opp_pokemon_remaining_hp(p) <= threshold:
            return True
    return False


def identify_opponent_deck(obs: Observation) -> str:
    seen = set(_opp_seen_ids)
    state = getattr(obs, 'current', None)
    if state:
        opp_idx = 1 - state.yourIndex
        opp_state = state.players[opp_idx]
        for p in (opp_state.active or []):
            if p:
                seen.add(getattr(p, 'id', -1))
        for p in (opp_state.bench or []):
            if p:
                seen.add(getattr(p, 'id', -1))

    if any(cid in seen for cid in [743, 742, 741, 245, 109]):
        return "ALAKAZAM"
    if any(cid in seen for cid in [678, 677]):
        return "LUCARIO"
    if any(cid in seen for cid in [345, 344]):
        return "CRUSTLE"
    if any(cid in seen for cid in [723, 722]):
        return "ABOMASNOW"
    if any(cid in seen for cid in [269, 268, 271]):
        return "BELLIBOLT"
    if any(cid in seen for cid in [1072, 304, 251, 135]):
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
    a_dmg = getattr(active, 'damage', 0)
    effective_max_hp = HP_TABLE.get(a_id, 200)
    remaining_hp = effective_max_hp - a_dmg

    if remaining_hp >= effective_max_hp * 0.4:
        return False

    healthy_bench = [
        p for p in my_state.bench
        if p and getattr(p, 'id', -1) in (ALAKAZAM_HAND, ALAKAZAM_HACK, YVELTAL_EX)
        and getattr(p, 'damage', 0) < 60
    ]
    return len(healthy_bench) > 0


def select_main_action(obs: Observation) -> list[int]:
    global _dark_strike_used_last_turn
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
    hand_size = len(my_state.hand) if my_state.hand else 0

    opp_deck = identify_opponent_deck(obs)
    max_bench = 2 if opp_deck == "ALAKAZAM" else 5

    # 0. RETREAT — protect badly damaged attacker
    if retreats and _should_retreat(obs):
        return [retreats[0]]

    # 1. EVOLVE — prioritize フーディン lines
    if evolves:
        for target in (ALAKAZAM_HAND, ALAKAZAM_HACK, KADABRA):
            for idx in evolves:
                if get_option_card_id(options[idx], obs) == target:
                    return [idx]
        return [evolves[0]]

    # 2. PLAYS (trainers + basics)
    if plays:
        bench_count = len([p for p in my_state.bench if p is not None])
        has_yveltal = any(getattr(p, 'id', -1) == YVELTAL_EX for p in my_state.bench if p)
        has_alakazam = any(
            getattr(p, 'id', -1) in (ALAKAZAM_HAND, ALAKAZAM_HACK)
            for p in (my_state.bench + (my_state.active or []))
            if p
        )

        allowed_plays = []
        for idx in plays:
            cid = get_option_card_id(options[idx], obs)
            if cid in (ABRA_M1S, ABRA_SV8A, YVELTAL_EX):
                if bench_count < max_bench:
                    allowed_plays.append(idx)
            else:
                allowed_plays.append(idx)

        # Bench setup: prioritize イベルタルex → ケーシィ進化ライン
        if bench_count < max_bench:
            if not has_yveltal:
                for idx in allowed_plays:
                    if get_option_card_id(options[idx], obs) == YVELTAL_EX:
                        return [idx]
            for idx in allowed_plays:
                if get_option_card_id(options[idx], obs) == ABRA_M1S:
                    return [idx]
            for idx in allowed_plays:
                if get_option_card_id(options[idx], obs) == ABRA_SV8A:
                    return [idx]

        active_hp = HP_TABLE.get(active_id, 200)
        active_remaining = active_hp - active_damage

        if active_remaining <= active_hp * 0.35:
            priority = [SWITCH, WEIRD_CLOCK, WONDER_PATCH, ULTRA_BALL, NIGHT_STRETCHER,
                        BOSS_ORDERS, LILLIES_DETERMINATION, JUDGE, CARMINE, ENERGY_TRANSFER_PRO]
        else:
            priority = [WONDER_PATCH, ULTRA_BALL, ENERGY_TRANSFER_PRO, NIGHT_STRETCHER,
                        WEIRD_CLOCK, SWITCH, BOSS_ORDERS, LILLIES_DETERMINATION, JUDGE, CARMINE]

        if opp_deck == "SNORLAX":
            for draw_card in (LILLIES_DETERMINATION, JUDGE, CARMINE):
                if draw_card in priority:
                    priority.remove(draw_card)
        elif my_state.deckCount > 5:
            priority.insert(2, LILLIES_DETERMINATION)
            priority.insert(3, CARMINE)
            priority.insert(4, JUDGE)

        # Boss's Orders: pull a weak target for デスソウル setup
        opp_active_poke = opp_state.active[0] if opp_state.active else None
        opp_active_remaining = get_opp_pokemon_remaining_hp(opp_active_poke)
        use_boss = False
        if active_id in (YVELTAL_EX, ALAKAZAM_HAND, ALAKAZAM_HACK) and get_energies(active_poke) >= 1:
            for p in opp_state.bench:
                if p and get_opp_pokemon_remaining_hp(p) <= DEATH_SOUL_THRESHOLD:
                    use_boss = True
                    break
            if not use_boss and opp_active_remaining > 150:
                for p in opp_state.bench:
                    if p and get_opp_pokemon_remaining_hp(p) < opp_active_remaining:
                        use_boss = True
                        break

        if use_boss:
            if BOSS_ORDERS in priority:
                priority.remove(BOSS_ORDERS)
            priority.insert(0, BOSS_ORDERS)

        for card_id in priority:
            for idx in allowed_plays:
                if get_option_card_id(options[idx], obs) == card_id:
                    return [idx]

    # 3. ATTACHES
    if attaches:
        active_dark = get_dark_energies(active_poke)
        active_total = get_energies(active_poke)

        if active_id == YVELTAL_EX:
            if active_dark < 2:
                for idx in attaches:
                    opt = options[idx]
                    if (get_option_card_id(opt, obs) == BASIC_DARK
                            and getattr(opt, 'inPlayArea', None) == AreaType.ACTIVE):
                        return [idx]
                for idx in attaches:
                    if getattr(options[idx], 'inPlayArea', None) == AreaType.ACTIVE:
                        return [idx]
            else:
                bench_alakazam = [
                    (i, p) for i, p in enumerate(my_state.bench)
                    if p and getattr(p, 'id', -1) in (ALAKAZAM_HAND, ALAKAZAM_HACK)
                    and get_energies(p) == 0
                ]
                if bench_alakazam:
                    bench_idx = bench_alakazam[0][0]
                    for idx in attaches:
                        opt = options[idx]
                        if (getattr(opt, 'inPlayArea', None) == AreaType.BENCH
                                and getattr(opt, 'index', -1) == bench_idx):
                            return [idx]

        elif active_id in (ALAKAZAM_HAND, ALAKAZAM_HACK):
            if active_total < 1:
                for idx in attaches:
                    opt = options[idx]
                    if (get_option_card_id(opt, obs) == BASIC_PSYCHIC
                            and getattr(opt, 'inPlayArea', None) == AreaType.ACTIVE):
                        return [idx]
                for idx in attaches:
                    if getattr(options[idx], 'inPlayArea', None) == AreaType.ACTIVE:
                        return [idx]
            else:
                bench_yveltal = [
                    (i, p) for i, p in enumerate(my_state.bench)
                    if p and getattr(p, 'id', -1) == YVELTAL_EX
                    and get_dark_energies(p) < 2
                ]
                if bench_yveltal:
                    bench_idx = bench_yveltal[0][0]
                    for idx in attaches:
                        opt = options[idx]
                        if (get_option_card_id(opt, obs) == BASIC_DARK
                                and getattr(opt, 'inPlayArea', None) == AreaType.BENCH
                                and getattr(opt, 'index', -1) == bench_idx):
                            return [idx]
                for idx in attaches:
                    if getattr(options[idx], 'inPlayArea', None) == AreaType.ACTIVE:
                        return [idx]

        return [attaches[0]]

    # 4. ATTACKS
    if attacks:
        if active_id == YVELTAL_EX:
            # デスソウル優先: HP50以下の相手ポケモンがいれば一網打尽
            if any_opp_pokemon_at_threshold(obs, DEATH_SOUL_THRESHOLD):
                return [attacks[0]]  # デスソウル
            # ダークストライク: 1攻撃しかない = ダークストライクがロックされている
            if len(attacks) == 1:
                return [attacks[0]]  # ダークストライク使えないのでデスソウル
            return [attacks[1]]  # ダークストライク 210

        elif active_id == ALAKAZAM_HAND:
            # ハンドパワー: 常に使う(手札が多いほど威力UP)
            return [attacks[0]]

        elif active_id == ALAKAZAM_HACK:
            # ストレンジハック: ダメカン再配置でデスソウル準備
            opp_active_poke = opp_state.active[0] if opp_state.active else None
            opp_remaining = get_opp_pokemon_remaining_hp(opp_active_poke)
            if opp_remaining <= 80 or any_opp_pokemon_at_threshold(obs, 80):
                return [attacks[0]]  # ストレンジハックでダメカン集中
            if len(attacks) > 1:
                return [attacks[1]]  # サイコキネシス: エネ数×50ダメ
            return [attacks[0]]

        return [attacks[-1]]

    # 5. RETREAT — fallback
    if retreats:
        return [retreats[0]]

    # 6. END TURN
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

    # BOSS'S ORDERS: target weakest opponent's bench for デスソウル setup
    is_opp_bench_selection = len(options) > 0 and all(
        getattr(opt, 'area', None) == AreaType.BENCH
        and getattr(opt, 'playerIndex', None) == opp_idx
        for opt in options
    )
    if is_opp_bench_selection:
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            opt_idx = getattr(opt, 'index', -1)
            poke_obj = opp_state.bench[opt_idx] if opp_state.bench and 0 <= opt_idx < len(opp_state.bench) else None
            remaining = get_opp_pokemon_remaining_hp(poke_obj)
            card = CARD_DB.get(cid)
            is_ex = (getattr(card, 'ex', False) or getattr(card, 'megaEx', False)
                     or 'ex' in (getattr(card, 'name', '') or '').lower()) if card else False

            if remaining <= DEATH_SOUL_THRESHOLD:
                score = 2000 - remaining  # near-KO target: highest priority
            elif remaining <= 100:
                score = 1000 - remaining
                if is_ex:
                    score += 500
            else:
                retreat = getattr(card, 'retreatCost', 2) if card else 2
                score = retreat * 50 - remaining // 10
                if is_ex:
                    score += 200
            scored.append((score, i))

        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # TOOL ATTACH: ツールの付け先選択
    context_card_id = -1
    cc = getattr(select, 'contextCard', None)
    if cc:
        context_card_id = getattr(cc, 'cardId', getattr(cc, 'id', -1))

    is_tool_attach = (
        context in (SelectContext.ATTACH_TO,)
        and max_count == 1
        and any(getattr(opt, 'area', None) in (AreaType.BENCH, AreaType.ACTIVE) for opt in options)
        and not any(get_option_card_id(opt, obs) in (BASIC_PSYCHIC, BASIC_DARK) for opt in options)
    )
    if is_tool_attach:
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            area = getattr(opt, 'area', None)
            score = 0
            if cid == YVELTAL_EX:
                score = 1000 if area == AreaType.ACTIVE else 800
            elif cid in (ALAKAZAM_HAND, ALAKAZAM_HACK):
                score = 600 if area == AreaType.ACTIVE else 400
            elif cid in (ABRA_M1S, KADABRA):
                score = 100
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # ATTACH_TO / ATTACH_FROM (エネルギー付け先)
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
                poke_obj = None
                if area == AreaType.BENCH and my_state.bench and 0 <= opt_idx < len(my_state.bench):
                    poke_obj = my_state.bench[opt_idx]
                elif area == AreaType.ACTIVE and my_state.active and 0 <= opt_idx < len(my_state.active):
                    poke_obj = my_state.active[opt_idx]

                score = 0
                if cid == YVELTAL_EX:
                    dark_e = get_dark_energies(poke_obj)
                    score = 900 - dark_e * 100
                elif cid in (ALAKAZAM_HAND, ALAKAZAM_HACK):
                    total_e = get_energies(poke_obj)
                    score = 700 - total_e * 100
                elif cid == KADABRA:
                    score = 200
                scored.append((score, i))
            scored.sort(key=lambda x: x[0], reverse=True)
            count = min(max_count, len(scored))
            return [x[1] for x in scored[:count]]
        else:
            # エネルギー選択: 使用者によって優先
            active_poke = my_state.active[0] if my_state.active else None
            active_id = getattr(active_poke, 'id', -1) if active_poke else -1
            scored = []
            for i, opt in enumerate(options):
                cid = get_option_card_id(opt, obs)
                if active_id == YVELTAL_EX:
                    score = 100 if cid == BASIC_DARK else 50
                else:
                    score = 100 if cid == BASIC_PSYCHIC else 50
                scored.append((score, i))
            scored.sort(key=lambda x: x[0], reverse=True)
            count = min(max_count, len(scored))
            return [x[1] for x in scored[:count]]

    # SETUP ACTIVE
    if context == SelectContext.SETUP_ACTIVE_POKEMON:
        if not options:
            return []
        for i, opt in enumerate(options):
            if get_option_card_id(opt, obs) == ABRA_M1S:
                return [i]
        for i, opt in enumerate(options):
            if get_option_card_id(opt, obs) == ABRA_SV8A:
                return [i]
        for i, opt in enumerate(options):
            if get_option_card_id(opt, obs) == YVELTAL_EX:
                return [i]
        return [0]

    # SETUP BENCH / TO BENCH
    if context in (SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH):
        opp_deck = identify_opponent_deck(obs)
        max_bench = 2 if opp_deck == "ALAKAZAM" else 5
        bench_count = len([p for p in my_state.bench if p is not None])

        if bench_count >= max_bench and min_count == 0:
            return []

        has_yveltal = any(getattr(p, 'id', -1) == YVELTAL_EX for p in my_state.bench if p)
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            score = 0
            if cid == YVELTAL_EX and not has_yveltal:
                score = 100
            elif cid == ABRA_M1S:
                score = 80
            elif cid == ABRA_SV8A:
                score = 60
            elif cid == YVELTAL_EX:
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
            if cid in (ABRA_M1S, ABRA_SV8A, KADABRA):
                score = 10   # 進化ラインは残す
            elif cid in (ALAKAZAM_HAND, ALAKAZAM_HACK, YVELTAL_EX):
                score = 0    # コアは絶対残す
            elif cid == BASIC_DARK:
                score = 40   # 悪エネはやや残す
            elif cid == BASIC_PSYCHIC:
                score = 50   # 超エネは捨てやすい(ワンダーパッチで回収可)
            elif cid in (SWITCH, WEIRD_CLOCK):
                score = 70
            elif cid == WONDER_PATCH:
                score = 30   # ワンダーパッチは重要
            else:
                score = 60
            scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored)))
        return [x[1] for x in scored[:count]]

    # DECK / LOOKING SEARCH
    is_search = (
        (hasattr(obs, 'current') and getattr(obs.current, 'looking', None) is not None)
        or (getattr(obs.select, 'deck', None) is not None)
        or any(getattr(opt, 'area', None) == AreaType.DECK for opt in options)
    )
    if is_search:
        has_yveltal = any(getattr(p, 'id', -1) == YVELTAL_EX for p in my_state.bench if p)
        has_alakazam = any(
            getattr(p, 'id', -1) in (ALAKAZAM_HAND, ALAKAZAM_HACK)
            for p in (my_state.bench + (my_state.active or []))
            if p
        )
        scored = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            score = 0
            if cid == YVELTAL_EX and not has_yveltal:
                score = 100
            elif cid == ALAKAZAM_HAND and not has_alakazam:
                score = 95
            elif cid == ALAKAZAM_HACK and not has_alakazam:
                score = 90
            elif cid == KADABRA:
                score = 85
            elif cid == ABRA_M1S:
                score = 80
            elif cid == ABRA_SV8A:
                score = 75
            elif cid == YVELTAL_EX:
                score = 70
            elif cid == BASIC_DARK:
                score = 50
            elif cid == BASIC_PSYCHIC:
                score = 45
            elif cid == WONDER_PATCH:
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
