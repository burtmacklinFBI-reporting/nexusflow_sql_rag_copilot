# Table: rep_performance_targets
**Domain:** Sales Operations
**Grain:** Quarterly goal per rep.

### Joins
- Use `rep_id` to join with `sales_reps`.

### Calculations
- **Annual Goals:** To get the annual target, `SUM(revenue_goal)` grouping by `rep_id` and `target_year`. Do not average them.