"""Single camera owner; publish matching JPEG and detection metadata atomically."""
import base64
import threading
import time
from . import detector


class CameraService:
    def __init__(self, config):
        self.config = config
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._snapshot = None
        self._error = "Camera initializing" if config.CAMERA_ENABLED else "Camera disabled"
        self._sequence = 0
        self._acquisition = bool(config.CAMERA_ENABLED)
        self._detection = self._acquisition
        self._generation = 0

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="marble-camera", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()  # Camera is closed by its owner before shutdown returns.

    def settings(self):
        with self._lock:
            return {"acquisition_enabled": self._acquisition,
                    "detection_enabled": self._detection}

    def configure(self, values):
        if not isinstance(values, dict) or not values or any(
            key not in ("acquisition_enabled", "detection_enabled") or type(value) is not bool
            for key, value in values.items()
        ):
            raise ValueError("Expected acquisition_enabled and/or detection_enabled booleans")
        with self._lock:
            acquisition = values.get("acquisition_enabled", self._acquisition)
            detection = values.get("detection_enabled", self._detection) if acquisition else False
            if (acquisition, detection) != (self._acquisition, self._detection):
                self._acquisition, self._detection = acquisition, detection
                self._generation += 1
                self._snapshot = None
                self._error = "Camera initializing" if acquisition else "Video acquisition disabled"
            return {"acquisition_enabled": acquisition, "detection_enabled": detection}

    def publish(self, jpeg, objects, width, height, timestamp_ms, generation=None):
        jpeg = bytes(jpeg)
        encoded = base64.b64encode(jpeg).decode('ascii')
        with self._lock:
            if not self._acquisition or (generation is not None and generation != self._generation):
                return
            self._sequence += 1
            self._snapshot = ({
                "sequence": self._sequence, "timestamp_ms": timestamp_ms,
                "width": width, "height": height, "objects": objects,
                "detection_enabled": self._detection,
                "detector": "circle-candidates" if self._detection else "disabled", "image_mime": "image/jpeg",
                "image_base64": encoded,
                "geometry": {"camera_hfov_deg": self.config.CAMERA_HFOV_DEG,
                             "camera_vfov_deg": self.config.CAMERA_VFOV_DEG,
                             "tof_hfov_deg": self.config.TOF_HFOV_DEG,
                             "tof_vfov_deg": self.config.TOF_VFOV_DEG,
                             "sensor_offset_x_mm": self.config.SENSOR_OFFSET_X_MM,
                             "alignment": "nominal-parallel-axes"},
            }, jpeg)
            self._error = None

    def fail(self, error):
        with self._lock:
            self._error = str(error) if self._acquisition else "Video acquisition disabled"
            self._snapshot = None

    def response(self, path):
        with self._lock:
            snapshot, error = self._snapshot, self._error
        age = None if snapshot is None else int(time.monotonic() * 1000) - snapshot[0]['timestamp_ms']
        if error or age is None or age >= self.config.CAMERA_STALE_AFTER_MS:
            return 503, {"error": error or "Camera data stale", "age_ms": age}
        if path == '/api/image.jpg':
            return 200, snapshot[1]
        payload = dict(snapshot[0], age_ms=age)
        if path == '/api/detections':
            payload.pop('image_base64')
        return 200, payload

    def _run(self):
        while not self._stop.is_set():
            if not self.settings()["acquisition_enabled"]:
                self._stop.wait(0.1)
                continue
            cam = None
            failed = False
            try:
                from maix import camera, image
                cam = camera.Camera(detector.WIDTH, detector.HEIGHT, image.Format.FMT_RGB888,
                                    fps=detector.CAMERA_FPS)
                if detector.EXPOSURE_US is None:
                    cam.exp_mode(camera.AeMode.Auto)
                else:
                    cam.exposure(detector.EXPOSURE_US)
                    if detector.GAIN is not None:
                        cam.gain(detector.GAIN)
                # Warm up without an unbounded blocking skip_frames call.
                warmup = 20
                last_frame = time.monotonic()
                while not self._stop.is_set():
                    with self._lock:
                        acquisition, detection, generation = self._acquisition, self._detection, self._generation
                    if not acquisition:
                        break
                    started = time.monotonic()
                    frame = cam.read(block=False)
                    if frame is None:
                        if time.monotonic() - last_frame > 5:
                            raise OSError('Camera stopped delivering frames')
                        self._stop.wait(0.005)
                        continue
                    last_frame = time.monotonic()
                    if warmup:
                        warmup -= 1
                        continue
                    timestamp = int(time.monotonic() * 1000)
                    circles = detector.detect_marbles(frame) if detection else []
                    objects = []
                    for index, circle in enumerate(circles):
                        x, y, w, h = detector.bounding_box(circle, frame.width(), frame.height())
                        objects.append({"id": index, "label": "marble candidate",
                                        "bbox": {"x": x, "y": y, "width": w, "height": h},
                                        "center": {"x": circle.x(), "y": circle.y()},
                                        "radius_px": circle.r(), "magnitude": circle.magnitude()})
                        frame.draw_rect(x, y, w, h, image.COLOR_GREEN, thickness=2)
                        frame.draw_string(x, y, str(index + 1), image.COLOR_GREEN)
                    jpeg = frame.to_jpeg(quality=self.config.CAMERA_JPEG_QUALITY).to_bytes()
                    self.publish(jpeg, objects, frame.width(), frame.height(), timestamp, generation)
                    self._stop.wait(max(0, 1 / self.config.CAMERA_PUBLISH_HZ - (time.monotonic() - started)))
            except Exception as exc:
                failed = True
                self.fail(exc)
                print('Camera:', exc)
            finally:
                if cam is not None:
                    try:
                        cam.close()
                    except Exception as exc:
                        print('Camera close:', exc)
            if failed:
                self._stop.wait(self.config.CAMERA_RETRY_SECONDS)
