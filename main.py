import os
import logging
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from routes import roles, usuarios, municiones, prueba
from conf_camara import camera, network

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.environ["YOLO_CONFIG_DIR"] = "/tmp/Ultralytics"
PORT = int(os.environ.get("PORT", 8000))

try:
    from ultralytics import YOLO
    camera.model = YOLO("yolov8n.pt")
    logger.info("Modelo YOLO cargado correctamente")
except Exception as e:
    logger.error(f"No se pudo cargar el modelo YOLO: {e}")

app = FastAPI(title="Backend Precision", version="1.0.0")

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://frontend-precision.vercel.app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
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
        "hoja": camera.last_best_box.xyxy[0].tolist() if camera.last_best_box else None,
        "impactos": [{"bbox": bbox, "centro": centro} for bbox, centro in camera.last_impactos],
        "celda": camera.last_celda_coords,
        "medidas": camera.last_medidas_texto,
    }

@app.get("/obtener_celda_actual")
async def obtener_celda_actual():
    hoja_coords = list(map(int, camera.last_best_box.xyxy[0])) if camera.last_best_box else None
    celda_coords = list(camera.last_celda_coords) if camera.last_celda_coords else None
    medidas = camera.last_medidas_texto if camera.last_medidas_texto else ""
    if hoja_coords:
        return {"hoja": hoja_coords, "celda": celda_coords, "medidas": medidas, "success": True}
    return {"hoja": None, "celda": celda_coords, "medidas": medidas, "success": False, "message": "No hay hoja detectada actualmente"}

app.include_router(roles.router)
app.include_router(usuarios.router, prefix="/usuarios")
app.include_router(municiones.router)
app.include_router(prueba.router)

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Iniciando servidor en puerto {PORT}")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
