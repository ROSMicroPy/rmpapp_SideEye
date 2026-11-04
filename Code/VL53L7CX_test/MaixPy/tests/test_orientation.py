import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api import State


class OrientationTests(unittest.TestCase):
    def test_all_rotations_and_flips_preserve_data_and_native_identity(self):
        for n in (4, 8):
            state = State(SimpleNamespace(RESOLUTION=n*n, RANGING_HZ=10, STALE_AFTER_MS=2000))
            distances = list(range(n*n))
            statuses = [5 if i % 2 else 9 for i in distances]
            targets = [1] * (n*n)
            state.publish((distances, statuses, targets))
            original = state.frame
            for rotation in (0, 90, 180, 270):
                for h in (False, True):
                    for v in (False, True):
                        state.configure_tof({'rotation': rotation, 'flip_h': h, 'flip_v': v})
                        code, frame = state.route('GET', '/api/frame')
                        self.assertEqual(code, 200)
                        for i in distances:
                            y, x = divmod(i, n)
                            for _ in range(rotation // 90):
                                y, x = x, n - 1 - y
                            if h: x = n - 1 - x
                            if v: y = n - 1 - y
                            self.assertEqual(frame['distance_mm'][y][x], i)
                            self.assertEqual(frame['zone_ids'][y][x], i)
                            self.assertEqual(frame['target_status'][y][x], statuses[i])
                            self.assertEqual(frame['targets_detected'][y][x], targets[i])
                        self.assertIs(state.frame, original)
                        self.assertEqual(frame['sequence'], original['sequence'])
                        self.assertEqual(frame['timestamp_ms'], original['timestamp_ms'])

    def test_defaults_partial_updates_and_invalid_values(self):
        state = State(SimpleNamespace(TOF_ROTATION=90, TOF_FLIP_H=True, TOF_FLIP_V=False))
        self.assertEqual(state.route('GET', '/api/tof/settings'),
                         (200, {'rotation': 90, 'flip_h': True, 'flip_v': False}))
        self.assertEqual(state.route('POST', '/api/tof/settings', {'flip_v': True})[0], 200)
        before = state.orientation.copy()
        for invalid in ({}, None, [], {'rotation': True}, {'rotation': 45}, {'rotation': 90.0},
                        {'flip_h': 1}, {'flip_v': 'false'}, {'unknown': False},
                        {'rotation': 180, 'flip_v': None}):
            self.assertEqual(state.route('POST', '/api/tof/settings', invalid)[0], 400)
            self.assertEqual(state.orientation, before)
