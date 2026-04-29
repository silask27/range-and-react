# File: api/app/engine/bucket_engine.py
# Summary: Adapts live villain combo state into Screen 3 bucket rows with percentages,
# holdings counts, and subgroup-aware hand data for the updated bucketizer output.

from __future__ import annotations

from collections import defaultdict

from api.app.engine.bucketizer import BUCKETS
from api.app.engine.villain_hand_bucket import UI_SUBGROUPS
from api.app.engine.dealing import available_combos_for_label
from api.app.engine.villain_hand_bucket import bucket_villain_hand


def _bucket_sort_key(bucket_name: str) -> int:
    try:
        return BUCKETS.index(bucket_name)
    except ValueError:
        return len(BUCKETS)


def _subgroup_sort_key(subgroup_name: str) -> int:
    try:
        return UI_SUBGROUPS.index(subgroup_name)
    except ValueError:
        return len(UI_SUBGROUPS)


def _sorted_combo_lists(combos: list[list[str]]) -> list[list[str]]:
    return sorted([list(combo) for combo in combos], key=lambda c: (c[0], c[1]))


def build_bucket_matrix_view(
    *,
    villain_range_combos_live: dict[str, list[list[str]]],
    board: list[str],
    hero_hand: tuple[str, str] | list[str],
    villain_profile_id: str,
    scenario_hero_range_tokens: list[str] | tuple[str, ...] | None = None,
    iters: int | None = None,
    seed: int = 42,
) -> dict:
    """
    Build the Screen 3 bucket rows from the current live villain combo map.

    Updated output shape:
    - Response-matrix rows remain keyed by broad bucket name.
    - Each broad bucket row now contains subgroup sections.
    - A flattened "hands" list is still included for transitional compatibility,
      but each hand entry also carries subgroup_name.

    Output:
    {
        "total_live_combos": 42,
        "hero_range_source": "fixed",
        "row_order": ["Draw", "Air", "SDV", "Value", "Nutted Value"],
        "rows": [
            {
                "bucket_name": "SDV",
                "bucket_percent": 35.71,
                "combo_count": 15,
                "holdings_count": 5,
                "hands": [
                    {
                        "label": "QJs",
                        "subgroup_name": "Top Pair",
                        "live_combos": 2,
                        "max_combos": 4,
                        "combo_cards": [["Qh","Jh"], ["Qs","Js"]],
                    }
                ],
                "subgroups": [
                    {
                        "subgroup_name": "Top Pair",
                        "combo_count": 8,
                        "holdings_count": 3,
                        "hands": [...],
                    }
                ],
            }
        ],
    }

    Iteration rule:
    - if iters is omitted, bucket_villain_hand() falls back to the street defaults
      defined in bucketizer.py via bz.resolve_iters(...)
    """
    live_label_totals = {
        label: len(combos)
        for label, combos in villain_range_combos_live.items()
        if combos
    }

    total_live_combos = sum(live_label_totals.values())
    if total_live_combos == 0:
        return {
            "total_live_combos": 0,
            "hero_range_source": "fixed",
            "row_order": [],
            "rows": [],
        }

    excluded_for_max = [*list(hero_hand), *list(board)]
    max_label_totals = {
        label: len(available_combos_for_label(label, excluded_cards=excluded_for_max))
        for label in live_label_totals
    }

    bucket_to_subgroup_to_label_to_combos: dict[str, dict[str, dict[str, list[list[str]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    bucket_combo_counts: dict[str, int] = defaultdict(int)
    bucket_subgroup_combo_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    hero_range_source: str | None = None

    for label, combos in villain_range_combos_live.items():
        if not combos:
            continue

        for combo_cards in combos:
            result = bucket_villain_hand(
                villain_hand=tuple(combo_cards),
                board=board,
                villain_profile_id=villain_profile_id,
                scenario_hero_range_tokens=scenario_hero_range_tokens,
                iters=iters,
                seed=seed,
            )

            if hero_range_source is None:
                hero_range_source = result.hero_range_source

            bucket_name = result.bucket_label
            subgroup_name = result.display_subgroup_label

            bucket_to_subgroup_to_label_to_combos[bucket_name][subgroup_name][label].append(
                list(combo_cards)
            )
            bucket_combo_counts[bucket_name] += 1
            bucket_subgroup_combo_counts[bucket_name][subgroup_name] += 1

    row_names = [bucket_name for bucket_name in BUCKETS if bucket_name in bucket_combo_counts]
    if not row_names:
        row_names = sorted(bucket_combo_counts.keys(), key=_bucket_sort_key)

    rows: list[dict] = []
    for bucket_name in row_names:
        subgroup_map = bucket_to_subgroup_to_label_to_combos[bucket_name]
        subgroup_names = sorted(subgroup_map.keys(), key=_subgroup_sort_key)

        subgroups: list[dict] = []
        flattened_hands: list[dict] = []

        for subgroup_name in subgroup_names:
            label_map = subgroup_map[subgroup_name]
            subgroup_hands: list[dict] = []

            for label, combo_lists in sorted(
                label_map.items(),
                key=lambda item: (-len(item[1]), item[0]),
            ):
                hand_entry = {
                    "label": label,
                    "subgroup_name": subgroup_name,
                    "live_combos": len(combo_lists),
                    "max_combos": max_label_totals.get(label, len(combo_lists)),
                    "combo_cards": _sorted_combo_lists(combo_lists),
                }
                subgroup_hands.append(hand_entry)
                flattened_hands.append(hand_entry)

            subgroups.append(
                {
                    "subgroup_name": subgroup_name,
                    "combo_count": bucket_subgroup_combo_counts[bucket_name][subgroup_name],
                    "holdings_count": len(subgroup_hands),
                    "hands": subgroup_hands,
                }
            )

        combo_count = bucket_combo_counts[bucket_name]
        rows.append(
            {
                "bucket_name": bucket_name,
                "bucket_percent": round((combo_count / total_live_combos) * 100, 2),
                "combo_count": combo_count,
                "holdings_count": len(flattened_hands),
                "hands": flattened_hands,
                "subgroups": subgroups,
            }
        )

    return {
        "total_live_combos": total_live_combos,
        "hero_range_source": hero_range_source or "fixed",
        "row_order": row_names,
        "rows": rows,
    }