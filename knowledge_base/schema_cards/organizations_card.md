# Table: organizations
**Domain:** CRM / Core
**Grain:** Parent company level.

### Key Columns
- `is_test_account` (INT): 1 for internal/testing, 0 for real customers.
- **Rule:** Every revenue query must filter `where is_test_account = 0`.