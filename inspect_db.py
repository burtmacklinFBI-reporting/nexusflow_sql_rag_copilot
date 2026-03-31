import psycopg2
import os
from dotenv import load_dotenv
import streamlit as st
# Load environment variables
# load_dotenv()

def inspect_database():
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

        # Get all table names
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            print("\n" + "="*50)
            print("TABLE: " + table.upper())
            print("="*50)

            # 1. Show Columns and Types
            cursor.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position;")
            columns = cursor.fetchall()
            col_info = [col[0] + " (" + col[1] + ")" for col in columns]
            print("STRUCTURE: " + " | ".join(col_info))
            print("-" * 50)

            # 2. Show Sample Data (First 3 rows)
            cursor.execute(f"SELECT * FROM {table} LIMIT 3;")
            rows = cursor.fetchall()
            
            if not rows:
                print("[No data found]")
            else:
                for row in rows:
                    print(row)

    except Exception as e:
        print("❌ Error: " + str(e))
    finally:
        if 'conn' in locals():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    inspect_database()