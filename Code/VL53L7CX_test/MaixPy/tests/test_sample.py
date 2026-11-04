"""Exercise recovery using scripted acquisitions, without MaixCAM hardware."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config
import vl53l7cx
from api import State


class SampleTests(unittest.IsolatedAsyncioTestCase):
    async def run_script(self, readings):
        spec = importlib.util.spec_from_file_location('sensor_application', ROOT / 'main.py')
        app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app)
        state = State(config)
        clock = [0]
        items = iter(readings)
        stops = []

        class Sensor:
            def start(self, *args):
                pass

            def read(self):
                clock[0] += 600
                value = next(items)
                if isinstance(value, Exception):
                    raise value
                return value

            def stop(self):
                stops.append(True)

        snapshots = []

        async def sleep(seconds):
            ms = seconds * 1000
            if ms != config.SENSOR_RETRY_MS:
                self.assertEqual(ms, 5)
            snapshots.append((state.sequence, state.error))
            if ms == config.SENSOR_RETRY_MS or len(snapshots) >= len(readings):
                raise asyncio.CancelledError()

        with patch.object(vl53l7cx, 'VL53L7CX', return_value=Sensor()) as factory, \
             patch.object(app, 'ticks_ms', side_effect=lambda: clock[0]), \
             patch.object(app.asyncio, 'sleep', side_effect=sleep), \
             patch.object(app, 'open_i2c', return_value=object()), \
             patch.object(app, 'enable_sensor'), patch('builtins.print'):
            with self.assertRaises(asyncio.CancelledError):
                await app.sample(state)
            self.assertEqual(factory.call_count, 1)
        self.assertEqual(stops, [True])
        return snapshots

    async def test_corruption_recovers_without_reinitializing_or_publishing_bad_data(self):
        good = ([300] * config.RESOLUTION, [5] * config.RESOLUTION, [1] * config.RESOLUTION)
        snapshots = await self.run_script([good, vl53l7cx.CorruptFrameError('bad IDs'), good])
        self.assertEqual(snapshots, [(1, None), (1, 'bad IDs'), (2, None)])

    async def test_persistent_corruption_reaches_existing_restart_path(self):
        snapshots = await self.run_script([vl53l7cx.CorruptFrameError('bad IDs')] * 4)
        self.assertTrue(all(sequence == 0 for sequence, error in snapshots))
        self.assertIn('stopped delivering valid frames', snapshots[-1][1])
        self.assertIn('discarded reads=4', snapshots[-1][1])

    async def test_bus_error_is_not_treated_as_recoverable_corruption(self):
        snapshots = await self.run_script([OSError('I2C bus failed')])
        self.assertEqual(snapshots, [(0, 'I2C bus failed')])
