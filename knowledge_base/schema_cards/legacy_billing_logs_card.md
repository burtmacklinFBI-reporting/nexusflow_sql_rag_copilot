# Table: legacy_billing_logs
**Domain:** Legacy Data
**Grain:** Unstructured event log.

### Trap
- **No Foreign Keys:** Join with `contracts` by matching `raw_contract_code` string to `contract_id` (requires casting).