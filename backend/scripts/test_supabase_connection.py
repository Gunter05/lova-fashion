"""
Quick smoke test: run this after filling in backend/.env to confirm both the
Postgres connection and the Supabase Storage client work before building on top of it.

Usage:
    cd backend
    python scripts/test_supabase_connection.py
"""
import os

import psycopg2
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()


def test_database():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("select count(*) from fabric_category;")
    count = cur.fetchone()[0]
    print(f"[OK] Connected to Postgres. fabric_category rows: {count}")
    cur.close()
    conn.close()


def test_storage():
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    buckets = supabase.storage.list_buckets()
    names = [b.name for b in buckets]
    print(f"[OK] Connected to Supabase Storage. Buckets: {names}")
    if "fabric-photos" not in names:
        print("[WARN] 'fabric-photos' bucket not found — did you create it in step 4?")


if __name__ == "__main__":
    test_database()
    test_storage()