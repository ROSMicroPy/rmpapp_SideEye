"""Register/DCI emulator for host tests. No claim to model sensor physics."""
import struct


def swapped(data):
    return b''.join(bytes((data[i + 3], data[i + 2], data[i + 1], data[i]))
                    for i in range(0, len(data), 4))


class FakeSensor:
    def __init__(self):
        self.page = 0
        self.trace = []
        self.memory = bytearray(65536)
        self.dci = {}
        self.reply = b''
        self.stopping = False
        self.frame = None
        self.firmware = bytearray()
        # Nonuniform, signed calibration values catch endian/binning mistakes.
        self.nvm = bytearray((i * 37 + 11) & 255 for i in range(492))

    def writeto_mem(self, address, register, data, mem_addr_size=8, mem_addr_le=False):
        self._write(address, register, data, mem_addr_size, mem_addr_le)
        return len(data)

    def _write(self, address, register, data, mem_addr_size=8, mem_addr_le=False):
        assert address == 0x29 and mem_addr_size == 16 and not mem_addr_le and len(data) <= 256
        data = bytes(data)
        self.trace.append(('w', self.page, register, data))
        if register == 0x7fff:
            self.page = data[0]
            return
        if self.page in (9, 10, 11):
            self.firmware.extend(data)
            return
        if self.page == 0 and register == 0x14:
            self.stopping = data[0] == 1
        self.memory[register:register + len(data)] = data
        if self.page != 2 or register + len(data) != 0x3000:
            return
        tail = bytes(self.memory[0x2ff8:0x3000])
        if tail == b'\x00\x00\x00\x0f\x02\x02\x00\x24':
            self.reply = self.nvm
        elif tail == b'\x00\x00\x00\x0f\x00\x02\x00\x08':
            header = self.memory[0x2ff4:0x2ff8]
            index = int.from_bytes(header[:2], 'big')
            size = ((header[2] << 8) | header[3]) >> 4
            data = bytearray(self.dci.get(index, bytes(size)))
            if index == 0x5440:
                data[8:10] = self.dci[0xd968][:2]
            self.reply = swapped(bytes(4) + data + bytes(8))
        elif tail[:6] == b'\x00\x00\x00\x0f\x05\x01':
            size = int.from_bytes(tail[6:], 'big') - 8
            start = 0x3000 - size - 12
            index = int.from_bytes(self.memory[start:start + 2], 'big')
            self.dci[index] = swapped(self.memory[start + 4:start + 4 + size])

    def readfrom_mem(self, address, register, size, mem_addr_size=8, mem_addr_le=False):
        data = bytearray(size)
        assert address == 0x29 and mem_addr_size == 16 and not mem_addr_le
        assert len(data) <= 256 or (
            self.page == 2 and register == 0 and self.frame is not None
            and len(data) == len(self.frame))
        size = len(data)
        if self.page == 0 and register == 0:
            result = b'\xf0'
        elif self.page == 0 and register == 1:
            result = b'\x02'
        elif self.page == 0 and register == 6:
            result = b'\x80' if self.stopping else b'\x01'
        elif self.page == 0 and register == 7:
            result = b'\x84'
        elif self.page == 1 and register == 0x21:
            result = b'\x10'
        elif self.page == 2 and register == 0x2c00:
            result = b'\x02\x03\x00\x00'
        elif self.page == 2 and 0x2c04 <= register < 0x2c04 + len(self.reply):
            start = register - 0x2c04
            result = self.reply[start:start + size]
        elif self.page == 2 and self.frame is not None and register < len(self.frame):
            result = self.frame[register:register + size]
        else:
            result = bytes(size)
        assert len(result) == size, (register, size, len(result))
        data[:] = result
        self.trace.append(('r', self.page, register, bytes(data)))
        return bytes(data)

    def set_frame(self, zones, sequence=1):
        # Build from the output list requested from firmware, not the Python decoder.
        output = struct.unpack('<12I', self.dci[0xd980])
        enables = struct.unpack('<4I', self.dci[0xd970])[0]
        frame = bytearray(16)
        frame[:4] = bytes((0x10, 5, 5, sequence))
        frame[8:10] = b'\x12\x34'
        distances = [i * 101 - 40 for i in range(zones)]
        statuses = [5 if i % 4 else 9 for i in range(zones)]
        targets = [1 if i % 7 else 0 for i in range(zones)]
        for i, header in enumerate(output):
            if not enables & (1 << i):
                continue
            index = header >> 16
            count, kind = (header >> 4) & 0xfff, header & 15
            size = count * kind if 1 < kind < 13 else count
            payload = bytes(size)
            if index == 0xdf44:
                payload = struct.pack('<%dh' % zones, *distances)
            elif index == 0xe084:
                payload = bytes(statuses)
            elif index == 0xdb84:
                payload = bytes(targets)
            frame.extend(struct.pack('<I', header))
            frame.extend(payload)
        frame.extend(b'\x0f\x00\x00\x00\x12\x34\x00\x00')
        assert len(frame) == struct.unpack('<2I', self.dci[0xd968])[0]
        self.frame = swapped(frame)
        return ([max(0, d // 4) for d in distances],
                [s if t else 255 for s, t in zip(statuses, targets)], targets)
