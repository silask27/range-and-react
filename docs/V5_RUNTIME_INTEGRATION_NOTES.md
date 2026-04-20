# V5 + size-model-v2 runtime integration notes

This patch set replaces the old predictive villain runtime in Range & React with:
- v5 action inference (blend over v1/v2/v3/v4 experts)
- size-model-v2 sizing inference

## Files in this patch
- `api/app/engine/villain_decision.py`
- `api/app/runtime_checks.py`
- `api/requirements.txt`
- `api/app/model_artifacts/villain_models/README.md`

## What this patch assumes
You have already completed the artifact-copy steps and created:
- `api/app/model_artifacts/villain_models/trained_models/`
- `trained_models_v2/`
- `trained_models_v3/`
- `trained_models_v4/`
- `trained_models_v5/`
- `trained_models_size_v2/`

## Important
This patch intentionally keeps the existing public backend contract:
- `choose_villain_action(...)`
- `VillainDecisionResult`

So the service layer and frontend should not need changes.
