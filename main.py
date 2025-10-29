from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import roles, usuarios, municiones, prueba
from fastapi.responses import StreamingResponse, JSONResponse
from conf_camara import camera, network
from fastapi import Body

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/detecciones_area")
@app.get("/detecciones_area")
def get_detecciones_area(x1: int, y1: int, x2: int, y2: int, impactos_data: dict = Body(None)):
    impactos_manual = impactos_data.get('impactos_manual') if impactos_data else None
    impactos_eliminados = impactos_data.get('impactos_eliminados') if impactos_data else None
    data = camera.detectar_area(x1, y1, x2, y2, impactos_manual, impactos_eliminados)
    if data is None:
        return {"error": "No hay frame disponible"}
    return data

@app.get("/detectar_camara")
def detectar_camara():
    ip = network.scan_for_camera_ip()
    if ip:
        return {"ip": ip}
    return {"ip": None, "error": "No se detectó ninguna cámara en la red"}

@app.get("/video_feed")
def video_feed(ip: str):
    video_gen = camera.generate_video_stream(ip)
    if video_gen is None:
        return JSONResponse(content={"error": "No se pudo abrir el stream"}, status_code=500)
    return StreamingResponse(video_gen, media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/detener_camara")
def detener_camara():
    camera.stop_streaming = True
    with camera.frame_lock:
        camera.current_frame = None
    return {"mensaje": "Transmisión detenida exitosamente"}

@app.get("/pausar_deteccion")
def pausar_deteccion():
    camera.pause_detection = True
    return {"mensaje": "Detección pausada"}

@app.get("/reanudar_deteccion")
def reanudar_deteccion():
    camera.pause_detection = False
    return {"mensaje": "Detección reanudada"}

@app.get("/detecciones")
def get_detecciones():
    return {
        "hoja": camera.last_best_box.xyxy[0].tolist() if camera.last_best_box is not None else None,
        "impactos": [
            {"bbox": bbox, "centro": centro}
            for bbox, centro in camera.last_impactos
        ],
        "celda": camera.last_celda_coords,
        "medidas": camera.last_medidas_texto,
    }

@app.get("/obtener_celda_actual")
async def obtener_celda_actual():
    hoja_coords = None
    if camera.last_best_box is not None:
        hx1, hy1, hx2, hy2 = map(int, camera.last_best_box.xyxy[0])
        hoja_coords = [hx1, hy1, hx2, hy2]
    celda_coords = list(camera.last_celda_coords) if camera.last_celda_coords else None
    medidas = camera.last_medidas_texto if camera.last_medidas_texto else ""
    if hoja_coords is not None:
        return {
            "hoja": hoja_coords,
            "celda": celda_coords,
            "medidas": medidas,
            "success": True
        }
    else:
        return {
            "hoja": None,
            "celda": celda_coords,
            "medidas": medidas,
            "success": False,
            "message": "No hay hoja detectada actualmente"
        }

app.include_router(roles.router)
app.include_router(usuarios.router, prefix="/usuarios")
app.include_router(municiones.router)
app.include_router(prueba.router)