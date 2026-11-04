import base64
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from api import State
from marble_detect.detector import bounding_box, detect_marbles
from marble_detect.service import CameraService


def circle(x=20, y=20, radius=10, magnitude=100):
    return SimpleNamespace(x=lambda: x, y=lambda: y, r=lambda: radius, magnitude=lambda: magnitude)


class DetectionTests(unittest.TestCase):
    def test_concentric_candidates_keep_strongest_and_separate_marbles(self):
        strongest, adjacent = circle(magnitude=200), circle(x=60)
        frame = Mock()
        frame.find_circles.return_value = [circle(x=21), adjacent, strongest]
        self.assertEqual(detect_marbles(frame), [strongest, adjacent])

    def test_boxes_clip_at_image_edges(self):
        self.assertEqual(bounding_box(circle(x=1, y=2), 320, 180), (0, 0, 15, 16))
        self.assertEqual(bounding_box(circle(x=319, y=179), 320, 180), (306, 166, 14, 14))


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.camera = CameraService(config)
        self.state = State(config, self.camera)
        self.clock = patch('marble_detect.service.time.monotonic', return_value=10)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_atomic_image_objects_and_independence_from_tof(self):
        objects = [{'label': 'marble candidate', 'bbox': {'x': 1, 'y': 2, 'width': 3, 'height': 4}}]
        self.camera.publish(b'jpeg-one', objects, 320, 180, 9900)
        status, snapshot = self.state.route('GET', '/api/camera')
        self.assertEqual(status, 200)
        self.assertEqual(snapshot['age_ms'], 100)
        self.assertEqual(base64.b64decode(snapshot['image_base64']), b'jpeg-one')
        self.assertEqual(snapshot['objects'], objects)
        self.assertEqual(snapshot['geometry']['sensor_offset_x_mm'], -60)
        self.assertEqual(self.state.route('GET', '/api/image.jpg'), (200, b'jpeg-one'))
        self.assertNotIn('image_base64', self.state.route('GET', '/api/detections')[1])
        self.assertEqual(self.state.route('GET', '/api/frame')[0], 503)
        self.camera.publish(b'jpeg-two', [], 320, 180, 10000)
        self.assertEqual(self.state.route('GET', '/api/camera')[1]['objects'], [])
        self.assertEqual(snapshot['objects'], objects)  # Older response is unchanged.

    def test_fault_staleness_and_recovery(self):
        for path in ('/api/camera', '/api/detections', '/api/image.jpg'):
            self.assertEqual(self.state.route('GET', path)[0], 503)
        self.camera.publish(b'jpeg', [], 320, 180, 8000)
        self.assertEqual(self.state.route('GET', '/api/camera')[0], 503)
        self.camera.publish(b'jpeg', [], 320, 180, 10000)
        self.camera.fail('Camera disconnected')
        self.assertEqual(self.state.route('GET', '/api/image.jpg')[0], 503)
        self.camera.publish(b'new', [], 320, 180, 10000)
        self.assertEqual(self.state.route('GET', '/api/camera')[0], 200)

    def test_worker_captures_draws_encodes_and_closes(self):
        camera_module, image_module = Mock(), Mock()
        cam = camera_module.Camera.return_value
        frame = cam.read.return_value
        frame.width.return_value, frame.height.return_value = 320, 180
        frame.find_circles.return_value = [circle()]
        frame.to_jpeg.return_value.to_bytes.return_value = b'jpeg'
        original = self.camera.publish
        def publish(*args):
            original(*args)
            self.camera._stop.set()
        with patch.dict(sys.modules, {'maix': SimpleNamespace(camera=camera_module, image=image_module)}), \
             patch.object(self.camera, 'publish', side_effect=publish):
            self.camera._run()
        cam.close.assert_called_once()
        frame.draw_rect.assert_called_once()
        self.assertEqual(self.camera.response('/api/camera')[1]['objects'][0]['bbox'],
                         {'x': 7, 'y': 7, 'width': 27, 'height': 27})

    def test_worker_failure_closes_and_records_error(self):
        camera_module = Mock()
        camera_module.Camera.return_value.read.side_effect = OSError('capture failed')
        def fail(error):
            CameraService.fail(self.camera, error)
            self.camera._stop.set()
        with patch.dict(sys.modules, {'maix': SimpleNamespace(camera=camera_module, image=Mock())}), \
             patch.object(self.camera, 'fail', side_effect=fail), patch('builtins.print'):
            self.camera._run()
        camera_module.Camera.return_value.close.assert_called_once()
        self.assertEqual(self.camera.response('/api/camera')[1]['error'], 'capture failed')


class CameraControlTests(unittest.TestCase):
    def test_disable_forces_detection_off_and_discards_inflight_frames(self):
        c = CameraService(config)
        c.publish(b'old', [], 320, 180, 0)
        generation = c._generation
        self.assertEqual(c.configure({'acquisition_enabled': False, 'detection_enabled': True}),
                         {'acquisition_enabled': False, 'detection_enabled': False})
        c.publish(b'late', [], 320, 180, 0, generation)
        self.assertIsNone(c._snapshot)
        c.configure({'acquisition_enabled': True})
        self.assertFalse(c.settings()['detection_enabled'])
        c.publish(b'late', [], 320, 180, 0, generation)
        self.assertIsNone(c._snapshot)
        c.publish(b'raw', [], 320, 180, 0, c._generation)
        self.assertFalse(c._snapshot[0]['detection_enabled'])

    def test_raw_worker_skips_detector_and_annotations(self):
        c = CameraService(config)
        c.configure({'detection_enabled': False})
        camera_module, image_module = Mock(), Mock()
        cam = camera_module.Camera.return_value
        frame = cam.read.return_value
        frame.width.return_value, frame.height.return_value = 320, 180
        frame.to_jpeg.return_value.to_bytes.return_value = b'raw'
        original = c.publish
        def publish(*args):
            original(*args)
            c._stop.set()
        with patch.dict(sys.modules, {'maix': SimpleNamespace(camera=camera_module, image=image_module)}), \
             patch.object(c, 'publish', side_effect=publish):
            c._run()
        frame.find_circles.assert_not_called()
        frame.draw_rect.assert_not_called()
        frame.draw_string.assert_not_called()
        cam.close.assert_called_once()
        self.assertEqual(c._snapshot[0]['objects'], [])

    def test_invalid_settings_do_not_mutate_state(self):
        c = CameraService(config)
        for values in (None, {}, {'acquisition_enabled': 'false'}, {'unknown': True}, []):
            with self.assertRaises(ValueError):
                c.configure(values)
        self.assertTrue(c.settings()['acquisition_enabled'])
