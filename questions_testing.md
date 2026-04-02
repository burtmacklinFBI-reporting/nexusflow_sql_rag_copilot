


• Best first chat test prompt:
  "Explain what a lifecycle stage means in our RevOps
  process." 

  What does 'Optum Standard' mean at NexusFlow?


  For finance reporting at NexusFlow, explain the timezone policy, fiscal year rule,
  and how they affect interpreting Gross Revenue (Billed).


  "If timestamps are in UTC but finance
  │ reports are in EST, how should month-end revenue be interpreted around midnight
  │ on the last day of a month?" { always test these different date formats so that we can check them.}


  If timestamps are in UTC but finance reports are in EST, how should month-
    end revenue be interpreted around midnight on the last day of a month?



    -------------- for sql 


   1)  "query": "What is the total settled payment amount in 2026?
   2)  Which accounts exceeded their API call limit of 5000 in February 2026?",
   3) "What is our total Net Realized Revenue
  │ (NRR) for the year 2026, excluding test accounts?


  ---------------- hybrid 

  For NexusFlow finance reporting, what is the timezone policy for month-end, and what is the total settled payment amount in 2026 excluding test accounts?


  ------------ chat histoty working or not

     1. "In NexusFlow finance policy, does a payment at 2026-03-01 03:00
      UTC belong to February or March in EST reporting?"
   2. "Great. For that same month, what is the total settled payment
      amount excluding test accounts?"


## Additional generated test questions

### Chat intent

1. "What does Optum Standard mean at NexusFlow, and when should it be applied?"
2. "Explain the difference between Gross Revenue (Billed) and Net Realized Revenue at NexusFlow."
3. "What does 'The Grain' mean in the NexusFlow handbook, and why does it matter for analysis?"
4. "Why can't we join daily usage directly to monthly invoices without aggregation?"
5. "How should finance interpret timestamps stored in UTC when month-end reporting is done in EST?"
6. "What is the refund policy for cohort reporting at NexusFlow?"
7. "Explain the pro-ration policy for contracts signed before and after the 15th of the month."
8. "What are Ghost contracts in NexusFlow, and why are they tricky to analyze?"
9. "What are the territory code mappings used by sales reps?"
10. "What does the handbook say about test accounts in executive reporting?"

### SQL intent

1. "What is the total settled payment amount in Q1 2026 excluding test accounts?"
2. "What is our total Gross Revenue (Billed) in 2026 excluding test accounts?"
3. "What is our total Net Realized Revenue in 2026 excluding test accounts?"
4. "List the organizations with refunded payments in 2026 and the total refunded amount for each."
5. "Which accounts exceeded 5000 API calls in February 2026?"
6. "Which accounts had the highest billable usage in March 2026?"
7. "Show the top 10 organizations by settled payment amount in 2026 excluding test accounts."
8. "How many real customer organizations do we have by industry?"
9. "List all payments with status codes that are not 0, 1, or 2."
10. "Decode the payment status codes using the status_mapping table."
11. "Find the total amount of settled payments by month in 2026 excluding test accounts."
12. "What is the total amount invoiced in Q1 2026, grouped by billing month?"
13. "Show all MANUAL_OVERRIDE audit events with their timestamp, user id, and source IP."
14. "How many AUTH_FAILURE events do we have in the audit logs?"
15. "Find total revenue from Ghost contracts that do not map to any contract in the current system."
16. "Which contracts were signed more than 12 months ago and may represent churn risk?"
17. "Show active seats usage by account for February 2026."
18. "Which organizations have both invoices and settled payments in 2026, and what are the totals for each?"

### Hybrid intent

1. "For Board reporting, what is our Q1 2026 performance against target after applying the migration adjustment?"
2. "What is Stacy Kelly's Q1 2026 commission using her comp plan rules and her actual revenue from the database?"
3. "What is Dylan Foley's Q1 2026 commission, including any guaranteed floor if applicable?"
4. "For NexusFlow finance reporting, explain the timezone policy and give me the total settled payment amount in 2026 excluding test accounts."
5. "What is the company's Q2 2026 target attainment using actual settled payments from the database and the board targets document?"
6. "For Board Target Attainment, what is Q1 2026 actual revenue after excluding Bauer Ltd and applying the migration credit?"
7. "Show West Coast rep revenue for Q1 2026 and compare it against the applicable target or plan context."
8. "Using the handbook definition of billable usage, which accounts generated the most billable usage in February 2026?"
9. "Compare Gross Revenue (Billed) and Net Realized Revenue for 2026, and explain the business difference between them."
10. "Using the territory code mapping rules, what revenue should be attributed to the West Coast region in Q1 2026?"
11. "Which organizations should be excluded from board target attainment, and what is the adjusted 2026 revenue after applying that rule?"
12. "What is Karen Wilson's Q1 2026 commission based on her assigned plan and actual revenue?"

### Ambiguous / intent-boundary tests

1. "How is revenue doing this year?"
2. "Tell me about payments for Bauer."
3. "What happened with billing around the end of February?"
4. "Can you check whether West Coast performance looks healthy?"
5. "Show me the reporting logic for revenue."
6. "What should finance look at for Q1?"
7. "Do we have any billing issues from migration?"
8. "Give me the customer payment picture for March."

### Follow-up / chat history tests

Sequence 1:
1. "What is the total settled payment amount in Q1 2026 excluding test accounts?"
2. "Now break that down by month."
3. "Which month was highest?"

Sequence 2:
1. "Explain what Optum Standard means at NexusFlow."
2. "Great, now calculate 2026 NRR using that standard."

Sequence 3:
1. "Which accounts exceeded 5000 API calls in February 2026?"
2. "Of those, which ones are test accounts?"
3. "Now remove the test accounts and give me the final list."

Sequence 4:
1. "What is Stacy Kelly's Q1 2026 revenue attainment?"
2. "Based on that, what commission plan should apply?"
3. "What is her final commission amount?"

Sequence 5:
1. "In finance policy, does a payment recorded at 2026-04-01 02:30 UTC belong to March or April in EST reporting?"
2. "Using that reporting logic, what is the total settled payment amount for that month excluding test accounts?"

### Edge-case prompts

1. "A payment was recorded at 2026-01-01 02:00 UTC. For NexusFlow finance reporting, which year should it belong to in EST?"
2. "If a user asks for executive reporting, what exact filters should be applied before calculating revenue?"
3. "Find any payment rows where the contract reference would fail a clean integer join."
4. "Show invoice totals and usage totals together for February 2026, but do it at the correct grain."
5. "What billable metrics exist, and how should they be used in overage analysis?"
6. "If a payment uses an unknown status code, how should the system determine its meaning?"
7. "Which audit log events are considered high priority according to the handbook, and how many do we have?"
8. "Does Bauer Ltd count in board target attainment? Explain the rule and apply it to Q1 2026 actuals."
