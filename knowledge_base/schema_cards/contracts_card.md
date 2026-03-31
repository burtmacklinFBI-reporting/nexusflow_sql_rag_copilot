# Table: contracts
**Domain:** Sales
**Grain:** Individual legal agreement.

### Joins
- **Downstream:** Joins to `invoices` on `contract_id`.
- **Payments Trap:** Joins to `payments` via `payment.contract_ref_id`. Requires `CAST(contract_ref_id AS INT) = contracts.contract_id`.
- **Legacy Trap:** Joins to `legacy_billing_logs` via `raw_contract_code`. Requires string cleaning and casting.
- **Note:** `contract_id` is the primary key (INT).