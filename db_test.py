# Now that I have created a docker container using the docker container command, now I want to test it whether my Python can actually talk to it or not.


import psycopg2
import os
from dotenv import load_dotenv
import streamlit as st
# Load environment variables
load_dotenv()

try:
    # useful when youa re doiung local testing
    connection = psycopg2.connect(
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
        database=os.getenv("PG_DATABASE"),
        sslmode="require"
    )
    
    cursor = connection.cursor()
    cursor.execute("SELECT version();")
    record = cursor.fetchone()
    print(f"✅ Success! You are connected to: {record}") # Got a sucess message looks like my thing is connected as I got the version.
    
except Exception as error:
    print(f"❌ Connection failed: {error}")

finally:
    if 'connection' in locals():
        cursor.close()
        connection.close()