# File: api/app/services/response_matrix_prefill.py
# Summary: Shared helpers for preparing response-matrix node state.

from __future__ import annotations

from api.app.models.state import HandState


def prepare_response_matrix_for_new_node(
    hand: HandState,
    *,
    iters: int | None,
) -> None:
    """
    Reset response-matrix node state.

    Prior response selections may be shown as reference during the next prune
    step, but a new fill-matrix node must start blank. This avoids carrying an
    answer from a bucket whose name changed across streets, such as Turn Draw
    becoming River Air.
    """
    del iters
    hand.response_matrix_saved = {}
