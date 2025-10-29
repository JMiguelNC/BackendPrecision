from fastapi import APIRouter, Body
from database.connection import get_connection
from fastapi.responses import JSONResponse
import base64

router = APIRouter()

@router.post("/guardar_prueba")
def guardar_prueba(data: dict = Body(...)):
    fecha = data.get("fecha")
    ordentiro = data.get("ordentiro")
    lote = data.get("lote")
    tamano = data.get("tamano")
    muestra = data.get("muestra")
    armamento = data.get("armamento")
    distancia_tiro = data.get("distancia_tiro")
    base = data.get("base")
    altura = data.get("altura")
    area_impactos = data.get("area_impactos")
    decision = data.get("decision")
    id_municion = data.get("id_municion")
    series = data.get("series", [])
    usuarios = data.get("usuarios", [])
    foto_base64 = data.get("foto")
    informe_base64 = data.get("informe")

    if not fecha:
        return JSONResponse({"error": "No se proporcionó la fecha"}, status_code=400)

    foto_bytes = None
    if foto_base64:
        try:
            foto_bytes = base64.b64decode(foto_base64)
        except Exception as e:
            return JSONResponse({"error": f"Error al decodificar la foto: {str(e)}"}, status_code=400)

    informe_bytes = None
    if informe_base64:
        try:
            informe_bytes = base64.b64decode(informe_base64)
        except Exception as e:
            return JSONResponse({"error": f"Error al decodificar el informe PDF: {str(e)}"}, status_code=400)

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO prueba (
                fecha_inspeccion, ordentiro, lote, tamano, muestra, armamento, distancia_tiro,
                base, altura, area_impactos, decision, id_municion, foto, informe
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            fecha, ordentiro, lote, tamano, muestra, armamento, distancia_tiro,
            base, altura, area_impactos, decision, id_municion, foto_bytes, informe_bytes
        ))
        nuevo_id = cur.fetchone()[0]

        for id_usuario in usuarios:
            cur.execute("INSERT INTO participantes (id_usuario) VALUES (%s) RETURNING id", (id_usuario,))
            id_participante = cur.fetchone()[0]
            cur.execute("INSERT INTO prueba_participantes (id_prueba, id_participante) VALUES (%s, %s)", (nuevo_id, id_participante))

        for id_serie in series:
            cur.execute("INSERT INTO prueba_series (id_prueba, id_serie) VALUES (%s, %s)", (nuevo_id, id_serie))

        conn.commit()
        cur.close()
        conn.close()
        return JSONResponse({"mensaje": "Prueba guardada correctamente", "id_prueba": nuevo_id})
    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        return JSONResponse({"error": str(e)}, status_code=500)

@router.put("/actualizar_prueba/{id_prueba}")
def actualizar_prueba(id_prueba: int, data: dict = Body(...)):
    base = data.get("base")
    altura = data.get("altura")
    area_impactos = data.get("area_impactos")
    decision = data.get("decision")
    series = data.get("series", [])
    foto_base64 = data.get("foto")
    informe_base64 = data.get("informe")

    foto_bytes = None
    if foto_base64:
        try:
            foto_bytes = base64.b64decode(foto_base64)
        except Exception as e:
            return JSONResponse({"error": f"Error al decodificar la foto: {str(e)}"}, status_code=400)

    informe_bytes = None
    if informe_base64:
        try:
            informe_bytes = base64.b64decode(informe_base64)
        except Exception as e:
            return JSONResponse({"error": f"Error al decodificar el informe PDF: {str(e)}"}, status_code=400)

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE prueba 
            SET base = %s, 
                altura = %s, 
                area_impactos = %s, 
                decision = %s,
                foto = %s,
                informe = %s
            WHERE id = %s
        """, (base, altura, area_impactos, decision, foto_bytes, informe_bytes, id_prueba))

        cur.execute("SELECT id_serie FROM prueba_series WHERE id_prueba = %s", (id_prueba,))
        series_existentes = [row[0] for row in cur.fetchall()]

        for id_serie in series:
            if id_serie not in series_existentes:
                cur.execute("INSERT INTO prueba_series (id_prueba, id_serie) VALUES (%s, %s)", (id_prueba, id_serie))

        conn.commit()
        cur.close()
        conn.close()
        return JSONResponse({"mensaje": "Prueba actualizada correctamente", "id_prueba": id_prueba})
    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/series")
def obtener_series():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, nro_serie FROM serie ORDER BY id ASC")
        filas = cur.fetchall()
        cur.close()
        conn.close()
        series = [{"id": fila[0], "nro_serie": fila[1]} for fila in filas]
        return JSONResponse(series)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/obtener_pruebas")
def obtener_pruebas():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT p.id, p.fecha_inspeccion, s.nro_serie, mun.calibre, 
                   p.base, p.altura, p.area_impactos, p.decision,
                   encode(p.foto, 'base64') AS foto_b64,
                   encode(p.informe, 'base64') AS informe_b64
            FROM prueba p
            LEFT JOIN prueba_series ps ON p.id = ps.id_prueba
            LEFT JOIN serie s ON ps.id_serie = s.id
            LEFT JOIN municion mun ON p.id_municion = mun.id
            ORDER BY p.id ASC
        """)
        filas = cur.fetchall()
        cur.close()
        conn.close()

        datos = {}
        for fila in filas:
            id_prueba, fecha, nro_serie, calibre, base, altura, area, decision, foto_b64, informe_b64 = fila
            if id_prueba not in datos:
                datos[id_prueba] = {
                    "nro": id_prueba,
                    "series": []
                }
            datos[id_prueba]["series"].append({
                "nombre": nro_serie if nro_serie else "Única serie",
                "calibre": calibre if calibre else "-",
                "base": float(base) if base else 0,
                "altura": float(altura) if altura else 0,
                "area": float(area) if area else 0,
                "estado": decision if decision else "-",
                "fecha": fecha.isoformat() if fecha else None,
                "foto": foto_b64,
                "informe": informe_b64
            })

        return JSONResponse(list(datos.values()))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/resumen_pruebas")
def resumen_pruebas():
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM prueba")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM prueba WHERE decision = 'APROBADO'")
        aprobados = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM prueba WHERE decision = 'RECHAZADO'")
        rechazados = cur.fetchone()[0]

        cur.close()
        conn.close()

        return {"total": total, "aprobados": aprobados, "rechazados": rechazados}
    except Exception as e:
        return {"error": str(e)}
