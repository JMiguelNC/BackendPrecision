import cv2
import numpy as np
import subprocess
import threading
import time
from fastapi.responses import StreamingResponse
from .config import RTSP_USER, RTSP_PASS, RTSP_PORT, RTSP_CHANNEL, RTSP_SUBTYPE
import imageio_ffmpeg as ffmpeg_dl
from ultralytics import YOLO

stop_streaming = False
pause_detection = False
current_frame = None
frame_lock = threading.Lock()
model = YOLO("modelo/train100/best.pt")

HOJA_ANCHO_CM = 21.59
HOJA_ALTO_CM = 27.94

last_best_box = None
last_impactos = []
last_celda_coords = None
last_medidas_texto = ""

def get_rtsp_url(ip: str):
    return f"rtsp://{RTSP_USER}:{RTSP_PASS}@{ip}:{RTSP_PORT}/cam/realmonitor?channel={RTSP_CHANNEL}&subtype={RTSP_SUBTYPE}&transportmode=tcp"

def read_rtsp_stream(ip: str):
    global stop_streaming, current_frame
    rtsp_url = get_rtsp_url(ip)
    ffmpeg_path = ffmpeg_dl.get_ffmpeg_exe()
    width, height = 1280, 720
    frame_size = width * height * 3
    command = [ffmpeg_path, "-rtsp_transport", "tcp", "-i", rtsp_url, "-s", f"{width}x{height}",
               "-f", "image2pipe", "-pix_fmt", "bgr24", "-vcodec", "rawvideo", "-"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)
    while not stop_streaming:
        raw_frame = process.stdout.read(frame_size)
        if len(raw_frame) != frame_size:
            continue
        try:
            frame = np.frombuffer(raw_frame, np.uint8).reshape((height, width, 3)).copy()
            with frame_lock:
                if not pause_detection:
                    current_frame = frame
        except:
            continue
    process.terminate()

def generate_video_stream(ip: str):
    global stop_streaming, pause_detection, current_frame
    global last_best_box, last_impactos, last_celda_coords, last_medidas_texto
    stop_streaming = False
    pause_detection = False
    current_frame = None
    last_best_box = None
    last_impactos = []
    last_celda_coords = None
    last_medidas_texto = ""
    threading.Thread(target=read_rtsp_stream, args=(ip,), daemon=True).start()
    
    while not stop_streaming:
        start_time = time.time()
        with frame_lock:
            frame = None if current_frame is None else current_frame.copy()
        if frame is None:
            continue
        try:
            if not pause_detection:
                results = model(frame, imgsz=640, conf=0.5)
                best_box = None
                impactos = []
                for r in results:
                    for box in r.boxes:
                        cls = int(box.cls[0])
                        conf = float(box.conf[0])
                        if model.names[cls] == "hoja":
                            if conf > (best_box.conf if best_box else 0):
                                best_box = box
                        elif model.names[cls] == "impacto":
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            cx, cy = (x1 + x2)//2, (y1 + y2)//2
                            impactos.append(((x1, y1, x2, y2), (cx, cy)))
                last_best_box = best_box
                if best_box is not None:
                    hx1, hy1, hx2, hy2 = map(int, best_box.xyxy[0])
                    impactos_dentro = [imp for imp in impactos if hx1 <= imp[1][0] <= hx2 and hy1 <= imp[1][1] <= hy2]
                    last_impactos = impactos_dentro
                    if impactos_dentro:
                        centros = [c for _, c in impactos_dentro]
                        centros_sorted_x = sorted(centros, key=lambda p: p[0])
                        centros_sorted_y = sorted(centros, key=lambda p: p[1])
                        x1_celda = centros_sorted_x[0][0]
                        y1_celda = centros_sorted_y[0][1]
                        x2_celda = centros_sorted_x[-1][0]
                        y2_celda = centros_sorted_y[-1][1]
                        last_celda_coords = (x1_celda, y1_celda, x2_celda, y2_celda)
                        px_hoja_ancho = hx2 - hx1
                        px_hoja_alto = hy2 - hy1
                        ratio_x = HOJA_ANCHO_CM / px_hoja_ancho
                        ratio_y = HOJA_ALTO_CM / px_hoja_alto
                        ancho_cm = round((x2_celda - x1_celda) * ratio_x, 2)
                        alto_cm = round((y2_celda - y1_celda) * ratio_y, 2)
                        suma_cm = round(ancho_cm + alto_cm, 2)
                        last_medidas_texto = f"Ancho: {ancho_cm} cm  Alto: {alto_cm} cm  Suma: {suma_cm} cm"
                else:
                    last_impactos = []
                    last_celda_coords = None
                    last_medidas_texto = ""
            success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if not success:
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        except Exception as e:
            print(f"Error en detección: {e}")
            continue
        elapsed = time.time() - start_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

def impactos_se_solapan(bbox1, bbox2, tolerancia=5):
    """
    Verifica si dos bounding boxes representan el mismo impacto.
    Usa una tolerancia más estricta para evitar falsos positivos.
    """
    x1_1, y1_1, x2_1, y2_1 = bbox1
    x1_2, y1_2, x2_2, y2_2 = bbox2
    
    # Calcular centros
    cx1 = (x1_1 + x2_1) / 2
    cy1 = (y1_1 + y2_1) / 2
    cx2 = (x1_2 + x2_2) / 2
    cy2 = (y1_2 + y2_2) / 2
    
    # Calcular distancia entre centros
    distancia = ((cx1 - cx2)**2 + (cy1 - cy2)**2)**0.5
    
    # Si la distancia entre centros es menor que la tolerancia, son el mismo impacto
    return distancia < tolerancia

def detectar_area(x1: int, y1: int, x2: int, y2: int, impactos_manual=None, impactos_eliminados=None):
    """
    Detecta objetos en el área visible y retorna coordenadas ABSOLUTAS 
    (respecto al frame completo de 1280x720)
    impactos_manual: lista de impactos agregados manualmente [{bbox: [x1,y1,x2,y2]}]
    impactos_eliminados: lista de impactos eliminados [{bbox: [x1,y1,x2,y2]}]
    """
    with frame_lock:
        frame = None if current_frame is None else current_frame.copy()
    if frame is None:
        return None
    
    # Extraer ROI (región de interés)
    roi = frame[y1:y2, x1:x2]
    results = model(roi, imgsz=640, conf=0.5)
    
    best_box = None
    impactos = []
    
    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            if model.names[cls] == "hoja":
                if conf > (best_box[1] if best_box else 0):
                    best_box = (box, conf)
            elif model.names[cls] == "impacto":
                x1b, y1b, x2b, y2b = map(int, box.xyxy[0])
                abs_x1 = x1b + x1
                abs_y1 = y1b + y1
                abs_x2 = x2b + x1
                abs_y2 = y2b + y1
                cx, cy = (abs_x1 + abs_x2)//2, (abs_y1 + abs_y2)//2
                
                # Verificar si este impacto está en la lista de eliminados
                bbox_actual = (abs_x1, abs_y1, abs_x2, abs_y2)
                esta_eliminado = False
                if impactos_eliminados:
                    for imp_elim in impactos_eliminados:
                        bbox_elim = tuple(imp_elim['bbox'])
                        if impactos_se_solapan(bbox_actual, bbox_elim, tolerancia=10):
                            esta_eliminado = True
                            print(f"Impacto eliminado encontrado: {bbox_actual} coincide con {bbox_elim}")
                            break
                
                # Solo agregar si no está eliminado
                if not esta_eliminado:
                    impactos.append(((abs_x1, abs_y1, abs_x2, abs_y2), (cx, cy)))
    
    # Agregar impactos manuales si existen
    if impactos_manual:
        for imp in impactos_manual:
            bbox = imp['bbox']
            x1m, y1m, x2m, y2m = bbox
            cx, cy = (x1m + x2m)//2, (y1m + y2m)//2
            impactos.append(((int(x1m), int(y1m), int(x2m), int(y2m)), (int(cx), int(cy))))
    
    celda_coords = None
    medidas_texto = ""
    hoja_bbox = None
    
    if best_box is not None:
        box_obj = best_box[0]
        hx1, hy1, hx2, hy2 = map(int, box_obj.xyxy[0])
        abs_hx1 = hx1 + x1
        abs_hy1 = hy1 + y1
        abs_hx2 = hx2 + x1
        abs_hy2 = hy2 + y1
        hoja_bbox = [abs_hx1, abs_hy1, abs_hx2, abs_hy2]
        
        if impactos:
            impactos_dentro = [imp for imp in impactos if abs_hx1 <= imp[1][0] <= abs_hx2 and abs_hy1 <= imp[1][1] <= abs_hy2]
            
            if impactos_dentro:
                centros = [c for _, c in impactos_dentro]
                centros_sorted_x = sorted(centros, key=lambda p: p[0])
                centros_sorted_y = sorted(centros, key=lambda p: p[1])
                
                x1_celda = centros_sorted_x[0][0]
                y1_celda = centros_sorted_y[0][1]
                x2_celda = centros_sorted_x[-1][0]
                y2_celda = centros_sorted_y[-1][1]
                celda_coords = (x1_celda, y1_celda, x2_celda, y2_celda)
                
                px_hoja_ancho = abs_hx2 - abs_hx1
                px_hoja_alto = abs_hy2 - abs_hy1
                ratio_x = HOJA_ANCHO_CM / px_hoja_ancho
                ratio_y = HOJA_ALTO_CM / px_hoja_alto
                ancho_cm = round((x2_celda - x1_celda) * ratio_x, 2)
                alto_cm = round((y2_celda - y1_celda) * ratio_y, 2)
                suma_cm = round(ancho_cm + alto_cm, 2)
                medidas_texto = f"Ancho: {ancho_cm} cm  Alto: {alto_cm} cm  Suma: {suma_cm} cm"
    
    return {
        "hoja": hoja_bbox,
        "impactos": [{"bbox": list(bbox), "centro": list(centro)} for bbox, centro in impactos],
        "celda": celda_coords,
        "medidas": medidas_texto,
    }