import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vl53l7cx import CorruptFrameError

spec = importlib.util.spec_from_file_location('diagnose_sensor', ROOT / 'tools/diagnose_sensor.py')
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


class DiagnosticTests(unittest.TestCase):
    def test_counts_rejections_without_retrying_and_stops_sensor(self):
        sensor = Mock()
        sensor._frame = bytearray(320)
        sensor.read.side_effect = [([123], [5], [1]), CorruptFrameError('bad frame'), None]
        clock = [0]

        def sleep(ms):
            clock[0] += 1000

        with patch.object(diagnostic, 'ticks_ms', side_effect=lambda: clock[0], create=True), \
             patch.object(diagnostic, 'ticks_diff', side_effect=lambda a, b: a - b, create=True), \
             patch.object(diagnostic.time, 'sleep', side_effect=sleep, create=True), \
             patch('builtins.print') as output:
            self.assertEqual(diagnostic.phase(sensor, 10, 3), (1, 1))
        sensor.start.assert_called_once_with(64, 10)
        sensor.stop.assert_called_once()
        self.assertEqual(sensor.read.call_count, 3)
        self.assertIn('good=1 rejected=1 rejected_pct=50.00 not_ready=1', output.call_args.args[0])

    def test_bus_errors_propagate_and_still_stop_sensor(self):
        sensor = Mock()
        sensor.read.side_effect = OSError('bus error')
        with patch.object(diagnostic, 'ticks_ms', return_value=0, create=True), \
             patch.object(diagnostic, 'ticks_diff', return_value=0, create=True):
            with self.assertRaisesRegex(OSError, 'bus error'):
                diagnostic.phase(sensor, 10)
        sensor.stop.assert_called_once()
