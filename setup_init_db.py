import psycopg2
import os
from dotenv import load_dotenv
import streamlit as st

# Load environment variables
# load_dotenv()

def run_sql_schema():
    # 1. Connection Config --> use them when you are running locally
    # connection_params = {
    #     "user": os.getenv("PG_USER"),
    #     "password": os.getenv("PG_PASSWORD"),
    #     "host": os.getenv("PG_HOST"),
    #     "port": os.getenv("PG_PORT"),
    #     "database": os.getenv("PG_DATABASE"),
    #     "sslmode": "require"
    # }

    connection_params = {
    "user": st.secrets["PG_USER"],
    "password": st.secrets["PG_PASSWORD"],
    "host": st.secrets["PG_HOST"],
    "port": st.secrets["PG_PORT"],
    "database": st.secrets["PG_DATABASE"],
    "sslmode": "require"
}

    try:
        # 2. Connect to the DB
        conn = psycopg2.connect(**connection_params)
        conn.autocommit = True # Ensures commands run immediately
        cursor = conn.cursor()

        print("🚀 Connected to Postgres. Starting Schema Build...")

        # 3. Read the .sql file you created earlier
        # Make sure 'init_db.sql' is in the same folder as this script
        with open('init_db.sql', 'r') as f:
            sql_commands = f.read()

        # 4. Execute the SQL
        # We split by semicolon to execute commands one by one
        cursor.execute(sql_commands)
        
        # Confirmation message: Indicates successful execution of SQL schema commands.
        print("✅ Schema created successfully!")

        # 5. Verify tables exist
        # Execute SQL query to get table names from the 'public' schema, information_schema is the ones in which all the tables will be created if we do not specify the schema and then table_name will give all the views, tables and all present in the directory.
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public';
        """)
        # Fetch all table names from the query result.
        tables = cursor.fetchall()
        # Print a header for the table list.
        print("\n📊 Current Tables in Database:")
        # Iterate through each fetched table name.
        for t in tables:
            # Print the table name, formatted as a list item.
            print(f" - {t[0]}")

    except Exception as error:
        print(f"❌ Error during schema build: {error}")

    finally:
        # Ensure connection was established before trying to close.
        if 'conn' in locals():
            # Close the database cursor.
            cursor.close()
            conn.close()

if __name__ == "__main__":
    run_sql_schema()