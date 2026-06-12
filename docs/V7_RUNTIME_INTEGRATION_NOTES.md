# V7 + size-model-v4 runtime integration notes

This patch set replaces the old predictive villain runtime in Range & React with:
- v7 action inference, a semantic direct model that uses v6 as a prior
- size-model-v4 sizing inference, including residual semantic sizing candidates
- v7 bucketizer logic using hybrid scenario/fixed comparison ranges, current-strength scoring, and equity-aware draw handling

## Files in this patch
- `api/app/engine/villain_decision.py`
- `api/app/engine/bucketizer.py`
- `api/app/engine/villain_hand_bucket.py`
- `api/app/engine/action_model_features_v6.py`
- `api/app/engine/action_model_features_v7.py`
- `api/app/engine/semantic_features_v7.py`
- `api/app/engine/size_model_features_v4.py`
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
- `trained_models_v7/`
- `trained_models_size_v2/`
- `trained_models_size_v3/`
- `trained_models_size_v4/`

## Important
This patch intentionally keeps the existing public backend contract:
- `choose_villain_action(...)`
- `VillainDecisionResult`

So the service layer and frontend should not need changes.

Runtime action selection remains deterministic: the selected action is always
the highest-probability action from the final v7 distribution.
