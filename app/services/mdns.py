import socket
import logging
from zeroconf import ServiceInfo, Zeroconf

logger = logging.getLogger(__name__)

class MDNSService:
    def __init__(self, port: int = 8000, name: str = "nexusmedia"):
        self.port = port
        self.name = name
        self.zeroconf = None
        self.service_info = None

    def get_local_ip(self):
        # Create a dummy socket to find the local IP address used for outbound connections
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start(self):
        ip_addr = self.get_local_ip()
        
        # Service details
        type_ = "_http._tcp.local."
        service_name = f"{self.name}.{type_}"
        server_name = f"{self.name}.local."

        try:
            ip_bytes = socket.inet_aton(ip_addr)
            
            self.service_info = ServiceInfo(
                type_,
                service_name,
                addresses=[ip_bytes],
                port=self.port,
                properties={'path': '/'},
                server=server_name
            )
            
            self.zeroconf = Zeroconf()
            self.zeroconf.register_service(self.service_info)
            logger.info(f"🚀 mDNS Service registered: http://{server_name}:{self.port} at IP {ip_addr}")
        except Exception as e:
            logger.error(f"Failed to start mDNS service: {e}", exc_info=True)

    def stop(self):
        if self.zeroconf and self.service_info:
            try:
                self.zeroconf.unregister_service(self.service_info)
                self.zeroconf.close()
                logger.info("🛑 mDNS Service stopped.")
            except Exception as e:
                logger.error(f"Failed to stop mDNS service: {e}")
