# Table: sales_reps
**Domain:** Sales Operations
**Grain:** One row per employee.

### Columns
- `region` (VARCHAR): The internal territory code. 
    - **Values:** 'page' (West), 'building' (East), 'entire' (EMEA/Global).
- **Semantic Join Trap:** No direct foreign key to `accounts`. Use the `region` column for a semantic match (see `accounts_cards.md` for the mapping logic).

### Joins
- **Performance:** Joins to `rep_performance_targets` on `rep_id`.
- **Audit Ambiguity:** `audit_logs_unstructured.performed_by_id` *might* reference a `rep_id`, but it could also be a system user. verify context before joining.