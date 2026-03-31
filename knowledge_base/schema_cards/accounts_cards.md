# Table: accounts
**Domain:** CRM
**Grain:** Sub-entity or department level.

### Purpose
A single organization can have multiple accounts (e.g., North America vs. EMEA).

### Columns
- `region` (VARCHAR): The geography of the account. 
    - **Note:** Uses full names (e.g., 'West', 'East', 'North', 'South', 'EMEA', 'APAC').
- **Semantic Join Trap:** To link an `account` to a `sales_rep`, you must match the `region` column.
    - **Mapping:** 'West' (Account) = 'page' (Rep), 'East' (Account) = 'building' (Rep), 'EMEA' (Account) = 'entire' (Rep).
    - **SQL Example:** `JOIN sales_reps sr ON a.region = CASE WHEN sr.region = 'page' THEN 'West' WHEN sr.region = 'building' THEN 'East' ELSE sr.region END`

### Joins
- **Parent:** Joins to `organizations` on `org_id`.
- **Children:** 
    - Parent to `contracts` (via `account_id`).
    - Parent to `usage_ledger` (via `account_id`).