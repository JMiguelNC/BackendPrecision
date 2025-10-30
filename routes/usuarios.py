from fastapi import APIRouter, UploadFile, Form, Body
from fastapi.responses import JSONResponse
from database.connection import get_connection
from passlib.context import CryptContext
from psycopg2 import errors
import base64
import traceback
import logging
import bcrypt
from passlib.hash import bcrypt as passlib_bcrypt

passlib_bcrypt.set_backend("bcrypt")

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger(__name__)

@router.post("/login")
async def login(data: dict = Body(...)):
    conn = None
    try:
        usuario = data.get("usuario")
        contrasena = data.get("contrasena")
        if not usuario or not contrasena:
            return JSONResponse({"success": False, "message": "Debe ingresar usuario y contraseña"}, status_code=400)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.contrasena, u.estado, u.rol_id, u.primer_inicio,
                   u.nombres, u.ap_paterno, u.ap_materno, r.nombre_rol
            FROM usuario u
            JOIN rol r ON u.rol_id = r.id
            WHERE u.usuario=%s
        """, (usuario,))
        user = cur.fetchone()

        if not user:
            cur.close()
            conn.close()
            return JSONResponse({"success": False, "message": "Usuario no encontrado"}, status_code=400)
        if user[2] != "true":
            cur.close()
            conn.close()
            return JSONResponse({"success": False, "message": "Usuario desactivado"}, status_code=400)

        stored_hash = user[1]
        valid = pwd_context.verify(contrasena, stored_hash)

        if valid and pwd_context.needs_update(stored_hash):
            new_hash = pwd_context.hash(contrasena)
            cur.execute("UPDATE usuario SET contrasena=%s WHERE id=%s", (new_hash, user[0]))
            conn.commit()
            stored_hash = new_hash

        cur.close()
        conn.close()

        if not valid:
            return JSONResponse({"success": False, "message": "Contraseña incorrecta"}, status_code=400)

        return JSONResponse({
            "success": True,
            "message": "Inicio de sesión exitoso",
            "user": {
                "id": user[0],
                "rol_id": user[3],
                "rol_nombre": user[8],
                "primer_inicio": user[4],
                "nombres": user[5],
                "ap_paterno": user[6],
                "ap_materno": user[7]
            }
        })

    except Exception:
        if conn:
            conn.rollback()
            conn.close()
        logger.error("Error en /usuarios/login:\n%s", traceback.format_exc())
        return JSONResponse({"success": False, "message": "Error interno del servidor"}, status_code=500)

@router.get("/")
def listar_usuarios():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.nombres, u.ap_paterno, u.ap_materno, u.ci, u.fecha_nacimiento,
                   u.usuario, u.correo, u.celular, u.rango, r.nombre_rol, u.foto, u.estado
            FROM usuario u
            JOIN rol r ON u.rol_id = r.id
            ORDER BY u.id
        """)
        usuarios = cur.fetchall()
        cur.close()
        conn.close()

        lista_usuarios = []
        for u in usuarios:
            foto_base64 = "data:image/jpeg;base64," + base64.b64encode(u[11]).decode("utf-8") if u[11] else None
            lista_usuarios.append({
                "id": u[0],
                "nombres": u[1],
                "apellidoPaterno": u[2],
                "apellidoMaterno": u[3],
                "ci": u[4],
                "fechaNacimiento": u[5].strftime("%Y-%m-%d") if u[5] else None,
                "usuario": u[6],
                "correo": u[7],
                "celular": u[8],
                "rango": u[9],
                "rol": u[10],
                "foto": foto_base64,
                "estado": True if u[12] == "true" else False
            })
        return lista_usuarios
    except Exception:
        if conn:
            conn.rollback()
            conn.close()
        logger.error("Error en listar_usuarios:\n%s", traceback.format_exc())
        return JSONResponse({"error": "Error interno del servidor"}, status_code=500)

@router.put("/{id}")
async def actualizar_usuario(id: int, usuario: str = Form(...), correo: str = Form(...), foto: UploadFile = None):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        foto_bytes = await foto.read() if foto else None
        if foto_bytes:
            cur.execute("""
                UPDATE usuario
                SET usuario=%s, correo=%s, foto=%s
                WHERE id=%s
            """, (usuario, correo, foto_bytes, id))
        else:
            cur.execute("""
                UPDATE usuario
                SET usuario=%s, correo=%s
                WHERE id=%s
            """, (usuario, correo, id))
        conn.commit()
        cur.close()
        conn.close()
        return JSONResponse({"mensaje": "Usuario actualizado correctamente"})
    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        logger.error("Error en actualizar_usuario:\n%s", traceback.format_exc())
        if isinstance(e, errors.UniqueViolation):
            if "usuario_usuario_key" in str(e):
                return JSONResponse({"error": "El nombre de usuario ya existe"}, status_code=400)
            elif "usuario_correo_key" in str(e):
                return JSONResponse({"error": "El correo ya está registrado"}, status_code=400)
        return JSONResponse({"error": "Error interno del servidor"}, status_code=500)

@router.delete("/{id}")
def eliminar_usuario(id: int):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE usuario SET estado='false' WHERE id=%s", (id,))
        conn.commit()
        cur.close()
        conn.close()
        return JSONResponse({"mensaje": "Usuario desactivado correctamente"})
    except Exception:
        if conn:
            conn.rollback()
            conn.close()
        logger.error("Error en eliminar_usuario:\n%s", traceback.format_exc())
        return JSONResponse({"error": "Error interno del servidor"}, status_code=500)
