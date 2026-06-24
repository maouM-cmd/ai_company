import random
import time
import math
from cg.api import (
    Observation, SelectType, SelectContext,
    search_begin, search_step, search_end, search_release,
    OptionType, AreaType
)

# Card IDs for Mega Gardevoir ex deck
MEGA_GARDEVOIR_EX = 747
KIRLIA = 746
RALTS = 745
LATIAS_EX = 184
SCREAM_TAIL_EX = 969
TELEPATH_PSYCHIC_ENERGY = 19
BASIC_PSYCHIC_ENERGY = 5
HEROS_CAPE = 1159

# HP reference table for common threats
HP_TABLE = {
    747: 280,  # Mega Gardevoir ex
    184: 210,  # Latias ex
    969: 230,  # Scream Tail ex
    678: 310,  # Mega Lucario ex
    652: 340,  # Mega Venusaur ex
    781: 280,  # Mega Heracross ex
    1072: 150, # Snorlax
    304: 160,  # Hop's Snorlax (ex)
    743: 150,  # Alakazam
    723: 260,  # Mega Abomasnow ex
    345: 140,  # Crustle
    24: 180,   # Charizard ex
    119: 170,  # Dragapult ex
    269: 200,  # Bellibolt ex
}

def profile_opponent_deck(seen_ids: list[int]) -> list[int]:
    unique_seen = set(seen_ids)

    if any(cid in unique_seen for cid in [1072, 304, 251, 135, 673, 674, 675, 676]):
        return [1072]*4 + [304]*4 + [251]*2 + [135]*2 + [1120]*4 + [1081]*4 + [1117]*4 + [1112]*4 + [1159]*1 + [1152]*3 + [1102]*4 + [1182]*4 + [1224]*4 + [6]*8

    if any(cid in unique_seen for cid in [678, 677, 333, 974]):
        return [678]*4 + [677]*4 + [1121]*4 + [1123]*4 + [1182]*4 + [1213]*4 + [1224]*4 + [1145]*4 + [1120]*4 + [1112]*4 + [1159]*1 + [6]*19

    if any(cid in unique_seen for cid in [119, 120, 121, 864]):
        return [119]*4 + [120]*3 + [121]*3 + [1079]*4 + [1121]*4 + [1123]*4 + [1182]*4 + [1224]*4 + [1213]*4 + [1192]*4 + [4]*15 + [6]*10

    if 781 in unique_seen:
        return [781]*4 + [1117]*4 + [1112]*4 + [1159]*1 + [1120]*4 + [1182]*4 + [1213]*4 + [1224]*4 + [1145]*4 + [1]*27

    if any(cid in unique_seen for cid in [24, 790, 928, 788, 926, 789, 927]):
        return [24]*4 + [1123]*4 + [1182]*4 + [1213]*4 + [1192]*4 + [2]*25 + [1]*15

    if any(cid in unique_seen for cid in [345, 532, 533]):
        return [345]*4 + [532]*4 + [1121]*4 + [1123]*4 + [1182]*4 + [1213]*4 + [1227]*4 + [1]*32

    if any(cid in unique_seen for cid in [743, 742, 741, 245, 109]):
        return [743]*3 + [742]*4 + [741]*4 + [1079]*3 + [1086]*4 + [1152]*4 + [1182]*4 + [1225]*4 + [1231]*4 + [5]*26

    if any(cid in unique_seen for cid in [723, 722, 721, 419, 418]):
        return [723]*4 + [722]*4 + [721]*2 + [1145]*4 + [1158]*1 + [1205]*2 + [1227]*4 + [1235]*4 + [3]*35

    if any(cid in unique_seen for cid in [269, 268, 271, 270]):
        return [269]*4 + [268]*4 + [271]*4 + [1121]*4 + [1123]*4 + [1182]*4 + [1213]*4 + [1224]*4 + [4]*28

    if any(cid in unique_seen for cid in [747, 746, 745, 184, 969]):
        return [747]*3 + [746]*3 + [745]*4 + [184]*2 + [969]*2 + [19]*4 + [5]*12 + [1159]*1 + [1120]*4 + [1123]*4 + [1112]*4 + [1117]*4 + [1182]*4 + [1227]*3 + [1199]*2 + [1213]*2 + [1102]*2

    return [1]*20 + [210]*10 + [1123]*5 + [1182]*5 + [1213]*5 + [1224]*5 + [1192]*10


def determinize(obs: Observation, my_deck: list[int] = None):
    state = obs.current
    if not state:
        return [], [], [], [], [], []

    your_idx = state.yourIndex
    opp_idx = 1 - your_idx
    my_state = state.players[your_idx]
    opp_state = state.players[opp_idx]

    if my_deck is None:
        my_deck = [747]*3 + [746]*3 + [745]*4 + [184]*2 + [969]*2 + [19]*4 + [5]*12 + [1159]*1 + [1120]*4 + [1123]*4 + [1112]*4 + [1117]*4 + [1182]*4 + [1227]*3 + [1199]*2 + [1213]*2 + [1102]*2

    def safe_get_id(x):
        if x is None:
            return None
        if isinstance(x, int):
            return x
        return getattr(x, 'id', None)

    known_my_cards = []
    if my_state.hand:
        known_my_cards.extend([safe_get_id(c) for c in my_state.hand if safe_get_id(c) is not None])
    if my_state.discard:
        known_my_cards.extend([safe_get_id(c) for c in my_state.discard if safe_get_id(c) is not None])
    if my_state.active and my_state.active[0]:
        a = my_state.active[0]
        aid = safe_get_id(a)
        if aid is not None:
            known_my_cards.append(aid)
        if hasattr(a, 'energies') and a.energies:
            known_my_cards.extend([safe_get_id(c) for c in a.energies if safe_get_id(c) is not None])
        if hasattr(a, 'tools') and a.tools:
            known_my_cards.extend([safe_get_id(c) for c in a.tools if safe_get_id(c) is not None])
        if hasattr(a, 'preEvolution') and a.preEvolution:
            for pre in a.preEvolution:
                pre_id = safe_get_id(pre)
                if pre_id is not None:
                    known_my_cards.append(pre_id)
    for p in my_state.bench:
        if p:
            pid = safe_get_id(p)
            if pid is not None:
                known_my_cards.append(pid)
            if hasattr(p, 'energies') and p.energies:
                known_my_cards.extend([safe_get_id(c) for c in p.energies if safe_get_id(c) is not None])
            if hasattr(p, 'tools') and p.tools:
                known_my_cards.extend([safe_get_id(c) for c in p.tools if safe_get_id(c) is not None])
            if hasattr(p, 'preEvolution') and p.preEvolution:
                for pre in p.preEvolution:
                    pre_id = safe_get_id(pre)
                    if pre_id is not None:
                        known_my_cards.append(pre_id)
    for p in my_state.prize:
        if p is not None:
            pid = safe_get_id(p)
            if pid is not None:
                known_my_cards.append(pid)

    remaining = list(my_deck)
    for c in known_my_cards:
        if c in remaining:
            remaining.remove(c)
    random.shuffle(remaining)

    your_prize = []
    for p in my_state.prize:
        if p is None:
            your_prize.append(remaining.pop(0) if remaining else 1)
        else:
            your_prize.append(safe_get_id(p))

    your_deck = remaining[:my_state.deckCount]

    opp_deck_count = opp_state.deckCount
    opp_hand_count = opp_state.handCount
    total_opp_hidden = opp_deck_count + sum(1 for p in opp_state.prize if p is None) + opp_hand_count

    opp_seen_cards = []
    if opp_state.active and opp_state.active[0]:
        opp_seen_cards.append(getattr(opp_state.active[0], 'id', -1))
        for pre in getattr(opp_state.active[0], 'preEvolution', []):
            opp_seen_cards.append(getattr(pre, 'id', -1))
    for p in opp_state.bench:
        if p:
            opp_seen_cards.append(getattr(p, 'id', -1))
            for pre in getattr(p, 'preEvolution', []):
                opp_seen_cards.append(getattr(pre, 'id', -1))
    if opp_state.discard:
        opp_seen_cards.extend([getattr(c, 'id', -1) for c in opp_state.discard])
    for p in opp_state.prize:
        if p is not None:
            opp_seen_cards.append(getattr(p, 'id', -1))

    opp_template = profile_opponent_deck(opp_seen_cards)

    opp_known = list(opp_seen_cards)
    remaining_opp = list(opp_template)
    for c in opp_known:
        if c in remaining_opp:
            remaining_opp.remove(c)
    random.shuffle(remaining_opp)

    while len(remaining_opp) < total_opp_hidden + 10:
        remaining_opp.append(1)

    opp_prize = []
    for p in opp_state.prize:
        if p is None:
            opp_prize.append(remaining_opp.pop(0) if remaining_opp else 1)
        else:
            opp_prize.append(safe_get_id(p))

    opp_hand = remaining_opp[:opp_hand_count]
    opp_deck_cards = remaining_opp[opp_hand_count:opp_hand_count + opp_deck_count]

    opp_active = []
    if opp_state.active and len(opp_state.active) > 0 and opp_state.active[0] is None:
        opp_active = [210]

    return your_deck, your_prize, opp_deck_cards, opp_prize, opp_hand, opp_active


def evaluate_state(obs: Observation, original_my_idx: int) -> float:
    if obs is None or obs.current is None:
        return 0.0
    state = obs.current

    my_idx = original_my_idx
    opp_idx = 1 - my_idx

    my = state.players[my_idx]
    opp = state.players[opp_idx]

    if state.result != -1:
        if state.result == my_idx:
            return 1000000.0
        else:
            return -1000000.0

    score = 0.0

    # --- Prize Race (most impactful) ---
    my_prize = len(my.prize)
    opp_prize = len(opp.prize)
    score += (6 - my_prize) * 20000.0
    score -= (6 - opp_prize) * 20000.0

    if my_prize <= 1:
        score += 50000.0
    if opp_prize <= 1:
        score -= 50000.0

    # --- My board state ---
    total_psychic = 0
    my_active = my.active[0] if my.active else None

    if my_active:
        a_id = getattr(my_active, 'id', -1)
        a_energies = len(getattr(my_active, 'energies', []))
        a_damage = getattr(my_active, 'damage', 0)
        a_tools = len(getattr(my_active, 'tools', []))
        total_psychic += a_energies

        if a_id == MEGA_GARDEVOIR_EX:
            score += 25000.0
            # Hero's Cape adds 50 effective HP
            effective_hp = 280 + (50 if a_tools > 0 else 0) - a_damage
            score -= a_damage * 600.0
            if effective_hp < 80:
                score -= 50000.0   # About to be KO'd — bad!
            elif effective_hp < 150:
                score -= 15000.0   # Risky
        elif a_id == SCREAM_TAIL_EX:
            score += 8000.0
            score -= getattr(my_active, 'damage', 0) * 150.0
        elif a_id == LATIAS_EX:
            score += 5000.0
        elif a_id == KIRLIA:
            score += 2000.0
        elif a_id == RALTS:
            score += 500.0

    bench_count = 0
    for p in my.bench:
        if p is None:
            continue
        bench_count += 1
        b_id = getattr(p, 'id', -1)
        b_energies = len(getattr(p, 'energies', []))
        b_damage = getattr(p, 'damage', 0)
        total_psychic += b_energies

        if b_id == MEGA_GARDEVOIR_EX:
            score += 15000.0
            score -= b_damage * 300.0
        elif b_id == LATIAS_EX:
            score += 12000.0   # Free-retreat support is huge
        elif b_id == SCREAM_TAIL_EX:
            score += 5000.0
        elif b_id == KIRLIA:
            score += 3000.0    # 1 step from Gardevoir
        elif b_id == RALTS:
            score += 1500.0

    score += bench_count * 1000.0
    if bench_count == 0:
        score -= 120000.0  # Bench-out prevention

    # Psychic energy drives attack damage: each energy = 30 damage
    score += total_psychic * 5000.0

    # --- KO prediction ---
    # Gardevoir attack: 30 * total_psychic damage
    projected_dmg = total_psychic * 30
    if opp.active and opp.active[0]:
        opp_active = opp.active[0]
        opp_a_id = getattr(opp_active, 'id', -1)
        opp_a_dmg = getattr(opp_active, 'damage', 0)
        opp_a_hp = HP_TABLE.get(opp_a_id, 200)

        remaining_opp_hp = opp_a_hp - opp_a_dmg
        score += opp_a_dmg * 40.0  # Accumulated damage on opponent is good

        if projected_dmg >= remaining_opp_hp:
            score += 80000.0   # Can KO this turn!
        elif projected_dmg >= remaining_opp_hp * 0.6:
            score += 20000.0   # Can KO in 2 turns

    # --- Opponent threatening us ---
    # If opponent active can likely KO our active next turn, penalize
    if opp.active and opp.active[0] and my_active:
        opp_a_id = getattr(opp.active[0], 'id', -1)
        my_a_id = getattr(my_active, 'id', -1)
        my_remaining_hp = HP_TABLE.get(my_a_id, 200) - getattr(my_active, 'damage', 0)
        # Rough estimate: if opponent has lots of energies, they might KO us
        opp_energy_count = len(getattr(opp.active[0], 'energies', []))
        if opp_energy_count >= 3 and my_remaining_hp < 150:
            score -= 25000.0

    # --- Hand size (draw power) ---
    hand_count = len(my.hand) if my.hand else my.handCount
    score += min(hand_count, 6) * 300.0

    # --- Deck safeguard (avoid self deck-out) ---
    deck_count = getattr(my, 'deckCount', 30)
    if deck_count <= 10:
        score -= (10 - deck_count) * 18000.0

    return score


def calculate_priors(options, obs: Observation = None) -> dict:
    """Gardevoir-specific action priors for better MCTS exploration."""
    priors = {}
    total = 0.0

    # Context: check active pokemon
    active_id = -1
    active_energy = 0
    total_board_energy = 0
    if obs and obs.current:
        state = obs.current
        my_idx = state.yourIndex
        my = state.players[my_idx]
        if my.active and my.active[0]:
            active_id = getattr(my.active[0], 'id', -1)
            active_energy = len(getattr(my.active[0], 'energies', []))
        for p in [my.active[0]] + list(my.bench) if my.active else list(my.bench):
            if p:
                total_board_energy += len(getattr(p, 'energies', []))

    for i, opt in enumerate(options):
        score = 0.0
        otype = getattr(opt, 'type', None)

        if otype == OptionType.EVOLVE:
            score = 120.0   # Always want to evolve Ralts -> Kirlia -> Gardevoir
        elif otype == OptionType.ATTACK:
            if active_id == MEGA_GARDEVOIR_EX:
                # Attack 2 (high damage) better when enough energy
                if total_board_energy >= 5:
                    score = 110.0
                else:
                    score = 85.0
            else:
                score = 90.0
        elif otype == OptionType.PLAY:
            score = 88.0
        elif otype == OptionType.ATTACH:
            in_active = hasattr(opt, 'inPlayArea') and opt.inPlayArea == AreaType.ACTIVE
            if active_id == MEGA_GARDEVOIR_EX and in_active and active_energy < 3:
                score = 105.0  # High priority: power up Gardevoir
            elif in_active:
                score = 85.0
            else:
                score = 75.0
        elif otype == OptionType.RETREAT:
            # Retreat is valuable when active is heavily damaged
            if obs and obs.current:
                my_a = obs.current.players[obs.current.yourIndex].active
                if my_a and my_a[0]:
                    dmg = getattr(my_a[0], 'damage', 0)
                    a_id = getattr(my_a[0], 'id', -1)
                    max_hp = HP_TABLE.get(a_id, 200)
                    if dmg > max_hp * 0.7:
                        score = 70.0  # Active is in danger, retreating is valuable
                    else:
                        score = 15.0
                else:
                    score = 15.0
            else:
                score = 15.0
        elif otype == OptionType.ABILITY:
            score = 10.0
        elif otype == OptionType.END:
            score = 1.0
        else:
            score = 30.0

        priors[i] = score
        total += score

    if total > 0:
        for i in priors:
            priors[i] = priors[i] / total
    return priors


class MCTSNode:
    def __init__(self, search_id: int, obs: Observation, parent=None, parent_action=None):
        self.search_id = search_id
        self.obs = obs
        self.parent = parent
        self.parent_action = parent_action
        self.children = {}
        self.priors = calculate_priors(
            obs.select.option if (obs and obs.select and obs.select.option) else [],
            obs
        )
        self.N = {}
        self.Q = {}
        self.W = {}
        if obs and obs.select and obs.select.option:
            for a in self.priors:
                if self.priors[a] > 0:
                    self.N[a] = 0
                    self.Q[a] = 0.0
                    self.W[a] = 0.0


def run_mcts(obs: Observation, my_deck: list[int] = None, time_limit_sec=0.20):
    if obs is None or obs.select is None or obs.select.type != SelectType.MAIN:
        return None

    options = obs.select.option
    if not options or len(options) <= 1:
        return None

    start_time = time.time()
    your_deck, your_prize, opp_deck, opp_prize, opp_hand, opp_active = determinize(obs, my_deck)
    try:
        root_state = search_begin(
            agent_observation=obs,
            your_deck=your_deck,
            your_prize=your_prize,
            opponent_deck=opp_deck,
            opponent_prize=opp_prize,
            opponent_hand=opp_hand,
            opponent_active=opp_active
        )
    except Exception:
        return None

    root_id = root_state.searchId
    root_node = MCTSNode(root_id, obs)

    # C_PUCT tuned: lower = more exploitation, higher = more exploration
    # With 0.20s limit and eval scale ~15000 per prize, 300 is a reasonable balance
    C_PUCT = 300.0
    VISIT_THRESH = 2
    iterations = 0
    created_ids = []

    while time.time() - start_time < time_limit_sec:
        curr_node = root_node
        path = [curr_node]

        # Selection
        while True:
            if curr_node.obs.current and curr_node.obs.current.yourIndex != obs.current.yourIndex:
                best_a = None
                break

            best_a = None
            best_puct = -float('inf')

            unvisited = [a for a in curr_node.N if curr_node.N[a] == 0]
            if unvisited:
                # Pick unvisited action with highest prior
                best_a = max(unvisited, key=lambda a: curr_node.priors[a])
            else:
                total_N = sum(curr_node.N.values())
                for a in curr_node.N:
                    u = C_PUCT * curr_node.priors[a] * math.sqrt(total_N) / (1 + curr_node.N[a])
                    s = curr_node.Q[a] + u
                    if s > best_puct:
                        best_puct = s
                        best_a = a

            if best_a is None:
                break

            if best_a in curr_node.children:
                curr_node = curr_node.children[best_a]
                path.append(curr_node)
            else:
                break

        # Expansion & Evaluation
        if best_a is not None:
            try:
                child_state = search_step(curr_node.search_id, [best_a])
                child_id = child_state.searchId
                child_obs = child_state.observation
                created_ids.append(child_id)

                is_opp_turn = child_obs.current and child_obs.current.yourIndex != obs.current.yourIndex
                parent_visits = curr_node.N[best_a]

                if parent_visits >= VISIT_THRESH and child_obs and child_obs.select and not is_opp_turn:
                    child_node = MCTSNode(child_id, child_obs, parent=curr_node, parent_action=best_a)
                    curr_node.children[best_a] = child_node
                    val = evaluate_state(child_obs, obs.current.yourIndex)
                    path.append(child_node)
                else:
                    val = evaluate_state(child_obs, obs.current.yourIndex)
                    try:
                        search_release(child_id)
                        created_ids.remove(child_id)
                    except Exception:
                        pass
            except Exception:
                val = -100000.0
        else:
            val = evaluate_state(curr_node.obs, obs.current.yourIndex)

        # Backpropagation
        if best_a is not None and (best_a not in curr_node.children):
            curr_node.W[best_a] = curr_node.W.get(best_a, 0.0) + val
            curr_node.N[best_a] = curr_node.N.get(best_a, 0) + 1
            curr_node.Q[best_a] = curr_node.W[best_a] / curr_node.N[best_a]

        for node in path:
            if node.parent is not None:
                p_action = node.parent_action
                node.parent.W[p_action] = node.parent.W.get(p_action, 0.0) + val
                node.parent.N[p_action] = node.parent.N.get(p_action, 0) + 1
                node.parent.Q[p_action] = node.parent.W[p_action] / node.parent.N[p_action]

        iterations += 1

    # Cleanup
    for cid in created_ids:
        try:
            search_release(cid)
        except Exception:
            pass
    try:
        search_end()
    except Exception:
        pass

    if sum(root_node.N.values()) == 0:
        return None

    best_action = max(root_node.N, key=lambda a: root_node.N[a])
    return [best_action]
