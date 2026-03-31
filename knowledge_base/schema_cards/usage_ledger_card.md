# Table: usage_ledger
**Domain:** Product & Usage
**Grain:** Daily per account per metric.

### Purpose
Tracks product consumption (API calls, storage).

### Joins & Caveats
- **The Grain Trap:** This table is daily. `invoices` is monthly. Never join these directly. You must aggregate `usage_ledger` by month and year before comparing to an invoice.
- **Metric Join:** Use `metric_name` to join with `product_metrics_metadata.internal_name`.