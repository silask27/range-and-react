# Predictive Villain Model Artifacts

Range & React now uses the finalized calibration-lab runtime:
- **v5** for action distributions
- **size-model-v2** for bet / raise sizing

## Expected folder layout

```text
api/app/model_artifacts/villain_models/
  trained_models/
  trained_models_v2/
  trained_models_v3/
  trained_models_v4/
  trained_models_v5/
  trained_models_size_v2/
```

## Required artifact sets

### `trained_models/`
The original v1 action expert artifacts:
- `open_action_model.pkl`
- `facing_bet_fold_continue_model.pkl`
- `facing_bet_call_raise_model.pkl`
- `facing_raise_fold_continue_model.pkl`
- `facing_raise_call_reraise_model.pkl`
- `training_summary.json`

### `trained_models_v2/`
The v2 action expert artifacts:
- `open_action_model_v2.pkl`
- `facing_bet_fold_continue_model_v2.pkl`
- `facing_bet_call_raise_model_v2.pkl`
- `facing_raise_fold_continue_model_v2.pkl`
- `facing_raise_call_reraise_model_v2.pkl`
- `training_summary_v2.json`

### `trained_models_v3/`
The v3 action expert artifacts:
- `open_action_prob_model_v3.pkl`
- `facing_bet_continue_prob_model_v3.pkl`
- `facing_bet_raise_given_continue_prob_model_v3.pkl`
- `facing_raise_continue_prob_model_v3.pkl`
- `facing_raise_reraise_given_continue_prob_model_v3.pkl`
- `training_summary_v3.json`

### `trained_models_v4/`
The v4 action expert artifacts:
- `open_action_prob_model_v4.pkl`
- `facing_bet_continue_prob_model_v4.pkl`
- `facing_bet_raise_given_continue_prob_model_v4.pkl`
- `facing_raise_continue_prob_model_v4.pkl`
- `facing_raise_reraise_given_continue_prob_model_v4.pkl`
- `training_summary_v4.json`

### `trained_models_v5/`
The finalized v5 blend config:
- `blend_config_v5.json`
- `training_summary_v5.json`

### `trained_models_size_v2/`
The size-model-v2 artifacts:
- `open_bet_size_model_v2.pkl`
- `raise_vs_bet_size_model_v2.pkl`
- `reraise_vs_raise_size_model_v2.pkl`
- `training_summary_size_v2.json`

## Notes

- v5 depends on the v1/v2/v3/v4 expert artifacts being present.
- The main app runtime now samples actions from the final v5 blended distribution.
- Bet / raise sizing now comes from size-model-v2.
- Artifacts should be copied from the **current finalized Villain Calibration Lab** project, not an older snapshot.
