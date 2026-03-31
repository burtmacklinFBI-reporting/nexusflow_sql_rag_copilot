import psycopg2
import json
import random
import os
from faker import Faker
from datetime import datetime
from dotenv import load_dotenv
import streamlit as st

# Load environment variables
# load_dotenv()

fake = Faker()

def generate_master_data():
    try:
        # useful when you are doiung local testing
        # conn = psycopg2.connect(
        #     user=os.getenv("PG_USER"),
        #     password=os.getenv("PG_PASSWORD"),
        #     host=os.getenv("PG_HOST"),
        #     port=os.getenv("PG_PORT"),
        #     database=os.getenv("PG_DATABASE"),
        #     sslmode="require"
        # )

        # useful when you are using streamlit cloud to deploy
        conn = psycopg2.connect(
        user=st.secrets["PG_USER"],
        password=st.secrets["PG_PASSWORD"],
        host=st.secrets["PG_HOST"],
        port=st.secrets["PG_PORT"],
        database=st.secrets["PG_DATABASE"],
        sslmode="require"
        )


        cursor = conn.cursor()
        print("🚀 Starting Master Data Generation (12 Tables)...")

        # 1. Status Mappings
        status_data = [
            ('payments', 0, 'Failed'),
            ('payments', 1, 'Settled'),
            ('payments', 2, 'Refunded')
        ]
        cursor.executemany("INSERT INTO status_mapping (table_context, code_value, human_label) VALUES (%s, %s, %s)", status_data)

        # 2. Product Metrics Metadata
        metrics_meta = [
            ('api_calls', 'Total API Requests', 'count', True),
            ('storage_gb', 'Data Storage Used', 'gb', True),
            ('seats_active', 'Active User Seats', 'count', False)
        ]
        cursor.executemany("INSERT INTO product_metrics_metadata (internal_name, display_name, unit, is_billable) VALUES (%s, %s, %s, %s)", metrics_meta)

        # 3. Sales Reps & Targets
        reps = []
        for _ in range(5):
            name = fake.name()
            cursor.execute("INSERT INTO sales_reps (name, region, base_quota) VALUES (%s, %s, %s) RETURNING rep_id",
                           (name, fake.word(), random.randint(50000, 100000)))
            rep_id = cursor.fetchone()[0]
            reps.append(rep_id)
            
            # Generate targets for the rep
            for q in [1, 2, 3, 4]:
                cursor.execute("INSERT INTO rep_performance_targets (rep_id, target_year, quarter, revenue_goal) VALUES (%s, %s, %s, %s)",
                               (rep_id, 2026, q, random.randint(20000, 80000)))

        # 4. Organizations, Accounts, Contracts, Invoices, Payments, Usage
        for _ in range(15):
            is_test = 1 if random.random() < 0.2 else 0
            cursor.execute("INSERT INTO organizations (name, industry, is_test_account) VALUES (%s, %s, %s) RETURNING org_id",
                           (fake.company(), fake.job(), is_test))
            org_id = cursor.fetchone()[0]
            
            for _ in range(random.randint(1, 2)):
                cursor.execute("INSERT INTO accounts (org_id, region) VALUES (%s, %s) RETURNING account_id",
                               (org_id, random.choice(['North', 'South', 'East', 'West', 'EMEA', 'APAC'])))
                acc_id = cursor.fetchone()[0]

                # Usage Ledger (10 entries per account)
                for _ in range(10):
                    cursor.execute("INSERT INTO usage_ledger (account_id, metric_name, usage_value, usage_date) VALUES (%s, %s, %s, %s)",
                                   (acc_id, random.choice(['api_calls', 'storage_gb']), random.randint(100, 5000), fake.date_this_month()))

                # Contracts
                cursor.execute("INSERT INTO contracts (account_id, total_contract_value, signed_date) VALUES (%s, %s, %s) RETURNING contract_id",
                               (acc_id, random.randint(5000, 100000), fake.date_between(start_date='-1y', end_date='today')))
                contract_id = cursor.fetchone()[0]

                # Invoices & Payments
                for m in range(1, 4): # 3 months of billing
                    cursor.execute("INSERT INTO invoices (contract_id, amount_due, billing_month, billing_year, invoice_status) VALUES (%s, %s, %s, %s, %s) RETURNING invoice_id",
                                   (contract_id, random.randint(1000, 5000), m, 2026, 'ISSUED'))
                    
                    # Payment Trap: Mix of clean and messy IDs
                    contract_ref = str(contract_id) if random.random() > 0.2 else f"CTX-{contract_id}"
                    cursor.execute("INSERT INTO payments (contract_ref_id, amount_paid, payment_date, status_code) VALUES (%s, %s, %s, %s)",
                                   (contract_ref, random.randint(500, 5000), fake.date_this_year(), random.choice([0, 1, 2])))

        # 5. Legacy Logs (Unjoinable)
        # Create a specific matching legacy record for Hard Case 2
        cursor.execute("INSERT INTO legacy_billing_logs (raw_contract_code, billing_event, event_timestamp) VALUES (%s, %s, %s)",
                       ("OLD_REF_40", "Legacy Import: 1500.00 USD", datetime.now()))
        
        for _ in range(20):
            cursor.execute("INSERT INTO legacy_billing_logs (raw_contract_code, billing_event, event_timestamp) VALUES (%s, %s, %s)",
                           (f"OLD_REF_{random.randint(1000, 9999)}", "Legacy Import", datetime.now()))

        # 6. Audit Logs (JSONB Trap)
        heavy_hitter_ip = "192.168.1.100"
        for i in range(30):
            action = random.choice(["SYSTEM_SYNC", "MANUAL_OVERRIDE", "AUTH_FAILURE"])
            ip = heavy_hitter_ip if (action == "MANUAL_OVERRIDE" and i % 2 == 0) else fake.ipv4()
            audit_meta = {"ip": ip, "agent": fake.user_agent(), "flags": ["audit", "system"]}
            cursor.execute("INSERT INTO audit_logs_unstructured (performed_by_id, action_type, metadata_json) VALUES (%s, %s, %s)",
                           (random.randint(1, 100), action, json.dumps(audit_meta)))

        conn.commit()
        print("✅ Success! All 12 tables have been populated with complex data.")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'conn' in locals():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    generate_master_data()
