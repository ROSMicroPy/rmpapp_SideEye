# Sensor assets

These files contain ST's sensor firmware and configuration data. They execute on
the VL53L7CX, not on the MaixCAM. The host app and driver use MaixPy (Python 3).
Copy this whole directory alongside `vl53l7cx.py` on the device.

Extracted from STMicroelectronics X-CUBE-TOF1 commit
`c12709c3ac802d91dd2a215178f53cb94c024709`,
`Drivers/BSP/Components/vl53l7cx/modules/vl53l7cx_buffers.h`.

The retained header is in `../tests/c_reference/uld/`. To reproduce the binaries:

```sh
python3 Code/VL53L7CX_test/MaixPy/tools/extract_sensor_data.py
```

`manifest.json` records lengths and SHA-256 checksums. The configuration selects
one output target per zone (`VL53L7CX_FW_NBTAR_RANGING` is 2 internally, per ST's
one-target build). Firmware size is 86,016 bytes; initialization streams it in
256-byte chunks. The other three assets total 1,788 bytes.

Retain `LICENSE.md` when redistributing these files or the derived Python driver.
