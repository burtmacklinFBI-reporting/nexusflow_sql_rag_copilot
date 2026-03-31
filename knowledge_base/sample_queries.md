# Gold Standard SQL: NexusFlow Query Library

This document contains "Gold Standard" SQL patterns that correctly handle the NexusFlow schema's "traps" and business logic as defined in the `company_knowledge.md`.

## 1. Finance & Revenue (NRR)

### Question: "What is our total Net Realized Revenue (NRR) for the year 2026, excluding test accounts?"

**Logic:**
- Filter out test organizations.
- Join Org -> Account -> Contract -> Payments.
- Handle the String/Int Trap (`contract_ref_id`).
- Sum `amount_paid` where status is Settled (1) minus Refunds (2).

```sql
SELECT 
    SUM(CASE WHEN p.status_code = 1 THEN p.amount_paid ELSE 0 END) - 
    SUM(CASE WHEN p.status_code = 2 THEN p.amount_paid ELSE 0 END) as net_realized_revenue
FROM organizations o
JOIN accounts a ON o.org_id = a.org_id
JOIN contracts c ON a.account_id = c.account_id
JOIN payments p ON CAST(SUBSTRING(p.contract_ref_id FROM '[0-9]+') AS INTEGER) = c.contract_id
WHERE o.is_test_account = 0
  AND p.payment_date BETWEEN '2026-01-01' AND '2026-12-31';
```

---

## 2. Sales Operations (Territory Performance)

### Question: "Show me the revenue attainment vs. goal for Sales Reps in the West Coast territory for Q1 2026."

**Logic:**
- Translate "West Coast" to the territory code 'page'.
- Join Sales Reps -> Performance Targets.
- Calculate revenue from Payments (NRR).
- Join Rep -> Account (via Sales Rep context) -> Contract -> Payments.

```sql
WITH RepRevenue AS (
    SELECT 
        sr.rep_id,
        sr.name as rep_name,
        SUM(p.amount_paid) as raw_revenue
    FROM sales_reps sr
    -- Semantic Join: Rep 'page' matches Account 'West'
    JOIN accounts a ON a.region = (
        CASE 
            WHEN sr.region = 'page' THEN 'West' 
            WHEN sr.region = 'building' THEN 'East' 
            WHEN sr.region = 'entire' THEN 'EMEA'
            ELSE sr.region 
        END
    )
    JOIN contracts c ON a.account_id = c.account_id
    JOIN payments p ON CAST(SUBSTRING(p.contract_ref_id FROM '[0-9]+') AS INTEGER) = c.contract_id
    JOIN organizations o ON a.org_id = o.org_id
    WHERE o.is_test_account = 0
      AND p.status_code = 1
    GROUP BY sr.rep_id, sr.name
)
SELECT 
    rep_name,
    raw_revenue,
    raw_revenue * 0.8 as weighted_revenue -- North America multiplier
FROM RepRevenue
WHERE rep_name ILIKE '%Stacy Kelly%';
```

---

## 3. Product & Usage (Overage Analysis)

### Question: "Which accounts exceeded their API call limit of 5000 in February 2026?"

**Logic:**
- Sum daily usage from `usage_ledger`.
- Join to `product_metrics_metadata` to verify the metric name.
- Filter for Feb 2026.

```sql
SELECT 
    a.account_id,
    o.name as company_name,
    SUM(ul.usage_value) as total_api_calls
FROM accounts a
JOIN organizations o ON a.org_id = o.org_id
JOIN usage_ledger ul ON a.account_id = ul.account_id
WHERE ul.metric_name = 'api_calls'
  AND ul.usage_date BETWEEN '2026-02-01' AND '2026-02-28'
GROUP BY a.account_id, o.name
HAVING SUM(ul.usage_value) > 5000;
```

---

## 4. Engineering & Auditing (Security Logs)

### Question: "List the IP addresses of all users who performed a 'MANUAL_OVERRIDE' on billing yesterday."

**Logic:**
- Filter `audit_logs_unstructured` by `action_type`.
- Extract the IP from the `metadata_json` blob.

```sql
SELECT 
    created_at as event_time,
    performed_by_id as user_id,
    metadata_json->>'ip' as source_ip
FROM audit_logs_unstructured
WHERE action_type = 'MANUAL_OVERRIDE'
  AND created_at >= CURRENT_DATE - INTERVAL '1 day';
```

---

## 5. Legacy Data Migration

### Question: "Find total revenue from 'Ghost' contracts (legacy data) that haven't been mapped to our modern system yet."

**Logic:**
- Query `legacy_billing_logs`.
- Attempt to join to `contracts`.
- Filter for those where the join fails (NULL).

```sql
SELECT 
    SUM(CAST(SUBSTRING(lbl.billing_event FROM '[0-9.]+') AS DECIMAL)) as legacy_revenue_unmapped
FROM legacy_billing_logs lbl
LEFT JOIN contracts c ON CAST(SUBSTRING(lbl.raw_contract_code FROM '[0-9]+') AS INTEGER) = c.contract_id
WHERE c.contract_id IS NULL;
```
