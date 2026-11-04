"""Run on MaixCAM after stopping main.py; exercises the sensor without REST."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api import ticks_ms, ticks_diff
import time
import binascii


def phase(sensor, hz, duration_s=60):
    from vl53l7cx import CorruptFrameError
    sensor.start(64, hz)
    good = bad = not_ready = 0
    max_read_ms = 0
    started = ticks_ms()
    try:
        while ticks_diff(ticks_ms(), started) < duration_s * 1000:
            before = ticks_ms()
            try:
                result = sensor.read()
            except CorruptFrameError as exc:
                bad += 1
                if bad <= 3:
                    print('Rejected:', exc)
                    # Capture the *original* failed read, without touching I2C.
                    print('word_swapped_hex:', binascii.hexlify(sensor._frame).decode())
            else:
                if result is None:
                    not_ready += 1
                else:
                    good += 1
            elapsed = ticks_diff(ticks_ms(), before)
            max_read_ms = max(max_read_ms, elapsed)
            time.sleep(0.005)
    finally:
        sensor.stop()
    elapsed_ms = ticks_diff(ticks_ms(), started)
    total = good + bad
    print('SUMMARY hz=%d good=%d rejected=%d rejected_pct=%.2f '
          'not_ready=%d elapsed_ms=%d max_call_ms=%d' %
          (hz, good, bad, 100 * bad / total if total else 0,
           not_ready, elapsed_ms, max_read_ms))
    return good, bad


def run(duration_s=60):
    from hardware import open_i2c, enable_sensor
    from vl53l7cx import VL53L7CX, DRIVER_VERSION

    if duration_s <= 0:
        raise ValueError('duration_s must be positive')
    print('Diagnostic driver:', DRIVER_VERSION, 'REST must be stopped')
    print('Each phase lasts', duration_s, 'seconds after initialization.')
    print('max_call_ms includes decode and any diagnostic printing.')
    enable = enable_sensor()
    try:
        for bus_hz, ranging_hz in ((400_000, 10), (400_000, 2), (100_000, 2)):
            print('\nPHASE requested_i2c_hz=%d ranging_hz=%d zones=64' % (bus_hz, ranging_hz))
            i2c = open_i2c(bus_hz)
            print('I2C:', i2c)
            sensor = VL53L7CX(i2c, config.SENSOR_ADDRESS)
            try:
                phase(sensor, ranging_hz, duration_s)
            finally:
                sensor.stop()
            del sensor, i2c
    finally:
        enable.value(0)
    print('\nDiagnostic complete. Restart main.py to resume the REST application.')


if __name__ == '__main__':
    run()
