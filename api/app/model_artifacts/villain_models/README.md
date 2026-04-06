# Predictive Villain Model Artifacts

Replace the files in this folder with the latest artifacts exported from
`villain-calibration-lab/data/trained_models/`.

Expected files:
- `open_action_model.pkl`
- `facing_bet_fold_continue_model.pkl`
- `facing_bet_call_raise_model.pkl`
- `facing_raise_fold_continue_model.pkl`
- `facing_raise_call_reraise_model.pkl`
- `open_bet_size_model.pkl`
- `raise_vs_bet_size_model.pkl`
- `training_summary.json`

Notes:
- Keep the filenames exactly the same.
- The main app runtime expects the artifacts to use feature version `v2`.
- If the feature version changes in the calibration lab, update the runtime
  feature code in `api/app/engine/villain_decision.py` to match before swapping
  in the new artifacts.
