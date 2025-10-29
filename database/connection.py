import os
import psycopg2

def get_connection():
    try:
        conn = psycopg2.connect(os.environ.get("DATABASE_URL"))
        return conn
    except Exception as e:
        print("Error al conectar con PostgreSQL:", e)
        return None
