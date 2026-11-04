import ctypes
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vl53l7cx import VL53L7CX, CorruptFrameError
from fake_sensor import FakeSensor, swapped

ASSETS = ROOT / 'vl53l7cx_data'


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.sleep = patch('vl53l7cx._sleep_ms')
        self.sleep.start()
        self.addCleanup(self.sleep.stop)
        self.bus = FakeSensor()
        self.sensor = VL53L7CX(self.bus, data_dir=str(ASSETS))

    def test_maix_read_failures_are_rejected(self):
        for response in (None, b"", b"\x01"):
            with self.subTest(response=response), patch.object(self.bus, 'readfrom_mem', return_value=response):
                with self.assertRaisesRegex(OSError, 'I2C read failed'):
                    self.sensor._read(0, 4)

    def test_maix_write_failures_are_rejected(self):
        for written in (-1, 0, 2):
            with self.subTest(written=written), patch.object(self.bus, 'writeto_mem', return_value=written):
                with self.assertRaisesRegex(OSError, 'I2C write failed'):
                    self.sensor._write(0, b'1234')

    def test_assets_and_streamed_firmware(self):
        manifest = json.loads((ASSETS / 'manifest.json').read_text())
        for name, info in manifest.items():
            data = (ASSETS / name).read_bytes()
            self.assertEqual(len(data), info['size'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), info['sha256'])
        self.assertEqual(self.bus.firmware, (ASSETS / 'firmware.bin').read_bytes())
        self.assertTrue(all(len(entry[3]) <= 256 for entry in self.bus.trace))

    def test_both_resolutions_and_duplicate_frames(self):
        for zones, hz in ((16, 60), (64, 15)):
            self.sensor.start(zones, hz)
            expected = self.bus.set_frame(zones)
            self.assertEqual(self.sensor.read(), expected)
            self.assertIsNone(self.sensor.read())
            expected = self.bus.set_frame(zones, 0)  # Stream counter wraps to zero.
            self.assertEqual(self.sensor.read(), expected)
            self.sensor.stop()
            with self.assertRaises(OSError):
                self.sensor.read()

    def test_corrupt_and_missing_blocks(self):
        self.sensor.start()
        self.bus.set_frame(64)
        frame = bytearray(swapped(self.bus.frame))
        frame[-4] ^= 1
        self.bus.frame = swapped(frame)
        with self.assertRaisesRegex(OSError, 'corrupted'):
            self.sensor.read()
        self.bus.set_frame(64, 2)
        frame = bytearray(swapped(self.bus.frame))
        # Replace the first target-count block's index with an unknown index.
        index = frame.find(b'\x01\x04\x84\xdb')
        self.assertGreater(index, 0)
        frame[index + 3] = 0xee
        self.bus.frame = swapped(frame)
        with self.assertRaisesRegex(CorruptFrameError, r'missing result blocks: missing=\[db84\]') as caught:
            self.sensor.read()
        self.assertIn('word_swapped_hex=' + frame.hex(), str(caught.exception))
        self.assertIn('stream=2 ready=2 read_ms=', str(caught.exception))

    def test_missing_block_waits_for_new_acquisition(self):
        self.sensor.start()
        self.bus.set_frame(64, 2)
        bad = bytearray(swapped(self.bus.frame))
        bad[bad.find(b'\x01\x04\x84\xdb') + 3] = 0xee
        self.bus.frame = swapped(bad)
        with self.assertRaises(CorruptFrameError):
            self.sensor.read()
        self.assertIsNone(self.sensor.read())
        expected = self.bus.set_frame(64, 3)
        self.assertEqual(self.sensor.read(), expected)

    def test_ranging_uses_one_full_buffer_transaction(self):
        for zones in (16, 64):
            self.sensor.start(zones)
            expected = self.bus.set_frame(zones)
            self.bus.trace.clear()
            self.assertEqual(self.sensor.read(), expected)
            reads = [entry for entry in self.bus.trace if entry[0] == 'r']
            self.assertEqual([(entry[2], len(entry[3])) for entry in reads],
                             [(0, 4), (0, len(self.bus.frame))])
            self.sensor.stop()

    def test_corruption_is_not_blindly_reread_and_original_error_is_preserved(self):
        self.sensor.start()
        self.bus.set_frame(64, 139)
        read = self.bus.readfrom_mem
        attempts = []

        def consumed_output(address, register, size, mem_addr_size=8, mem_addr_le=False):
            data = bytearray(read(address, register, size, mem_addr_size, mem_addr_le))
            if register == 0 and len(data) == len(self.bus.frame):
                attempts.append(register)
                if len(attempts) == 1:
                    data[-1] ^= 1
                else:
                    data[:] = bytes(len(data))  # Blind reread would mask the error.
            return bytes(data)

        with patch.object(self.bus, 'readfrom_mem', side_effect=consumed_output):
            with self.assertRaisesRegex(CorruptFrameError, 'corrupted.*stream=139 ready=139'):
                self.sensor.read()
            self.assertIsNone(self.sensor.read())
        self.assertEqual(len(attempts), 1)
        expected = self.bus.set_frame(64, 140)
        self.assertEqual(self.sensor.read(), expected)

    def test_corruption_consumes_sequence_even_when_decode_fails(self):
        self.sensor.start()
        self.bus.set_frame(64, 2)
        bad = bytearray(self.bus.frame)
        bad[-1] ^= 1
        self.bus.frame = bad
        self.bus.trace.clear()
        with self.assertRaisesRegex(OSError, 'corrupted.*header=.*footer=.*stream=2.*ready=2.*bytes=.*read_ms='):
            self.sensor.read()
        self.assertEqual(len(self.bus.trace), 2)  # Ready header + one full read.
        self.assertIsNone(self.sensor.read())
        expected = self.bus.set_frame(64, 3)
        self.assertEqual(self.sensor.read(), expected)

    def test_zero_buffer_is_rejected_despite_matching_zero_ids(self):
        self.sensor.start()
        with self.assertRaisesRegex(CorruptFrameError, r'missing=\[df44,e084,db84\]'):
            self.sensor._decode(bytearray(320))

    def test_timeout_and_invalid_configuration(self):
        for zones, hz in ((32, 10), (64, 16), (16, 61), (64, 0)):
            with self.assertRaises(ValueError):
                self.sensor.start(zones, hz)
        with patch.object(self.sensor, '_read', return_value=b'\x00'):
            with self.assertRaisesRegex(OSError, 'timed out'):
                self.sensor._boot()
            with self.assertRaisesRegex(OSError, 'timed out'):
                self.sensor._poll(1, 0, 6, 1, 1)

    def test_missing_and_truncated_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(OSError):
                VL53L7CX(FakeSensor(), data_dir=directory)
            (Path(directory) / 'firmware.bin').write_bytes(b'short')
            with self.assertRaisesRegex(OSError, 'asset size'):
                VL53L7CX(FakeSensor(), data_dir=directory)


@unittest.skipUnless(shutil.which('cc'), 'C compiler required for ST reference comparison')
class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        reference = ROOT / 'tests/c_reference'
        uld = ROOT / 'tests/c_reference/uld'
        library = Path(cls.build.name) / 'reference.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-O0', '-I' + str(reference),
                        '-I' + str(uld), str(reference / 'reference.c'),
                        str(uld / 'vl53l7cx_api.c'), '-o', str(library)], check=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_uint16,
                                            ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32)
        cls.lib.ref_reset.argtypes = [cls.callback_type]

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def test_transactions_and_results_match_st_uld(self):
        c_bus = FakeSensor()
        errors = []

        def callback(read, register, pointer, size):
            try:
                if read:
                    data = c_bus.readfrom_mem(0x29, register, size, mem_addr_size=16)
                    ctypes.memmove(pointer, bytes(data), size)
                else:
                    c_bus.writeto_mem(0x29, register, ctypes.string_at(pointer, size), mem_addr_size=16)
                return 0
            except Exception as exc:
                errors.append(exc)
                return 255

        hook = self.callback_type(callback)
        self.lib.ref_reset(hook)
        self.assertEqual(self.lib.ref_init(), 0, errors)
        py_bus = FakeSensor()
        with patch('vl53l7cx._sleep_ms'):
            sensor = VL53L7CX(py_bus, data_dir=str(ASSETS))
            self.assertEqual(py_bus.trace, c_bus.trace)
            for zones, hz in ((64, 10), (16, 30)):
                c_bus.trace.clear()
                py_bus.trace.clear()
                self.assertEqual(self.lib.ref_start(zones, hz), 0, errors)
                sensor.start(zones, hz)
                self.assertEqual(py_bus.trace, c_bus.trace)
                expected = py_bus.set_frame(zones)
                c_bus.set_frame(zones)
                d = (ctypes.c_int16 * zones)()
                s = (ctypes.c_uint8 * zones)()
                t = (ctypes.c_uint8 * zones)()
                self.assertEqual(self.lib.ref_read(d, s, t, zones), 0, errors)
                self.assertEqual(sensor.read(), (list(d), list(s), list(t)))
                self.assertEqual(sensor.read(), None)
                self.assertEqual(expected, (list(d), list(s), list(t)))
                c_bus.trace.clear()
                py_bus.trace.clear()
                self.assertEqual(self.lib.ref_stop(), 0, errors)
                sensor.stop()
                self.assertEqual(py_bus.trace, c_bus.trace)
        self.assertEqual(errors, [])
