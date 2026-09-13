# Desired Settings — tuning guide

Every scout has `scout/config.yaml: desired_settings.optimize_for`. The foreman can set global, each scout can override.

## Common optimize_for values
- `revenue_retained` — churn, pricing, onboarding
- `forecast_accuracy` — prophet, causal
- `detection_per_false_alarm` — anomaly, perimeter, purple
- `days_of_autonomy` — water-food-grid, off-grid
- `sovereignty_per_compliance_cost` — jurisdiction
- `calibration` — black-swan (Brier, not win rate)
- `safety_locked` — hazard-guardian (DO NOT CHANGE)

## Example: tune one scout
```yaml
# .agents/skills/epistemic-immune-system/scout/config.yaml
desired_settings:
  optimize_for: deception_caught
  paranoia: calibrated  # low|calibrated|high
```

## Example: global via CLI
```bash
scout set-optimize revenue_retained
scout config epistemic-immune-system --set paranoia=high
```
