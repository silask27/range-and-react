# File: api/app/routes/villains.py
# Summary: API routes for listing villain profiles and returning a single villain's
# UI-facing metadata for the frontend.

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.app.data.villain_profiles import (
    get_villain_profile,
    list_villain_profiles,
)
from api.app.models.villain_profile import VillainProfile

router = APIRouter(prefix="/villains", tags=["villains"])


def _serialize_villain(profile: VillainProfile) -> dict:
    """
    Return the UI-facing villain payload.

    Important:
    - Do not serialize the full backend tendency model here.
    - The frontend currently only needs the villain's metadata.
    """
    return {
        "id": profile.meta.id,
        "display_name": profile.meta.display_name,
        "type_label": profile.meta.type_label,
        "description": profile.meta.description,
        "image_name": profile.meta.image_name,
    }


@router.get("")
def get_villains() -> list[dict]:
    return [_serialize_villain(profile) for profile in list_villain_profiles()]


@router.get("/{villain_id}")
def get_villain(villain_id: str) -> dict:
    try:
        profile = get_villain_profile(villain_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown villain_id: {villain_id}") from exc

    return _serialize_villain(profile)