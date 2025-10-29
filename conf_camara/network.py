import socket
import ipaddress
import concurrent.futures
from .config import NETWORK_RANGE, RTSP_PORT

def is_port_open(ip, port=RTSP_PORT):
    try:
        with socket.create_connection((ip, port), timeout=2):  # aumentar timeout
            return ip
    except:
        return None

def scan_for_camera_ip(base_ip=NETWORK_RANGE, port=RTSP_PORT):
    net = ipaddress.ip_network(base_ip, strict=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=200) as executor:  # más hilos
        futures = {executor.submit(is_port_open, str(ip), port): ip for ip in net.hosts()}
        for future in concurrent.futures.as_completed(futures):
            ip = future.result()
            if ip:
                return str(ip)
    return None
