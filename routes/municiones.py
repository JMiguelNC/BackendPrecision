from fastapi import APIRouter
from database.connection import get_connection

router = APIRouter()

@router.get("/municiones")
def get_municiones():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, calibre FROM municion")
    municiones = [{"id": r[0], "calibre": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return municiones
