# Table: payments
**Domain:** Billing & Revenue
**Grain:** One row per individual payment transaction.

### Purpose
Records all incoming cash flow from customers. This is the source of truth for "Collected Revenue."

### Key Columns
- `contract_ref_id` (VARCHAR): A reference to the contract. **CRITICAL:** This is stored as a string. To join with `contracts.contract_id`, you MUST use `CAST(contract_ref_id AS INTEGER)`.
- `status_code` (INT): Numeric code for payment state. 
    - 0 = Failed
    - 1 = Settled (Successful)
    - 2 = Refunded

### Joins & Caveats
- **Join Trap:** Do not join directly to `organizations`. You must go through `contracts` -> `accounts` -> `organizations`.
- **Filtering:** For "Total Revenue" calculations, always filter `status_code = 1`.
- **Contract Link SOP:** The `contract_ref_id` column contains messy strings (e.g., '1', 'CTX-1'). 
    - **WRONG:** `CAST(contract_ref_id AS INTEGER)` (This will crash).
    - **RIGHT:** `CAST(SUBSTRING(contract_ref_id FROM '[0-9]+') AS INTEGER)` (Extracts the ID safely).