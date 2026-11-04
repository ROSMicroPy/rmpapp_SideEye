"""Rebuild the binary sensor assets from the retained ST header (host Python)."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / 'tests/c_reference/uld/vl53l7cx_buffers.h'
ASSETS = {
    'VL53L7CX_FIRMWARE': ('firmware.bin', 0x15000),
    'VL53L7CX_DEFAULT_CONFIGURATION': ('configuration.bin', 972),
    'VL53L7CX_DEFAULT_XTALK': ('xtalk.bin', 776),
    'VL53L7CX_GET_NVM_CMD': ('nvm_cmd.bin', 40),
}


def extract():
    source = HEADER.read_text()
    destination = ROOT / 'vl53l7cx_data'
    destination.mkdir(exist_ok=True)
    manifest = {}
    for symbol, (filename, expected) in ASSETS.items():
        match = re.search(r'const uint8_t\s+' + symbol + r'\[\]\s*=\s*\{(.*?)\};', source, re.S)
        if not match:
            raise ValueError('Array missing: ' + symbol)
        body = re.sub(r'/\*.*?\*/|//[^\n]*', '', match[1], flags=re.S)
        # ST uses two internal ranging targets when one output target is selected.
        body = body.replace('VL53L7CX_FW_NBTAR_RANGING', '2')
        values = bytes(int(token.strip(), 0) for token in body.split(',') if token.strip())
        if len(values) != expected:
            raise ValueError('%s: expected %d bytes, got %d' % (symbol, expected, len(values)))
        (destination / filename).write_bytes(values)
        manifest[filename] = {'size': len(values), 'sha256': hashlib.sha256(values).hexdigest()}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    extract()
