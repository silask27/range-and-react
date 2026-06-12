# Predictive Villain Model Artifacts

Range & React now uses the finalized calibration-lab runtime:
- **v7** for action distributions
- **size-model-v4** for bet / raise sizing

## Expected folder layout

```text
api/app/model_artifacts/villain_models/
  trained_models/
  trained_models_v2/
  trained_models_v3/
  trained_models_v4/
  trained_models_v5/
  trained_models_v6/
  trained_models_v7/
  trained_models_size_v2/
  trained_models_size_v3/
  trained_models_size_v4/
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
The v5 blend config used as one expert input to v6:
- `blend_config_v5.json`
- `training_summary_v5.json`

### `trained_models_v6/`
The v6 villain-prioritized meta action artifacts retained as priors for v7:
- `open_action_meta_model_v6.pkl`
- `facing_bet_meta_model_v6.pkl`
- `facing_raise_meta_model_v6.pkl`
- `training_summary_v6.json`

### `trained_models_v7/`
The finalized v7 semantic action artifacts:
- `open_action_model_v7.pkl`
- `facing_bet_model_v7.pkl`
- `facing_raise_model_v7.pkl`
- `training_summary_v7.json`

### `trained_models_size_v2/`
The size-model-v2 artifacts retained for compatibility and v3 comparison:
- `open_bet_size_model_v2.pkl`
- `raise_vs_bet_size_model_v2.pkl`
- `reraise_vs_raise_size_model_v2.pkl`
- `training_summary_size_v2.json`

### `trained_models_size_v3/`
The size-model-v3 artifacts retained as priors for v4:
- `open_bet_size_model_v3.pkl`
- `raise_vs_bet_size_model_v3.pkl`
- `reraise_vs_raise_size_model_v3.pkl`
- `training_summary_size_v3.json`

### `trained_models_size_v4/`
The finalized size-model-v4 artifacts:
- `open_bet_size_model_v4.pkl`
- `raise_vs_bet_size_model_v4.pkl`
- `reraise_vs_raise_size_model_v4.pkl`
- `training_summary_size_v4.json`

## Notes

- v7 depends on the v1/v2/v3/v4/v5/v6 expert artifacts being present.
- The main app runtime now chooses the highest-probability action from the final v7 distribution.
- Bet / raise sizing now comes from size-model-v4.
- Artifacts should be copied from the **current finalized Villain Calibration Lab** project, not an older snapshot.
