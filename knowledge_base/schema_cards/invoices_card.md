# Table: invoices
**Domain:** Billing
**Grain:** One row per billing cycle (monthly) per contract.

### Key Columns
- `billing_month`: Stored as an Integer (1-12).
- `invoice_status`: Includes 'VOID', 'ISSUED', 'SENT'. 

### Joins & Caveats
- **Revenue Trap:** An invoice being 'ISSUED' does not mean revenue was collected. For actual cash flow, always refer to the `payments` table.