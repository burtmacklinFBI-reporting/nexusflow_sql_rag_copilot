# Table: product_metrics_metadata
**Domain:** Product
**Grain:** One row per unique metric.

### Key Columns
- `is_billable`: Boolean. Some metrics (like 'seats_active') might not be billable depending on the contract.

### Joins
- **Usage:** Joins to `usage_ledger` on `usage_ledger.metric_name = product_metrics_metadata.internal_name`.