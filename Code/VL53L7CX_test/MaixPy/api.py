"""REST protocol and cached frames; also importable on CPython for tests."""
import json
import time
import asyncio


def ticks_ms():
    return int(time.monotonic() * 1000)


def ticks_diff(a, b):
    return a - b


class State:
    def __init__(self, config, camera=None):
        self.config = config
        self.camera = camera
        self.frame = None
        self.last_frame_ms = None
        self.sequence = 0
        self.error = "Sensor initializing"
        self.orientation = {"rotation": 0, "flip_h": False, "flip_v": False}
        self.configure_tof({"rotation": getattr(config, "TOF_ROTATION", 0),
                            "flip_h": getattr(config, "TOF_FLIP_H", False),
                            "flip_v": getattr(config, "TOF_FLIP_V", False)})

    def configure_tof(self, values):
        if not isinstance(values, dict) or not values or any(
            key not in self.orientation or
            (type(value) is not int or value not in (0, 90, 180, 270) if key == "rotation"
             else type(value) is not bool)
            for key, value in values.items()
        ):
            raise ValueError("Use rotation 0/90/180/270 and boolean flip_h/flip_v")
        self.orientation = dict(self.orientation, **values)
        return self.orientation.copy()

    def oriented_frame(self):
        frame = self.frame.copy()
        n = frame["rows"]
        ids = []
        for y in range(n):
            row_ids = []
            for x in range(n):
                row = n - 1 - y if self.orientation["flip_v"] else y
                col = n - 1 - x if self.orientation["flip_h"] else x
                for _ in range(self.orientation["rotation"] // 90):
                    row, col = n - 1 - col, row
                row_ids.append(row * n + col)
            ids.append(row_ids)
        for key in ("distance_mm", "target_status", "targets_detected"):
            frame[key] = [[self.frame[key][i // n][i % n] for i in row] for row in ids]
        frame["zone_ids"] = ids
        frame["orientation"] = self.orientation.copy()
        return frame

    def publish(self, result, now=None):
        distances, statuses, targets = result
        n = self.config.RESOLUTION
        if any(len(values) != n for values in result):
            raise ValueError("Unexpected sensor frame size")
        now = ticks_ms() if now is None else now
        side = 8 if n == 64 else 4
        # Status 5 is valid; 9 is valid with a large pulse. Preserve all statuses.
        values = [d if t > 0 and s in (5, 9) and d >= 0 else None
                  for d, s, t in zip(distances, statuses, targets)]
        self.sequence += 1
        self.frame = {
            "sensor": "VL53L7CX", "sequence": self.sequence,
            "timestamp_ms": now, "rows": side, "cols": side, "units": "mm",
            "distance_mm": [values[i:i + side] for i in range(0, n, side)],
            "target_status": [statuses[i:i + side] for i in range(0, n, side)],
            "targets_detected": [targets[i:i + side] for i in range(0, n, side)],
        }
        self.last_frame_ms = now
        self.error = None

    def route(self, method, path, payload=None):
        if method == "OPTIONS":
            return 204, None
        path = path.split("?", 1)[0]
        if path == "/api/tof/settings" and method in ("GET", "POST"):
            try:
                return 200, self.orientation.copy() if method == "GET" else self.configure_tof(payload)
            except ValueError as exc:
                return 400, {"error": str(exc)}
        if path == "/api/camera/settings" and method in ("GET", "POST"):
            if self.camera is None:
                return 503, {"error": "Camera unavailable"}
            try:
                return 200, self.camera.settings() if method == "GET" else self.camera.configure(payload)
            except ValueError as exc:
                return 400, {"error": str(exc)}
        if method != "GET":
            return 405, {"error": "Method not allowed"}
        path = path.split("?", 1)[0]
        if path in ("/api/camera", "/api/image.jpg", "/api/detections"):
            if self.camera is None:
                return 503, {"error": "Camera unavailable"}
            return self.camera.response(path)
        age = None if self.last_frame_ms is None else ticks_diff(ticks_ms(), self.last_frame_ms)
        ready = self.error is None and age is not None and age <= self.config.STALE_AFTER_MS
        if path == "/api/health":
            return (200 if ready else 503), {
                "ready": ready, "sensor": "VL53L7CX", "frame_age_ms": age,
                "error": self.error if self.error else (None if ready else "Sensor data stale"),
            }
        if path == "/api/config":
            side = 8 if self.config.RESOLUTION == 64 else 4
            return 200, {"sensor": "VL53L7CX", "rows": side, "cols": side,
                         "ranging_hz": self.config.RANGING_HZ, "units": "mm",
                         "order": "oriented row-major", "orientation": self.orientation.copy(), "valid_statuses": [5, 9],
                         "mounting": {"sensor_position": getattr(self.config, "SENSOR_POSITION", "right"),
                                      "viewpoint": "looking at camera lens", "populated_modules": 1,
                                      "offset_x_mm": getattr(self.config, "SENSOR_OFFSET_X_MM", -60.0),
                                      "alignment": "nominal-parallel-axes"}}
        if path == "/api/frame":
            if not ready:
                return 503, {"error": self.error or "Sensor data stale", "frame_age_ms": age}
            frame = self.oriented_frame()
            frame["age_ms"] = age
            return 200, frame
        return 404, {"error": "Not found"}


class HTTPServer:
    def __init__(self, state):
        self.state = state
        self.clients = 0

    async def _request(self, reader):
        # Read bounded chunks: reject oversized headers before parsing.
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = await reader.read(128)
            if not chunk:
                raise ValueError("Incomplete request")
            data += chunk
            if len(data) > 2048:
                return 431, {"error": "Headers too large"}
        try:
            method, path, version = data.split(b"\r\n", 1)[0].decode().split(" ")
            if version not in ("HTTP/1.0", "HTTP/1.1") or not path.startswith("/"):
                raise ValueError()
        except (ValueError, UnicodeError):
            return 400, {"error": "Malformed request"}
        payload = None
        if method == "POST" and path.split("?", 1)[0] in ("/api/camera/settings", "/api/tof/settings"):
            head, body = data.split(b"\r\n\r\n", 1)
            headers = {}
            for line in head.split(b"\r\n")[1:]:
                key, value = line.decode().split(":", 1)
                key = key.lower().strip()
                if key in headers:
                    raise ValueError("Duplicate header")
                headers[key] = value.strip()
            if "transfer-encoding" in headers:
                raise ValueError("Transfer encoding unsupported")
            size = int(headers.get("content-length", "-1"))
            if not 0 < size <= 512:
                raise ValueError("Invalid body length")
            if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                raise ValueError("Expected JSON")
            while len(body) < size:
                chunk = await reader.read(size - len(body))
                if not chunk:
                    raise ValueError("Incomplete body")
                body += chunk
            payload = json.loads(body[:size])
        return self.state.route(method, path, payload)

    async def _respond(self, writer, status, payload):
        binary = isinstance(payload, bytes)
        body = payload if binary else (b"" if payload is None else json.dumps(payload).encode())
        content_type = "image/jpeg" if binary else "application/json"
        reasons = {200: "OK", 204: "No Content", 400: "Bad Request",
                   404: "Not Found", 405: "Method Not Allowed", 408: "Request Timeout",
                   431: "Request Header Fields Too Large", 503: "Service Unavailable"}
        header = (
            "HTTP/1.1 %d %s\r\nContent-Type: %s\r\n"
            "Content-Length: %d\r\nConnection: close\r\nCache-Control: no-store\r\n"
            "Access-Control-Allow-Origin: %s\r\nVary: Origin\r\n"
            "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type\r\n"
            "Allow: GET, POST, OPTIONS\r\n\r\n"
        ) % (status, reasons[status], content_type, len(body), self.state.config.CORS_ORIGIN)
        writer.write(header.encode())
        writer.write(body)
        await asyncio.wait_for(writer.drain(), 3)

    async def handle(self, reader, writer):
        self.clients += 1
        try:
            if self.clients > 4:
                # Close excess connections immediately to bound work and memory.
                return
            try:
                status, payload = await asyncio.wait_for(self._request(reader), 3)
            except asyncio.TimeoutError:
                status, payload = 408, {"error": "Request timeout"}
            except ValueError:
                status, payload = 400, {"error": "Malformed request"}
            await self._respond(writer, status, payload)
        except (OSError, asyncio.TimeoutError):
            pass
        finally:
            self.clients -= 1
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (OSError, asyncio.TimeoutError):
                pass
