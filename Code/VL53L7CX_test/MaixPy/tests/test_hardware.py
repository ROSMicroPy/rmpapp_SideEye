"""Verify MaixPy pin routing and enable ordering without a board."""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hardware


class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.pinmap = Mock()
        self.i2c = Mock()
        self.gpio = Mock()
        self.err = Mock()
        self.modules = patch.dict(sys.modules, {
            'maix': types.SimpleNamespace(err=self.err),
            'maix.peripheral': types.SimpleNamespace(
                i2c=self.i2c, pinmap=self.pinmap, gpio=self.gpio),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_i2c5_pins_and_master_mode(self):
        self.assertIs(hardware.open_i2c(), self.i2c.I2C.return_value)
        self.assertEqual(self.pinmap.set_pin_function.call_args_list,
                         [call('A15', 'I2C5_SCL'), call('A27', 'I2C5_SDA')])
        self.i2c.I2C.assert_called_once_with(5, self.i2c.Mode.MASTER, freq=400_000)

    def test_pin_mapping_error_prevents_bus_open(self):
        self.err.check_raise.side_effect = RuntimeError('pin mapping failed')
        with self.assertRaises(RuntimeError):
            hardware.open_i2c()
        self.i2c.I2C.assert_not_called()

    def test_enable_a24_is_high_before_settle_delay(self):
        events = []
        self.gpio.GPIO.return_value.value.side_effect = lambda v: events.append(('value', v))
        with patch.object(hardware.time, 'sleep', side_effect=lambda s: events.append(('sleep', s))):
            enable = hardware.enable_sensor()
        self.pinmap.set_pin_function.assert_called_once_with('A24', 'GPIOA24')
        self.gpio.GPIO.assert_called_once_with('GPIOA24', self.gpio.Mode.OUT)
        self.assertIs(enable, self.gpio.GPIO.return_value)
        self.assertEqual(events, [('value', 1), ('sleep', 0.01)])
