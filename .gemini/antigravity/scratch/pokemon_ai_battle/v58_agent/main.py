"""
V58: Mega Gardevoir ex + Alakazam tech
Key improvements over V54:
  - Added Alakazam (non-EX) line (Abra->Kadabra->Alakazam) for Crustle matchup
  - Added Rare Candy (ふしぎなアめ) for fast evolution
  - Alakazam "Powerful Hand": place 2 damage counters per card in hand
    → bypasses Crustle's "Mysterious Rock Inn" EX block
  - Alakazam evolve ability "Psychic Draw": draw 3 cards → boosts Powerful Hand
  - Strategy vs Crustle: evolve Abra->Alakazam, attack for 160+ damage (KO in 1 hit)
  - Strategy vs Abomasnow: Rare Candy speeds up Gardevoir setup to survive Hammer-lanche
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
MEGA_GARDEVOIR_EX = 747
RALTS = 745
KIRLIA = 746
ABRA = 741
KADABRA = 742
ALAKAZAM = 743          # non-EX stage2, "Powerful Hand": 2 counters/hand card
RARE_CANDY = 1079       # ふしぎなアめ: evolve basic -> stage2 directly
TELEPATH_PSYCHIC_ENERGY = 19
BASIC_PSYCHIC_ENERGY = 5
HEROS_CAPE = 1159
CRUSHING_HAMMER = 1120
SWITCH = 1123
SUPER_POTION = 1112
POTION = 1117
BOSS_ORDERS = 1182
LILLIES_DETERMINATION = 1227
LACEY = 1199
JUDGE = 1213
DUSK_BALL = 1102

HP_TABLE = {
    MEGA_GARDEVOIR_EX: 280,
    ALAKAZAM: 140,
    KADABRA: 80,
    ABRA: 50,
    KIRLIA: 90,
    RALTS: 70,
}

_opp_seen_ids: set = set()
_my_last_prize_count: int = 6


def read_deck_csv() -> list[int]:
    return (
        [MEGA_GARDEVOIR_EX] * 3 +
        [KIRLIA] * 2 +
        [RALTS] * 4 +
        [ABRA] * 2 +
        [KADABRA] * 1 +
        [ALAKAZAM] * 2 +
        [RARE_CANDY] * 3 +
        [TELEPATH_PSYCHIC_ENERGY] * 4 +
        [BASIC_PSYCHIC_ENERGY] * 11 +
        [HEROS_CAPE] * 1 +
        [CRUSHING_HAMMER] * 4 +
        [SWITCH] * 4 +
        [SUPER_POTION] * 4 +
        [POTION] * 2 +
        [BOSS_ORDERS] * 4 +
        [LILLIES_DETERMINATION] * 3 +
        [LACEY] * 2 +
        [JUDGE] * 2 +
        [DUSK_BALL] * 2
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
        if area == AreaType.HAND and p_state.hand and 0 <= opt_idx < len(p_state.hand):
            card = p_state.hand[opt_idx]
            return getattr(card, 'id', getattr(card, 'cardId', -1))
        if area == AreaType.LOOKING and getattr(state, 'looking', None) and 0 <= opt_idx < len(state.looking):
            card = state.looking[opt_idx]
            return getattr(card, 'id', getattr(card, 'cardId', -1))
        if area == AreaType.ACTIVE and p_state.active and 0 <= opt_idx < len(p_state.active):
            poke = p_state.active[opt_idx]
            return getattr(poke, 'id', -1) if poke else -1
        if area == AreaType.BENCH and p_state.bench and 0 <= opt_idx < len(p_state.bench):
            poke = p_state.bench[opt_idx]
            return getattr(poke, 'id', -1) if poke else -1
        if getattr(state, 'looking', None) and 0 <= opt_idx < len(state.looking):
            card = state.looking[opt_idx]
            return getattr(card, 'id', getattr(card, 'cardId', -1))
        if p_state.hand and 0 <= opt_idx < len(p_state.hand):
            card = p_state.hand[opt_idx]
            return getattr(card, 'id', getattr(card, 'cardId', -1))
    except Exception:
        pass
    return -1


def get_energies(poke) -> int:
    try:
        return len(getattr(poke, 'energies', []) or [])
    except Exception:
        return 0


def _update_opp_memory(obs: Observation):
    global _opp_seen_ids, _my_last_prize_count
    state = getattr(obs, 'current', None)
    if not state:
        return
    my_idx = state.yourIndex
    my_state = state.players[my_idx]
    my_prizes = len(my_state.prize)
    if my_prizes == 6 and _my_last_prize_count < 6:
        _opp_seen_ids = set()
    _my_last_prize_count = my_prizes
    opp_idx = 1 - my_idx
    opp_state = state.players[opp_idx]

    def collect(poke):
        if poke is None:
            return
        cid = getattr(poke, 'id', None)
        if cid is not None:
            _opp_seen_ids.add(cid)
        for pre in getattr(poke, 'preEvolution', []):
            pid = getattr(pre, 'id', None)
            if pid is not None:
                _opp_seen_ids.add(pid)

    if opp_state.active:
        for p in opp_state.active:
            collect(p)
    for p in opp_state.bench:
        collect(p)
    if opp_state.discard:
        for c in opp_state.discard:
            if c:
                cid = getattr(c, 'id', None)
                if cid is not None:
                    _opp_seen_ids.add(cid)
    for p in opp_state.prize:
        if p is not None:
            cid = getattr(p, 'id', None)
            if cid is not None:
                _opp_seen_ids.add(cid)


def identify_opponent_deck(obs: Observation) -> str:
    seen = set(_opp_seen_ids)
    state = getattr(obs, 'current', None)
    if state:
        opp_idx = 1 - state.yourIndex
        opp_state = state.players[opp_idx]
        if opp_state.active:
            for p in opp_state.active:
                if p:
                    seen.add(getattr(p, 'id', -1))
        for p in opp_state.bench:
            if p:
                seen.add(getattr(p, 'id', -1))
        for c in (opp_state.discard or []):
            if c:
                seen.add(getattr(c, 'id', -1))

    if any(cid in seen for cid in [743, 742, 741]):
        return "ALAKAZAM"
    if any(cid in seen for cid in [723, 722, 721]):
        return "ABOMASNOW"
    if any(cid in seen for cid in [345, 532]):
        return "CRUSTLE"
    if any(cid in seen for cid in [269, 268, 271]):
        return "BELLIBOLT"
    if any(cid in seen for cid in [678, 677]):
        return "LUCARIO"
    if any(cid in seen for cid in [1072, 304, 251, 135]):
        return "SNORLAX"
    if any(cid in seen for cid in [119, 120, 121]):
        return "DRAGAPULT"
    if any(cid in seen for cid in [24, 790, 928]):
        return "CHARIZARD"
    if 781 in seen:
        return "HERACROSS"
    return "UNKNOWN"


def _get_total_psychic(my_state) -> int:
    total = 0
    if my_state.active:
        for p in my_state.active:
            if p:
                total += get_energies(p)
    for p in my_state.bench:
        if p:
            total += get_energies(p)
    return total


def _get_hand_size(obs: Observation) -> int:
    try:
        my_idx = obs.current.yourIndex
        return len(obs.current.players[my_idx].hand or [])
    except Exception:
        return 0


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
    a_tools = len(getattr(active, 'tools', []))
    effective_max_hp = HP_TABLE.get(a_id, 200) + (50 if a_tools > 0 else 0)
    remaining_hp = effective_max_hp - a_dmg

    opp_deck = identify_opponent_deck(obs)

    # Retreat Gardevoir to bench if Crustle is active (Gardevoir can't damage it)
    if (a_id == MEGA_GARDEVOIR_EX and opp_deck == "CRUSTLE"):
        opp_state = state.players[1 - my_idx]
        opp_active = opp_state.active[0] if opp_state.active else None
        opp_active_id = getattr(opp_active, 'id', -1) if opp_active else -1
        if opp_active_id == 345:  # Crustle is active
            bench_alakazam = [p for p in my_state.bench if p and getattr(p, 'id', -1) == ALAKAZAM]
            if bench_alakazam:
                return True

    # Retreat heavily damaged Gardevoir (normal retreat logic)
    if remaining_hp >= effective_max_hp * 0.5:
        return False

    bench_gardevoir = [
        p for p in my_state.bench
        if p and getattr(p, 'id', -1) == MEGA_GARDEVOIR_EX and getattr(p, 'damage', 0) < 100
    ]
    return len(bench_gardevoir) > 0


def select_main_action(obs: Observation) -> list[int]:
    options = obs.select.option
    evolves = []
    attacks = []
    attaches = []
    plays = []
    retreats = []
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
    active_damage = getattr(active_poke, 'damage', 0) if active_poke else 0
    active_id = getattr(active_poke, 'id', -1) if active_poke else -1

    opp_deck = identify_opponent_deck(obs)
    max_bench = 2 if opp_deck == "ALAKAZAM" else 5

    # 0. RETREAT
    if retreats and _should_retreat(obs):
        return [retreats[0]]

    # 1. EVOLVE — Alakazam > Gardevoir > Kirlia
    if evolves:
        for idx in evolves:
            cid = get_option_card_id(options[idx], obs)
            if cid == ALAKAZAM:
                return [idx]
        for idx in evolves:
            cid = get_option_card_id(options[idx], obs)
            if cid == MEGA_GARDEVOIR_EX:
                return [idx]
        for idx in evolves:
            cid = get_option_card_id(options[idx], obs)
            if cid == KIRLIA:
                return [idx]
        return [evolves[0]]

    # 2. PLAYS
    if plays:
        bench_count = len([p for p in my_state.bench if p is not None])
        total_psychic = _get_total_psychic(my_state)
        hand_size = _get_hand_size(obs)

        allowed_plays = []
        for idx in plays:
            cid = get_option_card_id(options[idx], obs)
            if cid in (RALTS, ABRA):
                if bench_count < max_bench:
                    allowed_plays.append(idx)
            else:
                allowed_plays.append(idx)

        # Against Crustle: prioritize Abra bench + Rare Candy for Alakazam setup
        if opp_deck == "CRUSTLE":
            # Check if Alakazam is already on bench or active
            has_alakazam = (active_id == ALAKAZAM or
                            any(getattr(p, 'id', -1) == ALAKAZAM for p in my_state.bench if p))
            # Check if Abra is in play
            has_abra_in_play = (active_id in (ABRA, KADABRA) or
                                any(getattr(p, 'id', -1) in (ABRA, KADABRA) for p in my_state.bench if p))
            if not has_alakazam:
                if not has_abra_in_play:
                    for idx in allowed_plays:
                        if get_option_card_id(options[idx], obs) == ABRA:
                            return [idx]
                else:
                    for idx in allowed_plays:
                        if get_option_card_id(options[idx], obs) == RARE_CANDY:
                            return [idx]

        # Rare Candy: fast evolve (Ralts->Gardevoir or Abra->Alakazam)
        for idx in allowed_plays:
            cid = get_option_card_id(options[idx], obs)
            if cid == RARE_CANDY:
                has_ralts_on_field = (active_id == RALTS or
                    any(getattr(p, 'id', -1) == RALTS for p in my_state.bench if p))
                has_abra_on_field = (active_id in (ABRA, KADABRA) or
                    any(getattr(p, 'id', -1) in (ABRA, KADABRA) for p in my_state.bench if p))
                if has_ralts_on_field or has_abra_on_field:
                    return [idx]

        # Standard bench placement
        if bench_count < max_bench:
            has_alakazam_needed = (opp_deck == "CRUSTLE" and
                not any(getattr(p, 'id', -1) in (ABRA, KADABRA, ALAKAZAM)
                        for p in my_state.bench if p) and
                active_id not in (ABRA, KADABRA, ALAKAZAM))
            if has_alakazam_needed:
                for idx in allowed_plays:
                    if get_option_card_id(options[idx], obs) == ABRA:
                        return [idx]
            for idx in allowed_plays:
                if get_option_card_id(options[idx], obs) == RALTS:
                    return [idx]

        # Healing priority
        if active_damage >= 140:
            priority = [SUPER_POTION, SWITCH, HEROS_CAPE, CRUSHING_HAMMER, DUSK_BALL, POTION, BOSS_ORDERS]
        elif active_damage >= 80:
            priority = [HEROS_CAPE, SUPER_POTION, CRUSHING_HAMMER, DUSK_BALL, POTION, SWITCH, BOSS_ORDERS]
        else:
            priority = [HEROS_CAPE, CRUSHING_HAMMER, SUPER_POTION, DUSK_BALL, POTION, SWITCH, BOSS_ORDERS]

        # Against Alakazam deck, skip Powerful Hand (also Alakazam), attack differently
        # Draw timing
        if opp_deck == "SNORLAX":
            for draw_card in (LILLIES_DETERMINATION, LACEY, JUDGE):
                if draw_card in priority:
                    priority.remove(draw_card)
        elif active_id == ALAKAZAM:
            # Against Crustle: draw cards first to maximize Powerful Hand damage
            if hand_size < 8:
                priority.insert(0, LILLIES_DETERMINATION)
                priority.insert(1, JUDGE)
                priority.insert(2, LACEY)
            # Don't play many trainers after we have enough hand size
        elif my_state.deckCount > 5:
            priority.insert(2, LILLIES_DETERMINATION)
            priority.insert(3, LACEY)
            priority.insert(4, JUDGE)

        # Boss's Orders logic (skip for Crustle/Abomasnow matchups)
        use_boss = False
        if (opp_deck not in ("ABOMASNOW", "SNORLAX", "CRUSTLE")
                and active_id == MEGA_GARDEVOIR_EX
                and get_energies(active_poke) >= 1):
            max_damage = total_psychic * 30
            opp_active_poke = opp_state.active[0] if opp_state.active else None
            opp_active_cid = getattr(opp_active_poke, 'id', -1) if opp_active_poke else -1
            opp_active_card = CARD_DB.get(opp_active_cid)
            opp_active_hp = getattr(opp_active_card, 'hp', 999) if opp_active_card else 999
            opp_active_damage = getattr(opp_active_poke, 'damage', 0) if opp_active_poke else 0
            opp_active_remaining = opp_active_hp - opp_active_damage

            if opp_active_remaining > max_damage:
                for p in opp_state.bench:
                    if p:
                        p_cid = getattr(p, 'id', -1)
                        p_card = CARD_DB.get(p_cid)
                        p_hp = getattr(p_card, 'hp', 999) if p_card else 999
                        p_remaining = p_hp - getattr(p, 'damage', 0)
                        if p_remaining <= max_damage:
                            use_boss = True
                            break

        if use_boss:
            if BOSS_ORDERS in priority:
                priority.remove(BOSS_ORDERS)
            priority.insert(0, BOSS_ORDERS)

        for card_id in priority:
            for idx in allowed_plays:
                if get_option_card_id(options[idx], obs) == card_id:
                    if card_id == SUPER_POTION and active_damage < 60:
                        continue
                    if card_id == POTION and active_damage < 30:
                        continue
                    return [idx]

    # 3. ATTACHES
    if attaches:
        # For Alakazam: spread to bench if active already has energy
        if active_id == ALAKAZAM:
            active_has_energy = get_energies(active_poke)
            if active_has_energy >= 1:
                # Attach to Gardevoir on bench instead
                for idx in attaches:
                    opt = options[idx]
                    area = getattr(opt, 'inPlayArea', None)
                    if area == AreaType.BENCH:
                        opt_idx = getattr(opt, 'index', -1)
                        if my_state.bench and 0 <= opt_idx < len(my_state.bench):
                            p = my_state.bench[opt_idx]
                            if p and getattr(p, 'id', -1) in (MEGA_GARDEVOIR_EX, KIRLIA, RALTS):
                                return [idx]
        active_energy_need = 1 if active_id == MEGA_GARDEVOIR_EX else 3
        active_has_energy = get_energies(active_poke)
        active_needs_more = active_has_energy < active_energy_need

        if active_needs_more:
            for idx in attaches:
                opt = options[idx]
                if (get_option_card_id(opt, obs) == TELEPATH_PSYCHIC_ENERGY
                        and getattr(opt, 'inPlayArea', None) == AreaType.ACTIVE):
                    return [idx]
            for idx in attaches:
                if getattr(options[idx], 'inPlayArea', None) == AreaType.ACTIVE:
                    return [idx]
        else:
            for idx in attaches:
                opt = options[idx]
                if (get_option_card_id(opt, obs) == TELEPATH_PSYCHIC_ENERGY
                        and getattr(opt, 'inPlayArea', None) == AreaType.BENCH):
                    return [idx]
            for idx in attaches:
                if getattr(options[idx], 'inPlayArea', None) == AreaType.BENCH:
                    return [idx]

        return [attaches[0]]

    # 4. ATTACKS
    if attacks:
        total_psychic = _get_total_psychic(my_state)

        # Alakazam: Powerful Hand attack (2 counters per hand card)
        if active_id == ALAKAZAM:
            hand_size = _get_hand_size(obs)
            # Attack if hand can KO or if we already have enough damage counters
            opp_active = opp_state.active[0] if opp_state.active else None
            opp_hp = 150  # Crustle HP
            if opp_active:
                opp_cid = getattr(opp_active, 'id', -1)
                opp_card = CARD_DB.get(opp_cid)
                if opp_card:
                    opp_hp = getattr(opp_card, 'hp', 150)
            opp_remaining = opp_hp - getattr(opp_active, 'damage', 0)
            projected_dmg = hand_size * 20  # 2 counters × 10 damage = 20 per card
            if projected_dmg >= opp_remaining or hand_size >= 7:
                return [attacks[0]]  # Powerful Hand (only 1 attack)
            # Not enough: skip attack (end turn with no attack to draw more)
            if end_idx is not None:
                return [end_idx]
            return [attacks[0]]  # attack anyway

        if len(attacks) > 1:
            opp_active_poke = opp_state.active[0] if opp_state.active else None
            if opp_active_poke:
                opp_cid = getattr(opp_active_poke, 'id', -1)
                opp_card = CARD_DB.get(opp_cid)
                opp_hp = getattr(opp_card, 'hp', 200) if opp_card else 200
                opp_remaining = opp_hp - getattr(opp_active_poke, 'damage', 0)
                proj_dmg = total_psychic * 30

                if proj_dmg >= opp_remaining:
                    return [attacks[1]]
                elif total_psychic <= 4:
                    return [attacks[0]]
                else:
                    return [attacks[1]]
            else:
                if total_psychic <= 4:
                    return [attacks[0]]
                else:
                    return [attacks[1]]

        return [attacks[-1]]

    # 5. RETREAT fallback
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

    opp_idx = 1 - obs.current.yourIndex
    my_idx = obs.current.yourIndex
    my_state = obs.current.players[my_idx]
    opp_state = obs.current.players[opp_idx]
    opp_deck = identify_opponent_deck(obs)

    # BOSS'S ORDERS TARGET
    is_opp_bench_selection = len(options) > 0 and all(
        getattr(opt, 'area', None) == AreaType.BENCH
        and getattr(opt, 'playerIndex', None) == opp_idx
        for opt in options
    )
    if is_opp_bench_selection:
        scored_options = []
        active_poke = my_state.active[0] if my_state.active else None
        total_psychic = _get_total_psychic(my_state)
        max_damage = total_psychic * 30

        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            opt_idx = getattr(opt, 'index', -1)
            poke_obj = None
            if opp_state.bench and 0 <= opt_idx < len(opp_state.bench):
                poke_obj = opp_state.bench[opt_idx]

            hp = 100; damage = 0; is_ex = False; retreat_cost = 2
            if poke_obj:
                card_data = CARD_DB.get(cid)
                if card_data:
                    hp = getattr(card_data, 'hp', 100)
                    retreat_cost = getattr(card_data, 'retreatCost', 2)
                    name = getattr(card_data, 'name', '')
                    is_ex = (getattr(card_data, 'ex', False)
                             or getattr(card_data, 'megaEx', False)
                             or 'ex' in name.lower())
                damage = getattr(poke_obj, 'damage', 0)

            remaining_hp = hp - damage
            energy_count = get_energies(poke_obj)
            if remaining_hp <= max_damage:
                score = 1000 + remaining_hp
                if is_ex:
                    score += 500
            else:
                score = retreat_cost * 100 - energy_count * 150
                if is_ex:
                    score -= 200
            scored_options.append((score, i))

        scored_options.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored_options)))
        return [x[1] for x in scored_options[:count]]

    # HERO'S CAPE TARGET
    context_card_id = -1
    cc = getattr(select, 'contextCard', None)
    if cc:
        context_card_id = getattr(cc, 'cardId', getattr(cc, 'id', -1))

    is_tool_attach = (
        context_card_id == HEROS_CAPE
        or (context == SelectContext.ATTACH_TO
            and max_count == 1
            and any(getattr(opt, 'area', None) in (AreaType.BENCH, AreaType.ACTIVE) for opt in options)
            and not any(get_option_card_id(opt, obs) in (BASIC_PSYCHIC_ENERGY, TELEPATH_PSYCHIC_ENERGY) for opt in options))
    )
    if is_tool_attach:
        scored_options = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            area = getattr(opt, 'area', None)
            score = 0
            if cid == MEGA_GARDEVOIR_EX:
                score = 1000 if area == AreaType.ACTIVE else 800
            elif cid == ALAKAZAM:
                score = 600 if area == AreaType.ACTIVE else 400
            elif cid in (KIRLIA, RALTS):
                score = 100
            scored_options.append((score, i))
        scored_options.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored_options)))
        return [x[1] for x in scored_options[:count]]

    # ATTACH_TO / ATTACH_FROM
    if context in (SelectContext.ATTACH_TO, SelectContext.ATTACH_FROM):
        is_choosing_pokemon = any(
            getattr(opt, 'area', None) in (AreaType.BENCH, AreaType.ACTIVE) for opt in options
        )
        if is_choosing_pokemon:
            scored_options = []
            for i, opt in enumerate(options):
                cid = get_option_card_id(opt, obs)
                opt_idx = getattr(opt, 'index', -1)
                area = getattr(opt, 'area', None)
                poke_obj = None
                if area == AreaType.BENCH and my_state.bench and 0 <= opt_idx < len(my_state.bench):
                    poke_obj = my_state.bench[opt_idx]
                elif area == AreaType.ACTIVE and my_state.active and 0 <= opt_idx < len(my_state.active):
                    poke_obj = my_state.active[opt_idx]
                energy_count = get_energies(poke_obj)
                score = 100 - (energy_count * 15)
                if cid in (MEGA_GARDEVOIR_EX, KIRLIA, RALTS):
                    score += 50
                scored_options.append((score, i))
            scored_options.sort(key=lambda x: x[0], reverse=True)
            count = min(max_count, len(scored_options))
            return [x[1] for x in scored_options[:count]]
        else:
            scored_options = []
            for i, opt in enumerate(options):
                cid = get_option_card_id(opt, obs)
                score = 100 if cid == TELEPATH_PSYCHIC_ENERGY else (90 if cid == BASIC_PSYCHIC_ENERGY else 0)
                scored_options.append((score, i))
            scored_options.sort(key=lambda x: x[0], reverse=True)
            count = min(max_count, len(scored_options))
            return [x[1] for x in scored_options[:count]]

    # SETUP ACTIVE
    if context == SelectContext.SETUP_ACTIVE_POKEMON:
        if not options:
            return []
        # Against Crustle: bring Alakazam to active (it can deal damage, EX can't)
        if opp_deck == "CRUSTLE":
            opp_active = opp_state.active[0] if opp_state.active else None
            opp_active_id = getattr(opp_active, 'id', -1) if opp_active else -1
            if opp_active_id == 345:  # Crustle is active
                for i, opt in enumerate(options):
                    if get_option_card_id(opt, obs) == ALAKAZAM:
                        return [i]
        for i, opt in enumerate(options):
            if get_option_card_id(opt, obs) == RALTS:
                return [i]
        for i, opt in enumerate(options):
            if get_option_card_id(opt, obs) == ABRA:
                return [i]
        return [0]

    # SETUP BENCH / TO BENCH
    if context in (SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH):
        max_bench = 2 if opp_deck == "ALAKAZAM" else 5
        bench_count = len([p for p in my_state.bench if p is not None])

        if bench_count >= max_bench and min_count == 0:
            # When retreating from Crustle to Alakazam: ensure Alakazam is selected
            if any(getattr(p, 'id', -1) == ALAKAZAM for p in my_state.bench if p):
                for i, opt in enumerate(options):
                    if get_option_card_id(opt, obs) == ALAKAZAM:
                        return [i]
            return []

        has_abra = any(getattr(p, 'id', -1) in (ABRA, KADABRA) for p in my_state.bench if p)
        active_id = getattr(my_state.active[0] if my_state.active else None, 'id', -1)
        active_is_abra = active_id in (ABRA, KADABRA, ALAKAZAM)

        scored_options = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            score = 0
            if opp_deck == "CRUSTLE" and not has_abra and not active_is_abra and cid == ABRA:
                score = 120  # High priority: need Alakazam for Crustle
            elif cid == RALTS:
                score = 80
            elif cid == ABRA and not has_abra:
                score = 70
            elif cid == ALAKAZAM:
                score = 60  # Alakazam to bench when retreating to it
            scored_options.append((score, i))

        scored_options.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored_options)))
        return [x[1] for x in scored_options[:count]]

    # DISCARD
    if context == SelectContext.DISCARD:
        scored_options = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            if cid in (MEGA_GARDEVOIR_EX, ALAKAZAM, KIRLIA, RALTS, ABRA, KADABRA):
                score = 0
            elif cid == BASIC_PSYCHIC_ENERGY:
                score = 50
            elif cid == TELEPATH_PSYCHIC_ENERGY:
                score = 30
            elif cid in (POTION, SUPER_POTION):
                score = 90
            elif cid in (CRUSHING_HAMMER, SWITCH, DUSK_BALL):
                score = 70
            else:
                score = 60
            scored_options.append((score, i))
        scored_options.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, min(max_count, len(scored_options)))
        return [x[1] for x in scored_options[:count]]

    # DECK / LOOKING SEARCH
    is_search = (
        (hasattr(obs, 'current') and getattr(obs.current, 'looking', None) is not None)
        or (getattr(obs.select, 'deck', None) is not None)
        or any(getattr(opt, 'area', None) == AreaType.DECK for opt in options)
    )
    if is_search:
        active_id = getattr(my_state.active[0] if my_state.active else None, 'id', -1)
        has_abra = any(getattr(p, 'id', -1) in (ABRA, KADABRA) for p in my_state.bench if p)
        active_is_abra = active_id in (ABRA, KADABRA)

        scored_options = []
        for i, opt in enumerate(options):
            cid = get_option_card_id(opt, obs)
            score = 0
            if opp_deck == "CRUSTLE" and not has_abra and not active_is_abra:
                if cid == ABRA:
                    score = 110
                elif cid == ALAKAZAM:
                    score = 105
                elif cid == RARE_CANDY:
                    score = 100
                elif cid == MEGA_GARDEVOIR_EX:
                    score = 90
                elif cid == KIRLIA:
                    score = 85
                elif cid == RALTS:
                    score = 80
                elif cid == TELEPATH_PSYCHIC_ENERGY:
                    score = 50
                elif cid == BASIC_PSYCHIC_ENERGY:
                    score = 40
            else:
                if cid == MEGA_GARDEVOIR_EX:
                    score = 90
                elif cid == KIRLIA:
                    score = 85
                elif cid == RALTS:
                    score = 80
                elif cid == ALAKAZAM and not has_abra:
                    score = 75
                elif cid == ABRA and not has_abra:
                    score = 70
                elif cid == TELEPATH_PSYCHIC_ENERGY:
                    score = 50
                elif cid == BASIC_PSYCHIC_ENERGY:
                    score = 40
            scored_options.append((score, i))
        scored_options.sort(key=lambda x: x[0], reverse=True)
        count = max(min_count, 1)
        count = min(count, max_count, len(scored_options))
        return [x[1] for x in scored_options[:count]]

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
