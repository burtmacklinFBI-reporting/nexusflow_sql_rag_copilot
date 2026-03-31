graph [
  directed 1
  multigraph 1
  node [
    id 0
    label "organizations"
    description "Parent company level entity containing organization details such as name, industry, and test account flag."
  ]
  node [
    id 1
    label "organizations.org_id"
    data_type "INT"
    is_primary_key 1
    description "Unique identifier for the organization."
  ]
  node [
    id 2
    label "organizations.name"
    data_type "VARCHAR"
    description "Name of the organization."
  ]
  node [
    id 3
    label "organizations.industry"
    data_type "VARCHAR"
    description "Industry sector of the organization."
  ]
  node [
    id 4
    label "organizations.is_test_account"
    data_type "INT"
    description "Flag indicating test (1) vs real (0) account."
  ]
  node [
    id 5
    label "accounts"
    description "CRM sub&#8209;entity representing a department or regional account within an organization."
  ]
  node [
    id 6
    label "accounts.account_id"
    data_type "INT"
    is_primary_key 1
    description "Unique identifier for the account."
  ]
  node [
    id 7
    label "accounts.org_id"
    data_type "INT"
    description "Foreign key to organizations.org_id."
  ]
  node [
    id 8
    label "accounts.region"
    data_type "VARCHAR"
    description "Geography of the account (e.g., 'West', 'East', 'EMEA', 'APAC')."
  ]
  node [
    id 9
    label "accounts.created_at"
    data_type "TIMESTAMP"
    description "Timestamp when the account was created."
  ]
  node [
    id 10
    label "contracts"
    description "Legal agreement linking an account to revenue; primary grain is one contract per row."
  ]
  node [
    id 11
    label "contracts.contract_id"
    data_type "INT"
    is_primary_key 1
    description "Primary key for the contract."
  ]
  node [
    id 12
    label "contracts.account_id"
    data_type "INT"
    description "Foreign key to accounts.account_id."
  ]
  node [
    id 13
    label "contracts.total_contract_value"
    data_type "NUMERIC"
    description "Total monetary value of the contract."
  ]
  node [
    id 14
    label "contracts.signed_date"
    data_type "DATE"
    description "Date when the contract was signed."
  ]
  node [
    id 15
    label "invoices"
    description "Monthly billing rows generated per contract."
  ]
  node [
    id 16
    label "invoices.invoice_id"
    data_type "INT"
    is_primary_key 1
    description "Unique identifier for the invoice."
  ]
  node [
    id 17
    label "invoices.contract_id"
    data_type "INT"
    description "Foreign key to contracts.contract_id."
  ]
  node [
    id 18
    label "invoices.amount_due"
    data_type "NUMERIC"
    description "Amount billed on the invoice."
  ]
  node [
    id 19
    label "invoices.billing_month"
    data_type "INT"
    description "Month of billing (1&#8209;12)."
  ]
  node [
    id 20
    label "invoices.billing_year"
    data_type "INT"
    description "Year of billing."
  ]
  node [
    id 21
    label "invoices.invoice_status"
    data_type "VARCHAR"
    description "Status of the invoice (e.g., 'VOID', 'ISSUED', 'SENT')."
  ]
  node [
    id 22
    label "payments"
    description "Cash&#8209;flow records; source of truth for collected revenue."
  ]
  node [
    id 23
    label "payments.payment_id"
    data_type "INT"
    is_primary_key 1
    description "Unique identifier for the payment."
  ]
  node [
    id 24
    label "payments.contract_ref_id"
    data_type "VARCHAR"
    description "Reference to contract; stored as messy string requiring extraction."
  ]
  node [
    id 25
    label "payments.amount_paid"
    data_type "NUMERIC"
    description "Cash amount received."
  ]
  node [
    id 26
    label "payments.payment_date"
    data_type "DATE"
    description "Date the payment was received."
  ]
  node [
    id 27
    label "payments.status_code"
    data_type "INT"
    description "Numeric payment state (0=Failed, 1=Settled, 2=Refunded)."
  ]
  node [
    id 28
    label "sales_reps"
    description "Employee records for sales representatives."
  ]
  node [
    id 29
    label "sales_reps.rep_id"
    data_type "INT"
    is_primary_key 1
    description "Unique identifier for the sales rep."
  ]
  node [
    id 30
    label "sales_reps.name"
    data_type "VARCHAR"
    description "Name of the sales rep."
  ]
  node [
    id 31
    label "sales_reps.region"
    data_type "VARCHAR"
    description "Internal territory code ('page'=West, 'building'=East, 'entire'=EMEA/Global)."
  ]
  node [
    id 32
    label "sales_reps.base_quota"
    data_type "NUMERIC"
    description "Base sales quota for the rep."
  ]
  node [
    id 33
    label "rep_performance_targets"
    description "Quarterly revenue goals per sales rep."
  ]
  node [
    id 34
    label "rep_performance_targets.target_id"
    data_type "INT"
    is_primary_key 1
    description "Unique identifier for the performance target row."
  ]
  node [
    id 35
    label "rep_performance_targets.rep_id"
    data_type "INT"
    description "Foreign key to sales_reps.rep_id."
  ]
  node [
    id 36
    label "rep_performance_targets.target_year"
    data_type "INT"
    description "Fiscal year of the target."
  ]
  node [
    id 37
    label "rep_performance_targets.quarter"
    data_type "INT"
    description "Quarter number (1&#8209;4)."
  ]
  node [
    id 38
    label "rep_performance_targets.revenue_goal"
    data_type "NUMERIC"
    description "Revenue goal for the quarter."
  ]
  node [
    id 39
    label "status_mapping"
    description "Key&#8209;value lookup for numeric status codes used across tables."
  ]
  node [
    id 40
    label "status_mapping.id"
    data_type "INT"
    is_primary_key 1
    description "Primary key for the mapping row."
  ]
  node [
    id 41
    label "status_mapping.table_context"
    data_type "VARCHAR"
    description "Table to which the code applies."
  ]
  node [
    id 42
    label "status_mapping.code_value"
    data_type "INT"
    description "Numeric code value."
  ]
  node [
    id 43
    label "status_mapping.human_label"
    data_type "VARCHAR"
    description "Human&#8209;readable label for the code."
  ]
  node [
    id 44
    label "usage_ledger"
    description "Daily per&#8209;account metric usage records."
  ]
  node [
    id 45
    label "usage_ledger.event_id"
    data_type "INT"
    is_primary_key 1
    description "Unique identifier for the usage event."
  ]
  node [
    id 46
    label "usage_ledger.account_id"
    data_type "INT"
    description "Foreign key to accounts.account_id."
  ]
  node [
    id 47
    label "usage_ledger.metric_name"
    data_type "VARCHAR"
    description "Name of the metric recorded."
  ]
  node [
    id 48
    label "usage_ledger.usage_value"
    data_type "NUMERIC"
    description "Quantity of usage for the metric."
  ]
  node [
    id 49
    label "usage_ledger.usage_date"
    data_type "DATE"
    description "Date of the usage record."
  ]
  node [
    id 50
    label "product_metrics_metadata"
    description "Metadata for each billable or non&#8209;billable product metric."
  ]
  node [
    id 51
    label "product_metrics_metadata.metric_id"
    data_type "INT"
    is_primary_key 1
    description "Unique identifier for the metric."
  ]
  node [
    id 52
    label "product_metrics_metadata.internal_name"
    data_type "VARCHAR"
    description "Canonical internal name of the metric."
  ]
  node [
    id 53
    label "product_metrics_metadata.is_billable"
    data_type "BOOL"
    description "Indicates if the metric is billable."
  ]
  node [
    id 54
    label "audit_logs_unstructured"
    description "Event&#8209;based security and operations logs stored as unstructured JSON."
  ]
  node [
    id 55
    label "audit_logs_unstructured.audit_id"
    data_type "INT"
    is_primary_key 1
    description "Unique identifier for the audit log entry."
  ]
  node [
    id 56
    label "audit_logs_unstructured.action_type"
    data_type "VARCHAR"
    description "Top&#8209;level category of the event (e.g., 'SYSTEM_SYNC')."
  ]
  node [
    id 57
    label "audit_logs_unstructured.metadata_json"
    data_type "JSONB"
    description "JSON payload containing IP, user&#8209;agent, tags, etc."
  ]
  node [
    id 58
    label "legacy_billing_logs"
    description "Legacy unstructured billing events; joins to contracts via raw contract code."
  ]
  node [
    id 59
    label "legacy_billing_logs.raw_contract_code"
    data_type "VARCHAR"
    description "String containing contract identifier; requires cleaning and casting to join."
  ]
  edge [
    source 0
    target 1
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 0
    target 2
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 0
    target 3
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 0
    target 4
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 5
    target 6
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 5
    target 7
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 5
    target 8
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 5
    target 9
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 5
    target 0
    key 0
    label "JOINS_WITH"
    join_condition "accounts.org_id = organizations.org_id"
  ]
  edge [
    source 5
    target 10
    key 0
    label "JOINS_WITH"
    join_condition "contracts.account_id = accounts.account_id"
  ]
  edge [
    source 5
    target 44
    key 0
    label "JOINS_WITH"
    join_condition "usage_ledger.account_id = accounts.account_id"
  ]
  edge [
    source 10
    target 11
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 10
    target 12
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 10
    target 13
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 10
    target 14
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 10
    target 15
    key 0
    label "JOINS_WITH"
    join_condition "invoices.contract_id = contracts.contract_id"
  ]
  edge [
    source 10
    target 22
    key 0
    label "JOINS_WITH"
    join_condition "CAST(SUBSTRING(payments.contract_ref_id FROM '[0-9]+') AS INTEGER) = contracts.contract_id"
  ]
  edge [
    source 10
    target 58
    key 0
    label "JOINS_WITH"
    join_condition "CAST(SUBSTRING(legacy_billing_logs.raw_contract_code FROM '[0-9]+') AS INTEGER) = contracts.contract_id"
  ]
  edge [
    source 15
    target 16
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 15
    target 17
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 15
    target 18
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 15
    target 19
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 15
    target 20
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 15
    target 21
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 22
    target 23
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 22
    target 24
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 22
    target 25
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 22
    target 26
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 22
    target 27
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 28
    target 29
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 28
    target 30
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 28
    target 31
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 28
    target 32
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 28
    target 5
    key 0
    label "JOINS_WITH"
    join_condition "accounts.region = CASE WHEN sales_reps.region = 'page' THEN 'West' WHEN sales_reps.region = 'building' THEN 'East' ELSE sales_reps.region END"
  ]
  edge [
    source 28
    target 33
    key 0
    label "JOINS_WITH"
    join_condition "rep_performance_targets.rep_id = sales_reps.rep_id"
  ]
  edge [
    source 33
    target 34
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 33
    target 35
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 33
    target 36
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 33
    target 37
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 33
    target 38
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 39
    target 40
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 39
    target 41
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 39
    target 42
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 39
    target 43
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 44
    target 45
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 44
    target 46
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 44
    target 47
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 44
    target 48
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 44
    target 49
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 44
    target 50
    key 0
    label "JOINS_WITH"
    join_condition "usage_ledger.metric_name = product_metrics_metadata.internal_name"
  ]
  edge [
    source 50
    target 51
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 50
    target 52
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 50
    target 53
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 54
    target 55
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 54
    target 56
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 54
    target 57
    key 0
    label "HAS_COLUMN"
  ]
  edge [
    source 58
    target 59
    key 0
    label "HAS_COLUMN"
  ]
]
