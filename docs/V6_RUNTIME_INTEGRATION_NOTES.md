# V6 + size-model-v3 runtime integration notes

This patch set replaces the old predictive villain runtime in Range & React with:
- v6 action inference, a villain-prioritized meta stacker over v1/v2/v3/v4/v5 experts
- size-model-v3 sizing inference
- v7 bucketizer logic using hybrid scenario/fixed comparison ranges, current-strength scoring, and equity-aware draw handling

## Files in this patch
- `api/app/engine/villain_decision.py`
- `api/app/engine/bucketizer.py`
- `api/app/engine/villain_hand_bucket.py`
- `api/app/engine/action_model_features_v6.py`
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
- `trained_models_v6/`
- `trained_models_size_v2/`
- `trained_models_size_v3/`

## Important
This patch intentionally keeps the existing public backend contract:
- `choose_villain_action(...)`
- `VillainDecisionResult`

So the service layer and frontend should not need changes.

Runtime action selection remains deterministic: the selected action is always
the highest-probability action from the final v6 distribution.
