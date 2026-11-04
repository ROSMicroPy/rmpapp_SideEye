# SideEye VL53L7CX MaixPy project

MaixCAM / MaixCAM-Pro application for MaixPy (Python 3). Reads the VL53L7CX
and serves the existing React visualization API using standard `asyncio`.
Default acquisition is 8×8 at 10 Hz, with one target per zone.

## Wiring and configuration

| Sensor signal | MaixCAM pin |
| --- | --- |
| SCL | A15 / I2C5_SCL |
| SDA | A27 / I2C5_SDA |
| Enable / LPn (active high) | A24 / GPIOA24 |
| GND | Common ground |

Use the sensor breakout's appropriate power supply and I2C pull-ups. The device
address is `0x29` (7-bit). The application maps A24 to a GPIO output, asserts it
high, and waits 10 ms before accessing the sensor. It holds the GPIO object
through acquisition and drives enable low after stopping or before retrying.

`config.py` contains pin assignments, resolution, ranging frequency, HTTP port,
CORS origin, and retry/stale intervals. I2C5 is supplied by the MaixCAM Linux
software I2C driver; the requested frequency does not guarantee its actual bus
rate. Validate acquisition timing on the board.

Configure Wi-Fi in the device Settings app. The service uses the existing Linux
network connection and listens on all interfaces at port 80. If that port is
already occupied or unavailable to your account, change `HTTP_PORT` (e.g. 8080).
No Wi-Fi credentials or connection management are embedded in this application.
`asyncio` is assumed installed.

## Run and package

Open this directory as a project in MaixVision and run `main.py`, with the other
Python modules and the complete `vl53l7cx_data` and `marble_detect` directories uploaded alongside it.
Alternatively, copy the project to the device and run `python3 main.py` there.

For an installable application, run `maixtool release` from this directory, or
use MaixVision's packaging function. `app.yaml` explicitly includes the runtime
files and ST firmware/license assets, excluding host tests and development tools.
`maixtool deploy` can serve the package for local installation. Packaging requires
maixtool on the development computer; sensor operation requires the device.

The application honors `maix.app.need_exit()` and Ctrl-C, cancels acquisition,
stops ranging, disables the sensor, and closes the REST listener on shutdown.

## React connection and REST contract

Run the sibling `../react` app and enter `http://<maixcam-ip>` (include the port
if changed). Use the IP shown in Settings or MaixVision. The paired viewer polls camera and ToF independently. `CORS_ORIGIN` defaults to `*` for development.

- `GET /api/frame`: latest valid frame, or HTTP 503 during a fault/stale state.
- `GET /api/health`: readiness, frame age, and error; HTTP 200 or 503.
- `GET /api/config`: sensor, rows, columns, ranging rate, units, native ordering,
  orientation, and accepted status codes.
- `OPTIONS`: HTTP 204 with CORS headers.

Frames retain `sensor`, `sequence`, `timestamp_ms`, `rows`, `cols`, `units`,
`distance_mm`, `target_status`, `targets_detected`, and `age_ms`. The three grids
are oriented row-major 8×8 or 4×4. Distances are millimeters; invalid/no-target zones use
JSON null. Status 5 or 9 with a detected target is valid. Timestamps use the
host monotonic clock, not UTC. The viewer's stale threshold is also 2000 ms;
coordinate any threshold changes with its `src/sensor.js`.

The driver preserves ST initialization/calibration, streamed firmware upload,
and complete-frame integrity checks. Ranging reads use one I2C transaction per
frame; configuration and firmware transfers use 256-byte chunks. MaixPy short
reads, null reads, and failed/short writes raise errors. Rejected frames never
replace cached data. Persistent faults trigger a retry after five seconds.

Sensor calls are synchronous and acquisition yields to HTTP between readiness
polls. Firmware upload and recovery can temporarily delay HTTP responses; the
viewer already retries failed/timed-out requests. This initial project keeps
all sensor access serialized. A future worker can isolate lengthy sensor calls
if uninterrupted HTTP during reinitialization is required.

## Development checks

From the repository root:

```sh
python3 -m unittest discover -s Code/VL53L7CX_test/MaixPy/tests -v
```

Tests cover REST/CORS, stale/error behavior, recovery, MaixPy hardware calls,
transfer errors, firmware checksums, and transaction parity with ST's retained
C ULD (requires a host C compiler). These tests emulate hardware.

For a physical sensor check, stop the application and run
`python3 tools/diagnose_sensor.py` on the MaixCAM. It uses the same pins/enable
and prints acquisition and rejection counts at several requested bus/frame
rates. Restart the application afterward. Never run both against the sensor
at the same time.

`tools/extract_sensor_data.py` regenerates the binary assets from the retained
ST header. Keep `vl53l7cx_data/LICENSE.md` with redistributed firmware and driver.

## Platform references

- [MaixPy I2C and pin mapping](https://wiki.sipeed.com/maixpy/doc/en/peripheral/i2c.html)
- [MaixPy I2C API](https://wiki.sipeed.com/maixpy/api/maix/peripheral/i2c.html)
- [MaixPy GPIO](https://wiki.sipeed.com/maixpy/doc/en/peripheral/gpio.html)
- [Application packaging](https://wiki.sipeed.com/maixpy/doc/en/basic/app.html)

The previous MicroPython entry point, machine/network dependencies, Wi-Fi
reconnect loop, uasyncio/tick fallbacks, manual garbage collection, and
MicroPython-only smoke test have been removed. Sensor assets and host reference
tests remain because they are still required/useful for this driver.

## Integrated camera and detection API

`marble_detect/` contains the independent copy of the original marble detector,
its camera worker, and tuning documentation. `app.yaml` includes this directory;
the application has no dependency on the sibling `MarbleDetect` directory.

| Endpoint | Response |
| --- | --- |
| `GET /api/camera` | Atomic JSON snapshot: annotated JPEG in `image_base64`, `image_mime`, `objects`, `width`, `height`, `sequence`, `timestamp_ms`, `age_ms`, `detector`, and `geometry`. |
| `GET /api/image.jpg` | Latest annotated JPEG bytes, `Content-Type: image/jpeg`. |
| `GET /api/detections` | Same snapshot metadata and objects, without the image data. |

All three support CORS and return 503 JSON when the camera is disabled, failed,
or stale. `/api/camera` is the viewer's endpoint so image and objects always come
from the same acquisition. Separate calls to image/detections may see different
sequences; use the combined endpoint when correspondence matters. A valid frame
with no candidates returns `objects: []`, not an error. Each object contains:

```json
{"id":0,"label":"marble candidate","bbox":{"x":137,"y":67,"width":37,"height":37},"center":{"x":155,"y":85},"radius_px":15,"magnitude":2400}
```

The existing distance endpoints retain their contract. `/api/health` still means
ToF health; camera endpoints report camera health independently. Camera and ToF
are acquired and polled independently, not hardware-synchronized. Compare their
monotonic `timestamp_ms` values if temporal association is needed. A camera error
does not clear or invalidate ToF frames, and vice versa.

## Matched camera / ToF view

The React viewer uses equally sized square panels, left for video/objects and
right for the populated ToF module. The second module remains unpopulated; no
readings are synthesized for it. The populated sensor is 60 mm to the right of
the lens **when looking at the front of the camera**. In forward-looking image
coordinates this is `SENSOR_OFFSET_X_MM = -60`.

Nominal defaults are stock GC4653 lens **81° H × 51° V** and VL53L7CX **60° H ×
60° V**. Capture uses 320×180 to retain 16:9. The viewport covers the ToF field of
view. Camera projection uses `tan(camera_FoV/2) / tan(ToF_FoV/2)` for each axis.
The wider camera edges are cropped and the narrower vertical coverage leaves
empty bands. This avoids assuming that equal panel sizes alone mean equal scale.
Object metadata still describes the complete camera image.

The comparison-distance slider sets an optical-axis depth plane D in millimeters
(default 1000). The camera center shifts by `-offset_x / (2 D tan(ToF_HFoV/2))`
viewport widths. Set D to the approximate marble depth. This assumes parallel
axes, no vertical/forward baseline, centered optics and a pinhole lens. It is a
nominal comparison, **not calibrated sensor fusion**: lens distortion, ISP crop,
module rotation/tilt, coarse ToF zone footprint, and objects at different depths
prevent exact overlap. Check rotation/mirroring with a target in a known corner.
No camera candidate is automatically assigned a distance from an unrelated zone.

Nominal specifications:
[Sipeed camera modules](https://wiki.sipeed.com/hardware/en/maixcam/cameras.html),
[ST VL53L7CX datasheet](https://www.st.com/resource/en/datasheet/vl53l7cx.pdf).

## Runtime camera controls

`GET /api/camera/settings` returns `acquisition_enabled` and `detection_enabled`.
`POST /api/camera/settings` accepts a JSON object with either or both boolean
fields (Content-Type: application/json). These are device-wide, in-memory settings;
restart restores the configuration defaults. Viewing mode remains local to each
browser and does not change the device settings.

Disabling acquisition forces detection off, immediately invalidates cached frames,
and makes the camera worker close the camera after its current operation finishes.
Frames in progress are discarded when settings change. Re-enabling acquisition
opens/warms up the camera again with detection still off until explicitly enabled.
Disabling only detection skips circle finding and all annotations, returns the raw
JPEG with `objects: []`, `detection_enabled: false`, and `detector: "disabled"`.
The camera thread stays available even if CAMERA_ENABLED is false at startup,
allowing acquisition to be enabled through the API. ToF operation is unaffected.


## ToF matrix orientation

Startup defaults in `config.py`: `TOF_ROTATION` (0, 90, 180, or 270 clockwise),
`TOF_FLIP_H`, and `TOF_FLIP_V` (booleans). Rotation is applied first, followed by
flips on the displayed horizontal and vertical axes. Both flips can be enabled.

`GET /api/tof/settings` returns `rotation`, `flip_h`, and `flip_v`.
`POST /api/tof/settings` accepts a JSON object containing any subset of those
fields. Invalid values return 400 without changing settings. The React display
controls load these settings on connection and update the device. UI changes
apply immediately to all clients but are in memory; restart restores config.py
values. Reconnect to refresh selectors if another viewer changes the settings.

`/api/frame` transforms distance, status, and target-count grids together at
response time. Its `zone_ids` matrix maps each displayed cell to its original
sensor zone, and `orientation` describes the applied transform. The raw sensor
cache, acquisition timestamps, and sequence numbers are unchanged. `/api/config`
reports `order: "oriented row-major"` and the current orientation. Clients must
not apply the transform a second time. React uses `zone_ids` to keep native zone
selection and the inspector consistent as orientation changes. No camera-image
rotation is performed by these controls.
