from fastapi import APIRouter, UploadFile, Form, Body
from database.connection import get_connection
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from psycopg2 import errors
import base64

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- LOGIN ---
@router.post("/login")
async def login(data: dict = Body(...)):
    try:
        usuario = data.get("usuario")
        contrasena = data.get("contrasena")

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

        cur.close()
        conn.close()

        if not user:
            return JSONResponse({"success": False, "message": "Usuario no encontrado"}, status_code=400)

        if user[2] != "true":
            return JSONResponse({"success": False, "message": "Usuario desactivado"}, status_code=400)

        if not pwd_context.verify(contrasena, user[1]):
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
    except Exception as e:
        if conn:
            conn.rollback()
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


# --- LISTAR USUARIOS ---
@router.get("/")
def listar_usuarios():
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
            foto_base64 = None
            if u[11]:
                foto_base64 = "data:image/jpeg;base64," + base64.b64encode(u[11]).decode("utf-8")

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
    except Exception as e:
        if conn:
            conn.rollback()
        return JSONResponse({"error": str(e)}, status_code=400)


# --- ACTUALIZAR USUARIO ---
@router.put("/{id}")
async def actualizar_usuario(
    id: int,
    usuario: str = Form(...),
    correo: str = Form(...),
    foto: UploadFile = None
):
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

        if isinstance(e, errors.UniqueViolation):
            if "usuario_usuario_key" in str(e):
                return JSONResponse({"error": "El nombre de usuario ya existe"}, status_code=400)
            elif "usuario_correo_key" in str(e):
                return JSONResponse({"error": "El correo ya está registrado"}, status_code=400)

        return JSONResponse({"error": str(e)}, status_code=400)


# --- ELIMINAR USUARIO ---
@router.delete("/{id}")
def eliminar_usuario(id: int):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE usuario
            SET estado='false'
            WHERE id=%s
        """, (id,))

        conn.commit()
        cur.close()
        conn.close()

        return JSONResponse({"mensaje": "Usuario desactivado correctamente"})
    except Exception as e:
        if conn:
            conn.rollback()
        return JSONResponse({"error": str(e)}, status_code=400)
