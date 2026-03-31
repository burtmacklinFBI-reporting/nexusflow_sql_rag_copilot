# Global Schema Summary (Reference for SQL Generation)

- **organizations**: `org_id` (INT), `name` (VARCHAR), `industry` (VARCHAR), `is_test_account` (INT - 0=Real, 1=Test)
- **accounts**: `account_id` (INT), `org_id` (INT), `region` (VARCHAR - e.g. 'West', 'East', 'EMEA'), `created_at` (TIMESTAMP)
- **contracts**: `contract_id` (INT), `account_id` (INT), `total_contract_value` (NUMERIC), `signed_date` (DATE)
- **invoices**: `invoice_id` (INT), `contract_id` (INT), `amount_due` (NUMERIC), `billing_month` (INT), `billing_year` (INT), `invoice_status` (VARCHAR)
- **payments**: `payment_id` (INT), `contract_ref_id` (VARCHAR - CAST TO INT TO JOIN), `amount_paid` (NUMERIC), `payment_date` (DATE), `status_code` (INT - 1=Settled)
- **sales_reps**: `rep_id` (INT), `name` (VARCHAR), `region` (VARCHAR - e.g. 'page'=West, 'building'=East), `base_quota` (NUMERIC)
- **rep_performance_targets**: `target_id` (INT), `rep_id` (INT), `target_year` (INT), `quarter` (INT), `revenue_goal` (NUMERIC)
- **status_mapping**: `id`, `table_context`, `code_value`, `human_label`
- **usage_ledger**: `event_id`, `account_id`, `metric_name`, `usage_value`, `usage_date` (DATE)
- **product_metrics_metadata**: `metric_id`, `internal_name`, `is_billable` (BOOL)
- **audit_logs_unstructured**: `audit_id`, `metadata_json` (JSONB - use ->> operator)
