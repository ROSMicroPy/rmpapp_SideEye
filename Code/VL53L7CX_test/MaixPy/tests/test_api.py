import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api import HTTPServer, State


def state(zones=64):
    return State(SimpleNamespace(RESOLUTION=zones, RANGING_HZ=10,
                                STALE_AFTER_MS=2000, CORS_ORIGIN="http://localhost:5173"))


class FrameTests(unittest.TestCase):
    def test_grid_and_validity(self):
        s = state()
        distances = list(range(64))
        statuses, targets = [5] * 64, [1] * 64
        statuses[1], statuses[2], targets[3], distances[4] = 255, 9, 0, -1
        s.publish((distances, statuses, targets))
        code, frame = s.route("GET", "/api/frame")
        self.assertEqual(code, 200)
        self.assertEqual(frame["distance_mm"][0][:5], [0, None, 2, None, None])
        self.assertEqual(frame["distance_mm"][7][7], 63)
        self.assertEqual(frame["target_status"][0][1], 255)

    def test_stale_fault_and_recovery(self):
        s = state(16)
        self.assertEqual(s.route("GET", "/api/frame")[0], 503)
        with patch("api.ticks_ms", return_value=10000):
            s.publish(([100] * 16, [5] * 16, [1] * 16), now=7000)
            self.assertEqual(s.route("GET", "/api/health")[0], 503)
            self.assertEqual(s.route("GET", "/api/frame")[0], 503)
            s.publish(([200] * 16, [5] * 16, [1] * 16))
            self.assertEqual(s.route("GET", "/api/frame")[1]["sequence"], 2)
            s.error = "I2C failed"
            self.assertEqual(s.route("GET", "/api/frame")[0], 503)

    def test_reject_bad_frame_without_replacing_cache(self):
        s = state()
        with self.assertRaises(ValueError):
            s.publish(([0], [5], [1]))
        self.assertIsNone(s.frame)


class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = state(16)
        self.http = HTTPServer(self.state)
        self.server = await asyncio.start_server(self.http.handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def request(self, request):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(request)
        await writer.drain()
        data = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
        head, body = data.split(b"\r\n\r\n", 1)
        headers = head.decode().split("\r\n")
        fields = dict(line.split(": ", 1) for line in headers[1:])
        self.assertEqual(int(fields["Content-Length"]), len(body))
        self.assertEqual(fields["Access-Control-Allow-Origin"], "http://localhost:5173")
        if request.startswith(b"GET /api/image.jpg") and headers[0].split()[1] == "200":
            self.assertEqual(fields["Content-Type"], "image/jpeg")
        return int(headers[0].split()[1]), body

    async def test_frame_and_preflight(self):
        self.state.publish(([300] * 16, [5] * 16, [1] * 16))
        code, body = await self.request(b"GET /api/frame?fresh=1 HTTP/1.1\r\nHost: sensor\r\n\r\n")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["distance_mm"], [[300] * 4] * 4)
        self.assertEqual(await self.request(b"OPTIONS /api/frame HTTP/1.1\r\n\r\n"), (204, b""))

    async def test_binary_camera_image_and_cors(self):
        from marble_detect.service import CameraService
        import config
        import time
        self.state.camera = CameraService(config)
        jpeg = b'\xff\xd8binary-jpeg\xff\xd9'
        self.state.camera.publish(jpeg, [], 320, 180, int(time.monotonic() * 1000))
        self.assertEqual(await self.request(b"GET /api/image.jpg HTTP/1.1\r\n\r\n"), (200, jpeg))
        code, body = await self.request(b"GET /api/camera HTTP/1.1\r\n\r\n")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)['objects'], [])

    async def test_camera_settings_get_post_and_validation(self):
        from marble_detect.service import CameraService
        import config
        self.state.camera = CameraService(config)
        body = b'{"acquisition_enabled":false,"detection_enabled":true}'
        request = (b"POST /api/camera/settings HTTP/1.1\r\nContent-Type: application/json\r\nContent-Length: "
                   + str(len(body)).encode() + b"\r\n\r\n" + body)
        code, raw = await self.request(request)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(raw), {'acquisition_enabled': False, 'detection_enabled': False})
        code, raw = await self.request(b"GET /api/camera/settings HTTP/1.1\r\n\r\n")
        self.assertFalse(json.loads(raw)['acquisition_enabled'])
        for body in (b'{}', b'null', b'{"detection_enabled":1}', b'invalid'):
            request = (b"POST /api/camera/settings HTTP/1.1\r\nContent-Type: application/json\r\nContent-Length: "
                       + str(len(body)).encode() + b"\r\n\r\n" + body)
            self.assertEqual((await self.request(request))[0], 400)

    async def test_tof_settings_http(self):
        body = b'{"rotation":270,"flip_h":true,"flip_v":true}'
        request = (b"POST /api/tof/settings HTTP/1.1\r\nContent-Type: application/json\r\nContent-Length: "
                   + str(len(body)).encode() + b"\r\n\r\n" + body)
        code, raw = await self.request(request)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(raw), json.loads(body))
        self.assertEqual((await self.request(b"GET /api/tof/settings HTTP/1.1\r\n\r\n"))[1], raw)

    async def test_errors_and_limits(self):
        for request, expected in [
            (b"GET /api/frame HTTP/1.1\r\n\r\n", 503),
            (b"POST /api/frame HTTP/1.1\r\n\r\n", 405),
            (b"GET /missing HTTP/1.1\r\n\r\n", 404),
            (b"bad request\r\n\r\n", 400),
            (b"GET / HTTP/1.1\r\nX: " + b"a" * 2100 + b"\r\n\r\n", 431),
        ]:
            code, _ = await self.request(request)
            self.assertEqual(code, expected)


if __name__ == "__main__":
    unittest.main()
