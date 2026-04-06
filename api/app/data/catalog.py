# File: api/app/data/catalog.py
# Summary: Canonical scenario catalog defining the app's core preflop setups, positions, aggressor, default pot sizes, starting hero/villain ranges, and preflop-screen display metadata.

from __future__ import annotations

from api.app.models.enums import Player, Position
from api.app.models.scenario import Scenario

DISPLAY_SEAT_ORDER: tuple[str, ...] = (
    "UTG",
    "UTG+1",
    "UTG+2",
    "LJ",
    "HJ",
    "CO",
    "BTN",
    "SB",
    "BB",
)


def _display_seats(*seats: str) -> tuple[str, ...]:
    """Return a normalized tuple of frontend display seats."""
    return tuple(seats)


def _all_other_display_seats(hero_position: Position, villain_position: Position) -> tuple[str, ...]:
    """Return all 9-max display seats except the current hero and villain seats."""
    excluded = {hero_position.value, villain_position.value}
    return tuple(seat for seat in DISPLAY_SEAT_ORDER if seat not in excluded)




SCENARIOS: dict[str, Scenario] = {
    "srp_ip_btn_vs_bb": Scenario(
        id="srp_ip_btn_vs_bb",
        display_name="SRP IP — BTN vs BB",
        description=(
            "Single-raised pot where Hero opens on the BTN and BB calls. "
            "Hero is in position postflop and is the preflop aggressor."
        ),
        hero_position=Position.BTN,
        villain_position=Position.BB,
        hero_is_ip=True,
        preflop_aggressor=Player.HERO,
        default_pot=5.5,
        villain_range_tokens=(
            "99", "AQo", "88", "ATs",
            "KQs", "AJo", "77", "KJs", "QJs", "KTs", "KQo", "A9s", "ATo", "66", "A8s", "QTs",
            "KJo", "A7s", "A5s", "K9s", "A4s", "A6s", "55", "A3s", "KTo",
            "QJo", "A9o", "K8s", "K7s", "44", "A8o", "QTo", "Q8s", "JTo", "J8s",
            "K6s", "98s", "K5s", "K4s", "K9o", "A5o", "33", "K3s", "A4o", "Q9o",
            "87s", "Q7s", "Q6s", "K2s", "J7s", "A6o", "97s", "Q5s", "A3o", "J9o", "T9o",
            "22", "K8o", "A2o", "Q4s", "76s", "86s", "96s", "J6s", "J5s", "Q3s",
            "Q2s", "T6s", "65s", "75s", "Q8o", "54s", "J4s", "98o", "85s",
            "95s", "J3s", "64s", "T4s", "T5s", "74s",
            "53s", "43s",
        ),
        hero_range_tokens=(
            "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo", "88", "ATs",
            "KQs", "AJo", "77", "KJs", "QJs", "KTs", "KQo", "A9s", "ATo", "66", "A8s", "QTs",
            "JTs", "KJo", "A7s", "A5s", "K9s", "A4s", "A6s", "55", "Q9s", "A3s", "J9s", "KTo",
            "QJo", "A9o", "T9s", "K8s", "A2s", "K7s", "44", "A8o", "QTo", "Q8s", "JTo", "J8s",
            "K6s", "98s", "T8s", "K5s", "A7o", "K4s", "K9o", "A5o", "33", "K3s", "A4o", "Q9o",
            "87s", "Q7s", "T7s", "Q6s", "K2s", "J7s", "A6o", "97s", "Q5s", "A3o", "J9o", "T9o",
            "22", "K8o", "A2o", "Q4s", "76s", "86s", "96s", "J6s", "J5s", "Q3s",
            "Q2s", "T6s", "65s", "75s", "Q8o", "54s", "J4s", "98o", "85s",
            "95s", "J3s", "64s", "T4s", "T5s", "74s",
            "53s", "43s",
        ),
        hero_scenario_name="BTN RFI",
        villain_scenario_name="BB Defend",
        hero_action_bubble="Open",
        villain_action_bubble="Call",
        non_aggressor_previous_action=None,
        players_not_folded_hero_action=_display_seats("SB"),
        players_not_folded_villain_action=_display_seats(),
    ),
    "srp_oop_utg_vs_btn": Scenario(
        id="srp_oop_utg_vs_btn",
        display_name="SRP OOP — UTG vs BTN",
        description=(
            "Single-raised pot where Hero opens from UTG and BTN calls. "
            "Hero is out of position postflop and is the preflop aggressor."
        ),
        hero_position=Position.UTG,
        villain_position=Position.BTN,
        hero_is_ip=False,
        preflop_aggressor=Player.HERO,
        default_pot=6.5,
        villain_range_tokens=(
            "99", "AQo", "88", "ATs",
            "KQs", "77", "KJs", "QJs", "66",
        ),
        hero_range_tokens=(
            "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo", "88", "ATs",
            "KQs", "77", "KJs", "QJs", "KTs", "KQo", "A9s", "66", "A8s", "QTs",
            "JTs",
        ),
        hero_scenario_name="UTG RFI",
        villain_scenario_name="BTN Defend",
        hero_action_bubble="Open",
        villain_action_bubble="Call",
        non_aggressor_previous_action=None,
        players_not_folded_hero_action=_all_other_display_seats(Position.UTG, Position.BTN),
        players_not_folded_villain_action=_display_seats("SB", "BB"),
    ),
    "3bet_ip_co_vs_hj": Scenario(
        id="3bet_ip_co_vs_hj",
        display_name="3Bet IP — CO vs HJ",
        description=(
            "3-bet pot where HJ opens, Hero 3-bets from the CO, and HJ calls. "
            "Hero is in position postflop and is the preflop aggressor."
        ),
        hero_position=Position.CO,
        villain_position=Position.HJ,
        hero_is_ip=True,
        preflop_aggressor=Player.HERO,
        default_pot=19.5,
        villain_range_tokens=(
            "QQ", "JJ", "TT", "AQs", "99", "AJs", "88", "ATs",
            "KQs", "77", "KJs", "KTs",
        ),
        hero_range_tokens=(
            "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo", "88", "ATs",
            "KQs", "77", "KJs", "QJs", "KTs", "KQo", "A9s", "66", "A8s", "QTs",
            "JTs",
        ),
        hero_scenario_name="3BET IP",
        villain_scenario_name="3BET Defend OOP",
        hero_action_bubble="Raise",
        villain_action_bubble="Call",
        non_aggressor_previous_action="Open",
        players_not_folded_hero_action=_display_seats("BTN", "SB", "BB"),
        players_not_folded_villain_action=_display_seats(),
    ),
    "3bet_oop_sb_vs_co": Scenario(
        id="3bet_oop_sb_vs_co",
        display_name="3Bet OOP — SB vs CO",
        description=(
            "3-bet pot where CO opens, Hero 3-bets from the SB, and CO calls. "
            "Hero is out of position postflop and is the preflop aggressor."
        ),
        hero_position=Position.SB,
        villain_position=Position.CO,
        hero_is_ip=False,
        preflop_aggressor=Player.HERO,
        default_pot=21.0,
        villain_range_tokens=(
            "AKo", "QQ", "JJ", "TT", "AQs", "99", "AJs", "88", "ATs", "77", "66", "55", "44", "33", "22",
            "KQs", "KJs", "KTs", "QJs", "QTs", "JTs", "A5s", "A4s",
        ),
        hero_range_tokens=(
            "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo", "88", "ATs",
            "KQs", "KJs", "QJs", "KTs", "A9s", "QTs", "JTs",
        ),
        hero_scenario_name="3BET OOP",
        villain_scenario_name="3BET Defend IP",
        hero_action_bubble="Raise",
        villain_action_bubble="Call",
        non_aggressor_previous_action="Open",
        players_not_folded_hero_action=_display_seats("BB"),
        players_not_folded_villain_action=_display_seats(),
    ),
    "4bet_ip_co_vs_sb": Scenario(
        id="4bet_ip_co_vs_sb",
        display_name="4Bet IP — CO vs SB",
        description=(
            "4-bet pot where SB 3-bets, Hero 4-bets from the CO, and SB calls. "
            "Hero is in position postflop and is the preflop aggressor."
        ),
        hero_position=Position.CO,
        villain_position=Position.SB,
        hero_is_ip=True,
        preflop_aggressor=Player.HERO,
        default_pot=39.0,
        villain_range_tokens=(
            "QQ", "JJ", "TT", "AQs",
        ),
        hero_range_tokens=(
            "AA", "KK", "QQ", "AKs", "AKo", "AQo", "A3s", "A4s",
        ),
        hero_scenario_name="4BET IP",
        villain_scenario_name="4BET Defend OOP",
        hero_action_bubble="Raise",
        villain_action_bubble="Call",
        non_aggressor_previous_action="Raise",
        players_not_folded_hero_action=_display_seats(),
        players_not_folded_villain_action=_display_seats(),
    ),
    "4bet_oop_hj_vs_co": Scenario(
        id="4bet_oop_hj_vs_co",
        display_name="4Bet OOP — HJ vs CO",
        description=(
            "4-bet pot where CO 3-bets, Hero 4-bets from the HJ, and CO calls. "
            "Hero is out of position postflop and is the preflop aggressor."
        ),
        hero_position=Position.HJ,
        villain_position=Position.CO,
        hero_is_ip=False,
        preflop_aggressor=Player.HERO,
        default_pot=39.0,
        villain_range_tokens=(
            "QQ", "JJ", "TT", "AQs", "AKo", "AJs", "ATs", "KJs", "KQs",
        ),
        hero_range_tokens=(
            "AA", "KK", "QQ", "AKs", "AKo", "AQo", "A5s", "KQs", "KJs", "AJs", "KTs",
        ),
        hero_scenario_name="4BET OOP",
        villain_scenario_name="4BET Defend OOP",
        hero_action_bubble="Raise",
        villain_action_bubble="Call",
        non_aggressor_previous_action="Raise",
        players_not_folded_hero_action=_display_seats(),
        players_not_folded_villain_action=_display_seats(),
    ),
    "bb_defend_oop_bb_vs_btn": Scenario(
        id="bb_defend_oop_bb_vs_btn",
        display_name="BB Defend OOP — BB vs BTN",
        description=(
            "Single-raised pot where BTN opens and Hero defends the BB. "
            "Hero is out of position postflop and Villain is the preflop aggressor."
        ),
        hero_position=Position.BB,
        villain_position=Position.BTN,
        hero_is_ip=False,
        preflop_aggressor=Player.VILLAIN,
        default_pot=5.5,
        villain_range_tokens=(
            "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo", "88", "ATs",
            "KQs", "AJo", "77", "KJs", "QJs", "KTs", "KQo", "A9s", "ATo", "66", "A8s", "QTs",
            "JTs", "KJo", "A7s", "A5s", "K9s", "A4s", "A6s", "55", "Q9s", "A3s", "J9s", "KTo",
            "QJo", "A9o", "T9s", "K8s", "A2s", "K7s", "44", "A8o", "QTo", "Q8s", "JTo", "J8s",
            "K6s", "98s", "T8s", "K5s", "A7o", "K4s", "K9o", "A5o", "33", "K3s", "A4o", "Q9o",
            "87s", "Q7s", "T7s", "Q6s", "K2s", "J7s", "A6o", "97s", "Q5s", "A3o", "J9o", "T9o",
            "22", "K8o", "A2o", "Q4s", "76s", "86s", "96s", "J6s", "J5s", "Q3s",
            "Q2s", "T6s", "65s", "75s", "Q8o", "54s", "J4s", "98o", "85s",
            "95s", "J3s", "64s", "T4s", "T5s", "74s",
            "53s", "43s",
        ),
        hero_range_tokens=(
            "99", "AQo", "88", "ATs",
            "KQs", "AJo", "77", "KJs", "QJs", "KTs", "KQo", "A9s", "ATo", "66", "A8s", "QTs",
            "KJo", "A7s", "A5s", "K9s", "A4s", "A6s", "55", "A3s", "KTo",
            "QJo", "A9o", "K8s", "K7s", "44", "A8o", "QTo", "Q8s", "JTo", "J8s",
            "K6s", "98s", "K5s", "K4s", "K9o", "A5o", "33", "K3s", "A4o", "Q9o",
            "87s", "Q7s", "Q6s", "K2s", "J7s", "A6o", "97s", "Q5s", "A3o", "J9o", "T9o",
            "22", "K8o", "A2o", "Q4s", "76s", "86s", "96s", "J6s", "J5s", "Q3s",
            "Q2s", "T6s", "65s", "75s", "Q8o", "54s", "J4s", "98o", "85s",
            "95s", "J3s", "64s", "T4s", "T5s", "74s",
            "53s", "43s",
        ),
        hero_scenario_name="BB Defend",
        villain_scenario_name="BTN RFI",
        hero_action_bubble="Call",
        villain_action_bubble="Open",
        non_aggressor_previous_action=None,
        players_not_folded_hero_action=_display_seats(),
        players_not_folded_villain_action=_display_seats("SB"),
    ),
    "btn_defend_ip_btn_vs_utg": Scenario(
        id="btn_defend_ip_btn_vs_utg",
        display_name="BTN Defend IP — BTN vs UTG",
        description=(
            "Single-raised pot where UTG opens and Hero defends on the BTN. "
            "Hero is in position postflop and Villain is the preflop aggressor."
        ),
        hero_position=Position.BTN,
        villain_position=Position.UTG,
        hero_is_ip=True,
        preflop_aggressor=Player.VILLAIN,
        default_pot=6.5,
        villain_range_tokens=(
            "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo", "88", "ATs",
            "KQs", "77", "KJs", "QJs", "KTs", "KQo", "A9s", "66", "A8s", "QTs",
            "JTs",
        ),
        hero_range_tokens=(
            "99", "AQo", "88", "ATs",
            "KQs", "77", "KJs", "QJs", "66",
        ),
        hero_scenario_name="BTN Defend",
        villain_scenario_name="UTG RFI",
        hero_action_bubble="Call",
        villain_action_bubble="Open",
        non_aggressor_previous_action=None,
        players_not_folded_hero_action=_display_seats("SB", "BB"),
        players_not_folded_villain_action=_all_other_display_seats(Position.BTN, Position.UTG),
    ),
    "3bet_defend_oop_hj_vs_co": Scenario(
        id="3bet_defend_oop_hj_vs_co",
        display_name="3Bet Defend OOP — HJ vs CO",
        description=(
            "3-bet pot where Hero opens from the HJ, CO 3-bets, and Hero calls. "
            "Hero is out of position postflop and Villain is the preflop aggressor."
        ),
        hero_position=Position.HJ,
        villain_position=Position.CO,
        hero_is_ip=False,
        preflop_aggressor=Player.VILLAIN,
        default_pot=19.5,
        villain_range_tokens=(
            "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo", "88", "ATs",
            "KQs", "77", "KJs", "QJs", "KTs", "KQo", "A9s", "66", "A8s", "QTs",
            "JTs",
        ),
        hero_range_tokens=(
            "QQ", "JJ", "TT", "AQs", "99", "AJs", "88", "ATs",
            "KQs", "77", "KJs", "KTs",
        ),
        hero_scenario_name="3BET Defend OOP",
        villain_scenario_name="3BET IP",
        hero_action_bubble="Call",
        villain_action_bubble="Raise",
        non_aggressor_previous_action="Open",
        players_not_folded_hero_action=_display_seats(),
        players_not_folded_villain_action=_display_seats("BTN", "SB", "BB"),
    ),
    "3bet_defend_ip_co_vs_sb": Scenario(
        id="3bet_defend_ip_co_vs_sb",
        display_name="3Bet Defend IP — CO vs SB",
        description=(
            "3-bet pot where Hero opens from the CO, SB 3-bets, and Hero calls. "
            "Hero is in position postflop and Villain is the preflop aggressor."
        ),
        hero_position=Position.CO,
        villain_position=Position.SB,
        hero_is_ip=True,
        preflop_aggressor=Player.VILLAIN,
        default_pot=21.0,
        villain_range_tokens=(
            "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo", "88", "ATs",
            "KQs", "KJs", "QJs", "KTs", "A9s", "QTs", "JTs",
        ),
        hero_range_tokens=(
            "AKo", "QQ", "JJ", "TT", "AQs", "99", "AJs", "88", "ATs", "77", "66", "55", "44", "33", "22",
            "KQs", "KJs", "KTs", "QJs", "QTs", "JTs", "A5s", "A4s",
        ),
        hero_scenario_name="3BET Defend IP",
        villain_scenario_name="3BET OOP",
        hero_action_bubble="Call",
        villain_action_bubble="Raise",
        non_aggressor_previous_action="Open",
        players_not_folded_hero_action=_display_seats(),
        players_not_folded_villain_action=_display_seats("BB"),
    ),
    "4bet_defend_oop_sb_vs_co": Scenario(
        id="4bet_defend_oop_sb_vs_co",
        display_name="4Bet Defend OOP — SB vs CO",
        description=(
            "4-bet pot where Hero 3-bets from the SB, CO 4-bets, and Hero calls. "
            "Hero is out of position postflop and Villain is the preflop aggressor."
        ),
        hero_position=Position.SB,
        villain_position=Position.CO,
        hero_is_ip=False,
        preflop_aggressor=Player.VILLAIN,
        default_pot=39.0,
        villain_range_tokens=(
            "AA", "KK", "QQ", "AKs", "AKo", "AQo", "A3s", "A4s",
        ),
        hero_range_tokens=(
            "QQ", "JJ", "TT", "AQs",
        ),
        hero_scenario_name="4BET Defend OOP",
        villain_scenario_name="4BET IP",
        hero_action_bubble="Call",
        villain_action_bubble="Raise",
        non_aggressor_previous_action="Raise",
        players_not_folded_hero_action=_display_seats(),
        players_not_folded_villain_action=_display_seats(),
    ),
    "4bet_defend_ip_co_vs_hj": Scenario(
        id="4bet_defend_ip_co_vs_hj",
        display_name="4Bet Defend IP — CO vs HJ",
        description=(
            "4-bet pot where Hero 3-bets from the CO, HJ 4-bets, and Hero calls. "
            "Hero is in position postflop and Villain is the preflop aggressor."
        ),
        hero_position=Position.CO,
        villain_position=Position.HJ,
        hero_is_ip=True,
        preflop_aggressor=Player.VILLAIN,
        default_pot=39.0,
        villain_range_tokens=(
            "AA", "KK", "QQ", "AKs", "AKo", "AQo", "A5s", "KQs", "KJs", "AJs", "KTs",
        ),
        hero_range_tokens=(
            "QQ", "JJ", "TT", "AQs", "AKo", "AJs", "ATs", "KJs", "KQs",
        ),
        hero_scenario_name="4BET Defend IP",
        villain_scenario_name="4BET OOP",
        hero_action_bubble="Call",
        villain_action_bubble="Raise",
        non_aggressor_previous_action="Raise",
        players_not_folded_hero_action=_display_seats(),
        players_not_folded_villain_action=_display_seats(),
    ),
    "limp_iso_ip_co_vs_hj": Scenario(
        id="limp_iso_ip_co_vs_hj",
        display_name="LIMP ISO IP — CO vs HJ",
        description=(
            "Isolated limped pot where HJ limps, Hero isolates from the CO, and HJ calls. "
            "Hero is in position postflop and is the preflop aggressor."
        ),
        hero_position=Position.CO,
        villain_position=Position.HJ,
        hero_is_ip=True,
        preflop_aggressor=Player.HERO,
        default_pot=5.0,
        villain_range_tokens=(
            "22", "33", "44", "55", "66", "A5s", "A3s", "A4s", "A2s", "A6s", "65s", "76s", "98s", "54s",
        ),
        hero_range_tokens=(
            "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo", "88", "ATs",
            "KQs", "77", "KJs", "QJs", "KTs", "KQo", "A9s", "66", "A8s", "QTs",
            "JTs", "AJo", "K9s", "Q9s", "J9s", "55",
        ),
        hero_scenario_name="CO ISO",
        villain_scenario_name="HJ Limp",
        hero_action_bubble="Raise",
        villain_action_bubble="Call",
        non_aggressor_previous_action="Limp",
        players_not_folded_hero_action=_display_seats("BTN", "SB", "BB"),
        players_not_folded_villain_action=_display_seats(),
    ),
    "limp_iso_oop_sb_vs_hj": Scenario(
        id="limp_iso_oop_sb_vs_hj",
        display_name="LIMP ISO OOP — SB vs HJ",
        description=(
            "Isolated limped pot where HJ limps, Hero isolates from the SB, and HJ calls. "
            "Hero is out of position postflop and is the preflop aggressor."
        ),
        hero_position=Position.SB,
        villain_position=Position.HJ,
        hero_is_ip=False,
        preflop_aggressor=Player.HERO,
        default_pot=5.5,
        villain_range_tokens=(
            "22", "33", "44", "55", "66", "A5s", "A3s", "A4s", "A2s", "A6s", "65s", "76s", "98s", "54s",
        ),
        hero_range_tokens=(
            "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo", "88", "ATs",
            "KQs", "77", "KJs", "QJs", "KTs", "KQo", "A9s", "66", "A8s", "QTs",
            "JTs",
        ),
        hero_scenario_name="SB ISO",
        villain_scenario_name="HJ Limp",
        hero_action_bubble="Raise",
        villain_action_bubble="Call",
        non_aggressor_previous_action="Limp",
        players_not_folded_hero_action=_display_seats("BB"),
        players_not_folded_villain_action=_display_seats(),
    ),
}


SCENARIO_ORDER: list[str] = [
    "srp_ip_btn_vs_bb",
    "srp_oop_utg_vs_btn",
    "3bet_ip_co_vs_hj",
    "3bet_oop_sb_vs_co",
    "4bet_ip_co_vs_sb",
    "4bet_oop_hj_vs_co",
    "bb_defend_oop_bb_vs_btn",
    "btn_defend_ip_btn_vs_utg",
    "3bet_defend_oop_hj_vs_co",
    "3bet_defend_ip_co_vs_sb",
    "4bet_defend_oop_sb_vs_co",
    "4bet_defend_ip_co_vs_hj",
    "limp_iso_ip_co_vs_hj",
    "limp_iso_oop_sb_vs_hj",
]


def list_scenarios() -> list[Scenario]:
    """Return scenarios in the canonical UI dropdown order."""
    return [SCENARIOS[scenario_id] for scenario_id in SCENARIO_ORDER]


def get_scenario(scenario_id: str) -> Scenario:
    """Return a scenario by id."""
    return SCENARIOS[scenario_id]