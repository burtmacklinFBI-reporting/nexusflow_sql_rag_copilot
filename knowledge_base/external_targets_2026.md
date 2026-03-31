# 2026 Global Sales Targets & Quotas (Extended for RAG Testing)

**Source:** Board of Directors Meeting (Dec 2025)
**Status:** Active
**Purpose:** Executive Performance Reviews and "Sales Efficiency" analysis.

## 1. Quarterly Revenue Goals (Company-Wide)
These are top-down targets. Compare these against the sum of `payments` (status=1).
- **Q1 2026:** $500,000
- **Q2 2026:** $750,000
- **Q3 2026:** $1,000,000
- **Q4 2026:** $1,500,000

## 2. Regional Multipliers & Mapping Rules
When calculating "Weighted Revenue," use these multipliers.

| Global Region | Multiplier | DB `region` Mapping |
| :--- | :--- | :--- |
| **APAC** | 1.2x | (None currently in Faker data) |
| **EMEA** | 1.0x | `entire` |
| **North America** | 0.8x | `page` (West), `building` (East), `North` |

**Conflict Resolution:** If a record matches multiple regions, the **EMEA (1.0x)** multiplier takes precedence.

## 3. The "Strategy" Layer (RAG-Only Context)
The following rules exist **only in this document** and are not reflected in SQL constraints.

### A. Strategic Account Exclusions
Revenue from the following Organizations should be **excluded** from "Board Target Attainment" calculations (they are managed by the CEO directly):
- *Organization Name:* "Bauer Ltd" (Org ID: 2)
- *Reason:* Internal test account and Strategic Partner.

### B. Q1 Special "Migration" Adjustment
Due to the billing system migration in January, the Board has authorized a **one-time $25,000 credit** to be added to the "Actuals" for Q1 2026.
- **Rule:** `Total Q1 Performance = (SQL NRR) + $25,000`.

### C. Performance Tiers
- **Tier 1 (Explorer):** < 80% of target (No bonus)
- **Tier 2 (Achiever):** 80% - 100% of target (5% commission)
- **Tier 3 (President’s Club):** > 100% of target (12% commission)

## 4. Testing Edge Cases
- **Date Range:** The 2026 targets apply strictly to payments made between `2026-01-01` and `2026-12-31`.
- **Currency:** All targets are in USD.