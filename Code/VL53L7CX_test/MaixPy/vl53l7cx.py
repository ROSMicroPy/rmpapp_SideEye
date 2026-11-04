"""MaixPy implementation of the ST VL53L7CX ULD operations used by this app.

Copyright (c) 2021 STMicroelectronics. All rights reserved.
Derived from ST's ULD; BSD-3-Clause, see
vl53l7cx_data/LICENSE.md. One target per zone, 4x4 or 8x8.
No native module is needed. Sensor firmware is streamed from the filesystem.
"""
import struct
import time
import binascii

DRIVER_VERSION = 'maixpy-1'


class CorruptFrameError(OSError):
    """A result failed integrity checks; no distances may be published."""


def _sleep_ms(ms):
    time.sleep(ms / 1000)


def _swap_words(data):
    """Convert each 32-bit word between sensor and host byte order in place."""
    if len(data) % 4:
        raise ValueError('Unaligned sensor buffer')
    for i in range(0, len(data), 4):
        data[i], data[i + 3] = data[i + 3], data[i]
        data[i + 1], data[i + 2] = data[i + 2], data[i + 1]
    return data


def _average_grid(data, offset, fmt):
    """ST's 2x2 binning of a calibration grid, including C integer rounding."""
    stride = struct.calcsize(fmt)
    grid = [struct.unpack_from(fmt, data, offset + stride * i)[0] for i in range(64)]
    for y in range(4):
        for x in range(4):
            i = 2 * x + 16 * y
            total = sum(grid[j] for j in (i, i + 1, i + 8, i + 9))
            if fmt == '<I':
                total &= 0xffffffff  # Match uint32_t addition in ST's ULD.
            value = total // 4 if total >= 0 else -((-total) // 4)
            struct.pack_into(fmt, data, offset + stride * (x + 4 * y), value)
    data[offset + 16 * stride:offset + 64 * stride] = bytes(48 * stride)


class VL53L7CX:
    def __init__(self, i2c, address=0x29, data_dir=None):
        if not 8 <= address <= 0x77:
            raise ValueError('Invalid 7-bit I2C address')
        self.i2c = i2c
        self.address = address
        if data_dir is None:
            prefix = __file__.rsplit('/', 1)[0] + '/' if '/' in __file__ else ''
            data_dir = prefix + 'vl53l7cx_data'
        self.data_dir = data_dir.rstrip('/')
        self.running = False
        self.zones = 64
        self._stream = 255
        self._frame = None
        # Verify sizes before changing the sensor. Firmware is never read in full.
        for name, size in (('firmware.bin', 0x15000), ('configuration.bin', 972),
                           ('xtalk.bin', 776), ('nvm_cmd.bin', 40)):
            with open(self.data_dir + '/' + name, 'rb') as source:
                source.seek(0, 2)
                if source.tell() != size:
                    raise OSError('Invalid sensor asset size: ' + name)
        self._byte(0x7fff, 0)
        alive = self._read(0, 1)[0] == 0xf0
        revision = self._read(1, 1)[0]
        self._byte(0x7fff, 2)
        if not alive or revision != 2:
            raise OSError('VL53L7CX not detected')
        self._initialize()

    def _asset(self, name):
        with open(self.data_dir + '/' + name, 'rb') as source:
            return bytearray(source.read())

    def _write(self, register, data):
        for offset in range(0, len(data), 256):
            chunk = bytes(data[offset:offset + 256])
            written = self.i2c.writeto_mem(self.address, register + offset, chunk,
                                          mem_addr_size=16, mem_addr_le=False)
            if written != len(chunk):
                raise OSError('VL53L7CX I2C write failed at 0x%04x' % (register + offset))

    def _read_into(self, register, data):
        for offset in range(0, len(data), 256):
            size = min(256, len(data) - offset)
            data[offset:offset + size] = self._read(register + offset, size)
        return data

    def _read(self, register, size):
        data = self.i2c.readfrom_mem(self.address, register, size,
                                     mem_addr_size=16, mem_addr_le=False)
        if data is None or len(data) != size:
            raise OSError('VL53L7CX I2C read failed at 0x%04x' % register)
        return bytearray(data)

    def _byte(self, register, value):
        self._write(register, bytes((value,)))

    def _sequence(self, pairs):
        for register, value in pairs:
            self._byte(register, value)

    def _poll(self, size, pos, register, mask, expected):
        for _ in range(200):
            data = self._read(register, size)
            _sleep_ms(10)
            if size >= 4 and data[2] >= 0x7f:
                raise OSError('VL53L7CX MCU error during command')
            if data[pos] & mask == expected:
                return
        raise OSError('VL53L7CX command timed out at 0x%04x' % register)

    def _command_done(self):
        self._poll(4, 1, 0x2c00, 0xff, 3)

    def _boot(self):
        for _ in range(500):
            status = self._read(6, 1)[0]
            if status & 0x80:
                error = self._read(7, 1)[0]
                if error:
                    raise OSError('VL53L7CX boot error %d' % error)
                return
            _sleep_ms(1)
            if status & 1:
                return
        raise OSError('VL53L7CX MCU boot timed out')

    def _upload_firmware(self):
        chunk = bytearray(256)
        with open(self.data_dir + '/firmware.bin', 'rb') as source:
            for page, size in ((9, 0x8000), (10, 0x8000), (11, 0x5000)):
                self._byte(0x7fff, page)
                for register in range(0, size, len(chunk)):
                    if source.readinto(chunk) != len(chunk):
                        raise OSError('Truncated VL53L7CX firmware')
                    self._write(register, chunk)

    def _initialize(self):
        self._sequence(((0x7fff, 0), (9, 4), (0xf, 0x40), (0xa, 3)))
        self._read(0x7fff, 1)
        self._sequence(((0xc, 1), (0x101, 0), (0x102, 0), (0x10a, 1),
                        (0x4002, 1), (0x4002, 0), (0x10a, 3), (0x103, 1),
                        (0xc, 0), (0xf, 0x43)))
        _sleep_ms(1)
        self._sequence(((0xf, 0x40), (0xa, 1)))
        _sleep_ms(100)
        self._byte(0x7fff, 0)
        self._poll(1, 0, 6, 0xff, 1)
        self._sequence(((0xe, 1), (0x7fff, 2), (3, 0x0d), (0x7fff, 1)))
        self._poll(1, 0, 0x21, 0x10, 0x10)
        self._byte(0x7fff, 0)
        self._read(0x7fff, 1)
        self._sequence(((0xc, 1), (0x7fff, 0), (0x101, 0), (0x102, 0),
                        (0x10a, 1), (0x4002, 1), (0x4002, 0), (0x10a, 3),
                        (0x103, 1), (0x400f, 0), (0x21a, 0x43), (0x21a, 3),
                        (0x21a, 1), (0x21a, 0), (0x219, 0), (0x21b, 0),
                        (0x7fff, 0)))
        self._read(0x7fff, 1)
        self._sequence(((0xc, 0), (0x7fff, 1), (0x20, 7), (0x20, 6)))
        self._upload_firmware()
        self._sequence(((0x7fff, 1), (0x7fff, 2), (3, 0x0d), (0x7fff, 1)))
        self._poll(1, 0, 0x21, 0x10, 0x10)
        self._byte(0x7fff, 0)
        self._read(0x7fff, 1)
        self._sequence(((0xc, 1), (0x7fff, 0), (0x114, 0), (0x115, 0),
                        (0x116, 0x42), (0x117, 0), (0xb, 0)))
        self._read(0x7fff, 1)
        self._sequence(((0xc, 0), (0xb, 1)))
        self._boot()
        self._byte(0x7fff, 2)
        self._write(0x2fd8, self._asset('nvm_cmd.bin'))
        self._poll(4, 0, 0x2c00, 0xff, 2)
        nvm = self._read_into(0x2c04, bytearray(492))
        self._offset = nvm[:488]
        self._send_offset(16)
        self._send_xtalk(16)
        self._write(0x2c34, self._asset('configuration.bin'))
        self._command_done()
        self._dci_write(0xdb80, b'\x01\x00\x01\x00')
        self._dci_write(0xd964, b'\x01\x00\x00\x00')
        self._replace(0xe108, 40, 0x26, b'\x01')
        self._replace(0xe108, 40, 0x25, b'\x01')

    def _send_offset(self, zones):
        # The ULD shifts eight bytes left, then replaces the final eight bytes.
        data = bytearray(self._offset)
        if zones == 16:
            data[0x10:0x18] = b'\x0f\x04\x04\x00\x08\x10\x10\x07'
            _swap_words(data)
            _average_grid(data, 0x3c, '<I')
            _average_grid(data, 0x140, '<h')
            _swap_words(data)
        data[:480] = data[8:488]
        data[0x1e0:0x1e8] = b'\x00\x00\x00\x0f\x03\x01\x01\xe4'
        self._write(0x2e18, data)
        self._command_done()

    def _send_xtalk(self, zones):
        data = self._asset('xtalk.bin')
        if zones == 16:
            data[8:16] = b'\x0f\x04\x04\x17\x08\x10\x10\x07'
            data[0x20:0x28] = b'\x00\x78\x00\x08\x00\x00\x00\x08'
            _swap_words(data)
            _average_grid(data, 0x34, '<I')
            _swap_words(data)
            data[0x134:0x138] = b'\xa0\xfc\x01\x00'
            data[0x78:0x7c] = bytes(4)
        self._write(0x2cf8, data)
        self._command_done()

    @staticmethod
    def _dci_header(index, size):
        if size % 4 or not 0 < size <= 1024:
            raise ValueError('Invalid DCI data size')
        return bytes((index >> 8, index & 255, (size >> 4) & 255, (size & 15) << 4))

    def _dci_read(self, index, size):
        command = self._dci_header(index, size) + b'\x00\x00\x00\x0f\x00\x02\x00\x08'
        self._write(0x2ff4, command)
        self._command_done()
        data = _swap_words(self._read_into(0x2c04, bytearray(size + 12)))
        return data[4:4 + size]

    def _dci_write(self, index, data):
        size = len(data)
        header = self._dci_header(index, size)
        payload = _swap_words(bytearray(data))
        footer = b'\x00\x00\x00\x0f\x05\x01' + struct.pack('>H', size + 8)
        self._write(0x3000 - (size + 12), header + payload + footer)
        self._command_done()

    def _replace(self, index, size, position, value):
        data = self._dci_read(index, size)
        data[position:position + len(value)] = value
        self._dci_write(index, data)

    def start(self, resolution=64, frequency=10):
        if resolution not in (16, 64) or not 1 <= frequency <= (15 if resolution == 64 else 60):
            raise ValueError('Use 16 zones at 1-60 Hz or 64 zones at 1-15 Hz')
        if self.running:
            self.stop()
        dss = self._dci_read(0xad38, 16)
        dss[4] = dss[6] = 64 if resolution == 16 else 16
        dss[9] = 4 if resolution == 16 else 1
        self._dci_write(0xad38, dss)
        zone = self._dci_read(0x5450, 8)
        zone[0] = zone[1] = 4 if resolution == 16 else 8
        zone[4] = zone[5] = 8 if resolution == 16 else 4
        self._dci_write(0x5450, zone)
        self._send_offset(resolution)
        self._send_xtalk(resolution)
        self._replace(0x5458, 4, 1, bytes((frequency,)))
        zone = self._dci_read(0x5450, 8)
        if zone[0] * zone[1] != resolution:
            raise OSError('VL53L7CX resolution readback mismatch')
        self.zones = resolution
        self._stream = 255
        output = [0x0000000d, 0x54b400c0, 0x54c00040, 0x54d00104,
                  0x55d00404, 0xdb840401, 0xdbc40404, 0xdec40402,
                  0xdf440402, 0xe0440401, 0xe0840401, 0xd85808c0]
        enables = 7 | 32 | 256 | 1024
        size = 24
        for i, header in enumerate(output):
            if not enables & (1 << i):
                continue
            kind = header & 15
            count = (header >> 4) & 0xfff
            if 1 <= kind < 13:
                count = resolution
                output[i] = (header & 0xffff000f) | (count << 4)
                size += kind * count
            else:
                size += count
            size += 4
        self._dci_write(0xd980, struct.pack('<12I', *output))
        self._dci_write(0xd968, struct.pack('<2I', size, 13))
        self._dci_write(0xd970, struct.pack('<4I', enables, 0, 0, 0xc0000000))
        self._frame = bytearray(size)
        self._sequence(((0x7fff, 0), (9, 5), (0x7fff, 2)))
        # Mark as running before the command so cleanup can stop a partial start.
        self.running = True
        try:
            self._write(0x2ffc, b'\x00\x03\x00\x00')
            self._command_done()
            actual = struct.unpack_from('<H', self._dci_read(0x5440, 12), 8)[0]
            if actual != size:
                raise OSError('VL53L7CX frame size mismatch')
        except Exception:
            try:
                self.stop()
            except Exception:
                pass
            raise

    def read(self):
        if not self.running:
            raise OSError('Sensor is not ranging')
        header = self._read(0, 4)
        if (header[0] == self._stream or header[0] == 255 or header[1] != 5
                or header[2] & 5 != 5 or header[3] & 0x10 != 0x10):
            if header[3] & 0x80:
                raise OSError('VL53L7CX ranging error %d' % header[2])
            return None
        # Read the result in one transaction. Splitting it into chunks leaves
        # gaps in which the sensor can replace the output with its next frame.
        # Keep firmware/config transfers chunked; only ranging uses this buffer.
        started = int(time.monotonic() * 1000)
        self._frame[:] = self._read(0, len(self._frame))
        ended = int(time.monotonic() * 1000)
        elapsed = ended - started
        stream = self._frame[0]
        # Like ST's get_ranging_data, consume this stream before decoding.
        # Reading the output is not a harmless peek: never immediately reread
        # a rejected result. The next call must pass check_data_ready again.
        self._stream = stream
        _swap_words(self._frame)
        if self._frame[8:10] != self._frame[-4:-2]:
            raise CorruptFrameError(
                'VL53L7CX corrupted frame: header=%02x%02x footer=%02x%02x '
                'stream=%d ready=%d bytes=%d read_ms=%d' %
                (self._frame[8], self._frame[9], self._frame[-4], self._frame[-3],
                 stream, header[0], len(self._frame), elapsed))
        try:
            return self._decode(self._frame)
        except CorruptFrameError as exc:
            raise CorruptFrameError('%s; stream=%d ready=%d read_ms=%d' %
                                    (exc, stream, header[0], elapsed))

    def _decode(self, data):
        if data[8:10] != data[-4:-2]:
            raise CorruptFrameError('VL53L7CX corrupted frame')
        found = {}
        offset = 16
        while offset < len(data) - 4:
            header = struct.unpack_from('<I', data, offset)[0]
            kind, count, index = header & 15, (header >> 4) & 0xfff, header >> 16
            size = kind * count if 1 < kind < 13 else count
            offset += 4
            if offset + size > len(data) - 4:
                raise self._block_error('truncated result block', data, found, offset - 4)
            if index in (0xdf44, 0xe084, 0xdb84):
                expected_kind = 2 if index == 0xdf44 else 1
                if kind != expected_kind or count != self.zones or index in found:
                    raise self._block_error('invalid result block', data, found, offset - 4)
                if index == 0xdf44:
                    found[index] = [max(0, struct.unpack_from('<h', data, offset + i * 2)[0] // 4)
                                    for i in range(self.zones)]
                else:
                    found[index] = list(data[offset:offset + size])
            offset += size
        if offset != len(data) - 4 or len(found) != 3:
            raise self._block_error('missing result blocks', data, found, offset)
        distances, statuses, targets = found[0xdf44], found[0xe084], found[0xdb84]
        for i, count in enumerate(targets):
            if count == 0:
                statuses[i] = 255
        return distances, statuses, targets

    def _block_error(self, reason, data, found, offset):
        # Only construct diagnostics on failure, not on every acquisition.
        missing = ','.join('%04x' % index for index in (0xdf44, 0xe084, 0xdb84)
                           if index not in found)
        present = ','.join('%04x' % index for index in found)
        return CorruptFrameError(
            'VL53L7CX %s: missing=[%s] found=[%s] offset=%d bytes=%d '
            'word_swapped_hex=%s' %
            (reason, missing, present, offset, len(data), binascii.hexlify(data).decode()))

    def stop(self):
        if not self.running:
            return
        try:
            flag = struct.unpack('<I', self._read(0x2ffc, 4))[0]
            if flag != 0x4ff:
                self._sequence(((0x7fff, 0), (0x15, 0x16), (0x14, 1)))
                self._poll_stop()
            status = self._read(6, 1)[0]
            if status & 0x80:
                error = self._read(7, 1)[0]
                if error not in (0, 0x84, 0x85):
                    raise OSError('VL53L7CX stop error %d' % error)
        finally:
            self._sequence(((0x7fff, 0), (0x14, 0), (0x15, 0), (9, 4), (0x7fff, 2)))
            self.running = False

    def _poll_stop(self):
        for _ in range(500):
            status = self._read(6, 1)[0]
            _sleep_ms(10)
            if status & 0x80:
                return
        raise OSError('VL53L7CX stop timed out')
