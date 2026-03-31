-- DOMAIN 1: CRM & ACCOUNTS
DROP TABLE IF EXISTS organizations CASCADE;
CREATE TABLE organizations (
    org_id SERIAL PRIMARY KEY, -- autoincremental primary key which cannot be null
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(100),
    is_test_account INT DEFAULT 0 -- Trap: 1 for internal/test, 0 for real
);

DROP TABLE IF EXISTS accounts CASCADE;
CREATE TABLE accounts (
    account_id SERIAL PRIMARY KEY,
    org_id INT REFERENCES organizations(org_id),
    region VARCHAR(50), -- North, South, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DOMAIN 2: BILLING & REVENUE
DROP TABLE IF EXISTS contracts CASCADE;
CREATE TABLE contracts (
    contract_id SERIAL PRIMARY KEY,
    account_id INT REFERENCES accounts(account_id),
    total_contract_value DECIMAL(12,2),
    signed_date DATE
);

DROP TABLE IF EXISTS invoices CASCADE;
CREATE TABLE invoices (
    invoice_id SERIAL PRIMARY KEY,
    contract_id INT REFERENCES contracts(contract_id),
    amount_due DECIMAL(12,2),
    billing_month INT, -- Trap: stored as 1, 2, 3...
    billing_year INT,
    invoice_status VARCHAR(20) -- 'VOID', 'ISSUED', 'SENT'
);

DROP TABLE IF EXISTS payments CASCADE;
CREATE TABLE payments (
    payment_id SERIAL PRIMARY KEY,
    -- THE BIG TRAP: contract_ref_id is VARCHAR, while contract_id is INT
    contract_ref_id VARCHAR(50), 
    amount_paid DECIMAL(12,2),
    payment_date DATE,
    status_code INT -- Trap: 0=Failed, 1=Settled, 2=Refunded
);

-- DOMAIN 3: PRODUCT & USAGE
DROP TABLE IF EXISTS usage_ledger CASCADE;
CREATE TABLE usage_ledger (
    event_id SERIAL PRIMARY KEY,
    account_id INT REFERENCES accounts(account_id),
    metric_name VARCHAR(50), -- 'api_calls', 'seats_active'
    usage_value INT,
    usage_date DATE -- Trap: Daily grain
);

-- DOMAIN 4: METADATA LOOKUPS
DROP TABLE IF EXISTS status_mapping CASCADE;
CREATE TABLE status_mapping (
    id SERIAL PRIMARY KEY,
    table_context VARCHAR(50), -- e.g., 'payments'
    code_value INT,
    human_label VARCHAR(50) -- e.g., 'Settled'
);


-- DOMAIN 4: EXTENSIONS & TRAPS (The missing 5 tables)

DROP TABLE IF EXISTS legacy_billing_logs CASCADE;
CREATE TABLE legacy_billing_logs (
    log_id SERIAL PRIMARY KEY,
    -- TRAP: No foreign key constraint, just a string that might match contract_id
    raw_contract_code VARCHAR(100), 
    billing_event TEXT,
    event_timestamp TIMESTAMP
);

DROP TABLE IF EXISTS product_metrics_metadata CASCADE;
CREATE TABLE product_metrics_metadata (
    metric_id SERIAL PRIMARY KEY,
    internal_name VARCHAR(50), -- e.g., 'api_calls'
    display_name VARCHAR(100),
    unit VARCHAR(20), -- 'count', 'gb', 'minutes'
    is_billable BOOLEAN DEFAULT TRUE
);

DROP TABLE IF EXISTS sales_reps CASCADE;
CREATE TABLE sales_reps (
    rep_id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    region VARCHAR(50),
    base_quota DECIMAL(12,2)
);

DROP TABLE IF EXISTS rep_performance_targets CASCADE;
CREATE TABLE rep_performance_targets (
    target_id SERIAL PRIMARY KEY,
    rep_id INT REFERENCES sales_reps(rep_id),
    target_year INT,
    quarter INT,
    revenue_goal DECIMAL(12,2)
);

DROP TABLE IF EXISTS audit_logs_unstructured CASCADE;
CREATE TABLE audit_logs_unstructured (
    audit_id SERIAL PRIMARY KEY,
    performed_by_id INT, -- MIGHT be a user_id or a rep_id (ambiguous)
    action_type VARCHAR(50),
    metadata_json JSONB, -- TRAP: Data hidden in JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);