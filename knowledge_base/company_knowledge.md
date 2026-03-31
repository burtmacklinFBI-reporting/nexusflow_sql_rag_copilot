# NexusFlow: AI Employee Handbook & Business Logic

**Confidential: Internal Use Only**
**Version:** 2.0 (Post-2022 Acquisition)

---

## 1. Company Profile
**Name:** NexusFlow
**Industry:** B2B SaaS (Revenue Operations Automation)
**Market:** Enterprise (US & EMEA)
**Mission:** unifying messy revenue data for high-growth companies.

### Core Architecture
Our internal data is modeled to reflect the complexity we solve for clients. It is **intentionally hostile** in places (legacy strings, JSON blobs) to ensure our internal tools (and you, the AI) are robust.

### Business Model (Hybrid Pricing)
We operate on a **Base + Overage** model:
1.  **Base Platform Fee:** Fixed `total_contract_value` spread across the contract term.
2.  **Usage Overages:** Billed monthly based on `usage_ledger` metrics that exceed the plan limit.
    *   *Note:* The `invoices.amount_due` is the *final sum* of the Base Fee + Overages for that month.

---

## 2. The "Nexus" Lexicon (Standard Terminology)

| Term | Definition | SQL Context |
| :--- | :--- | :--- |
| **"Optum Standard"** | The highest tier of data hygiene. Requests for "Clean Data" or "Executive Reporting" MUST apply this standard. | Filter: `organizations.is_test_account = 0` AND `payments.status_code = 1` |
| **"Ghost" Contracts** | Historical revenue records from our 2022 acquisition that lack modern metadata. | Source: `legacy_billing_logs`. Link via `raw_contract_code` string cleaning. |
| **"The Grain"** | The specific level of detail for a table. **CRITICAL:** Never join tables of different grains (e.g., Daily Usage vs. Monthly Invoices) without aggregation. | See: `usage_ledger` (Daily) vs `invoices` (Monthly). |
| **"Settled"** | Money actually in the bank. The *only* status that counts for Revenue. | `payments.status_code = 1` |
| **"Territory Codes"** | Internal code names for Sales Regions used in `sales_reps`. | 'page' = **West Coast**, 'building' = **East Coast**, 'entire' = **EMEA/Global**. |

---

## 3. Key Performance Indicators (KPIs) & Metrics

### A. Revenue Metrics (Finance Domain)

**1. Gross Revenue (Billed)**
*   **Definition:** Total amount invoiced to customers, regardless of payment.
*   **Logic:** `SUM(amount_due)` from `invoices`.
*   **Caveat:** "Issued" invoices are not cash. Do not use for Cash Flow reports.

**2. Net Realized Revenue (NRR) - *The Golden Metric***
*   **Definition:** Actual cash collected (minus refunds).
*   **Formula:** `SUM(amount_paid WHERE status_code = 1) - SUM(amount_paid WHERE status_code = 2)`.
*   **Source:** `payments` table.

**3. Churned Revenue**
*   **Definition:** Revenue lost when a contract expires and is not renewed.
*   **Logic:** Since `contracts` table lacks an explicit `end_date`, assume a **Standard 12-Month Term**.
    *   *Formula:* Identify accounts where `MAX(signed_date) < CURRENT_DATE - INTERVAL '1 year'`.

### B. Product Usage Metrics (Engineering Domain)

**1. Billable Usage**
*   **Definition:** Usage that contributes to overage charges.
*   **Logic:** `SUM(usage_value)` from `usage_ledger` joined to `product_metrics_metadata` where `is_billable = TRUE`.
*   **Aggregation Rule:** You must `SUM` daily usage by `billing_month` before joining to Invoices.

**2. Active Seats**
*   **Definition:** The number of unique users logged in.
*   **Logic:** Query `usage_ledger` where `metric_name = 'seats_active'`.

---

## 4. Standard Operating Procedures (Data Traps)

**SOP-000: The "Status Code" Truth**
*   **Note:** While we list common codes below (0, 1, 2), the **Ultimate Truth** lives in the `status_mapping` table. If you encounter an unknown code (e.g., 3), query that table to decode it.

**SOP-001: The "Contract Ref" Handshake**
*   **Issue:** The `payments` table uses a VARCHAR (`contract_ref_id`) to link to the INT `contracts.contract_id`.
*   **Procedure:** You MUST cast the column: `CAST(payments.contract_ref_id AS INTEGER) = contracts.contract_id`.

**SOP-002: Legacy Data Integration**
*   **Issue:** `legacy_billing_logs` uses messy strings like `OLD_REF_123`.
*   **Procedure:** 
    1.  Extract the number: `SUBSTRING(raw_contract_code FROM '[0-9]+')`.
    2.  Cast to Integer.
    3.  Join to `contracts.contract_id`.

**SOP-003: Unstructured Audit Logs**
*   **Issue:** Critical security tags are hidden inside the `metadata_json` JSONB column.
*   **Procedure:** Use the arrow operator `->>` for text extraction. Example: `metadata_json->>'ip'` to get the IP address.
*   **Known Event Types (`action_type`):**
    *   `SYSTEM_SYNC`: Automated background jobs (Low Priority).
    *   `MANUAL_OVERRIDE`: Human intervention in billing (High Priority/Audit).
    *   `AUTH_FAILURE`: Failed login attempts.

---

## 5. Organizational Policies

*   **Timezone Policy:** All database timestamps (`created_at`, `event_timestamp`) are stored in **UTC**. Reports for Finance must be converted to **EST (UTC-5)** before aggregation.
*   **Fiscal Year:** Follows the Calendar Year (Jan 1 - Dec 31).
*   **Currency:** All monetary values are **USD**. No conversion required.
*   **Pro-ration Policy:** We do **NOT** pro-rate. Contracts signed after the 15th of the month are billed starting the *following* month. Contracts signed on/before the 15th are billed for the full month.
*   **Refunds:** Must be subtracted from the period they were *originally paid*, to accurately reflect the net value of that period's cohort.
*   **Test Data:** All Executive/Board reports must strictly exclude `is_test_account = 1`. Engineering/Debugging reports may include them but must label them clearly.

---

## 6. Field Glossary (Plain English Data Dictionary)

| Field Name | Table(s) | Plain English Definition |
| :--- | :--- | :--- |
| `is_test_account` | `organizations` | A flag where `1` means the company is internal (us) or a test user, and `0` means it's a real, paying customer. |
| `region` | `accounts`, `sales_reps` | The geographical territory (e.g., 'North', 'EMEA'). Note: Sales Rep regions might be named differently (e.g., 'building', 'entire') than Account regions. |
| `total_contract_value` | `contracts` | The maximum possible money we can earn from a contract over its entire lifetime. |
| `amount_due` | `invoices` | The specific amount of money we asked the customer to pay for a particular month. |
| `billing_month` | `invoices` | The month (1-12) that the bill covers. 1 = January, 12 = December. |
| `status_code` | `payments` | The outcome of a credit card/bank transfer: `0` (Failed), `1` (Success/Settled), `2` (Refunded). |
| `usage_value` | `usage_ledger` | A number representing how much of a product was used (e.g., 5000 API calls or 10 GB of storage). |
| `is_billable` | `product_metrics_metadata` | A Yes/No flag. If No, we track the usage but don't charge the customer for it. |
| `base_quota` | `sales_reps` | The minimum amount of sales (in dollars) a salesperson is expected to close in a year. |
| `revenue_goal` | `rep_performance_targets` | The specific dollar target a salesperson needs to hit for a single 3-month quarter. |
| `metadata_json` | `audit_logs_unstructured` | A "digital bucket" containing technical details like IP addresses and browser info, stored in a flexible JSON format. |
