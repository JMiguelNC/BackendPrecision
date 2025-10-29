from fastapi import APIRouter
from database.connection import get_connection

router = APIRouter()

@router.get("/roles")
def get_roles():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre_rol FROM rol")
    roles = [{"id": r[0], "nombre_rol": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return roles