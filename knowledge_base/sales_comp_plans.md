# FY2026 Sales Compensation & Roster Mapping

**Confidential: HR & Sales Ops Only**
**Effective Date:** Jan 1, 2026

## 1. Compensation Plan Tiers
There are two distinct commission structures based on role seniority.

### Plan A: "Standard Rep" (High Base, Low Variable)
*   **Target:** For Junior/Mid-level reps.
*   **Commission Rate:** Flat **8%** on all revenue above 80% quota attainment.
*   **Accelerator:** None.

### Plan B: "Executive Closer" (Low Base, High Variable)
*   **Target:** For Senior reps handling strategic accounts.
*   **Commission Rate:** **15%** on all revenue above 100% quota attainment.
*   **Accelerator:** If attainment > 120%, the rate jumps to **20%** retroactively for the whole quarter.

## 2. Active Rep Roster & Plan Assignment
This mapping links the SQL `sales_reps` table to their HR plan.

| Rep Name (SQL) | Role | Plan Assignment | Notes |
| :--- | :--- | :--- | :--- |
| **Stacy Kelly** | Senior Account Exec | **Plan B (Executive)** | Focuses on 'Page' (West) territory. |
| **Karen Wilson** | Account Manager | **Plan A (Standard)** | Handling 'Building' (East) renewals. |
| **Dylan Foley** | VP of Sales | **Plan B (Executive)** | Validates 'Entire' (EMEA) deals. |

## 3. Special Commission Rules
*   **Legacy Exception:** Dylan Foley is "grandfathered" into a **guaranteed floor**. Even if he misses quota, he receives a minimum $2,000 bonus per quarter.
*   **Split Deals:** If two reps share a region (e.g., North), the commission is split 50/50 unless specified otherwise in the `audit_logs`.
