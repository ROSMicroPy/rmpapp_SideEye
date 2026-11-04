# VL53L7CX depth monitor

React app for the MaixCAM REST service in `../MaixPy`. Displays the annotated camera image and object details on the left, and the actual
8×8 (or 4×4) sensor grid on the right, with selectable zones, distance statistics, confidence
filtering, and mounting-orientation controls. There is no simulated-data fallback.

## Run

Use Node.js 20.19+ or 22.12+ (Vite requirement: https://vite.dev/guide/).

```sh
cd react
npm install
npm run dev
```

Open the local URL printed by Vite, normally `http://localhost:5173`. Enter the
MaixCAM URL (use its IP from Settings or MaixVision), such as `http://192.168.1.50`, then click
**Connect sensor**. Enter the base URL, without `/api/frame`. The last address is
remembered locally; connecting is explicit. Disconnect before editing the URL.

The computer and MaixCAM must be reachable on the same LAN. Run the frontend over
HTTP when connecting directly to the HTTP board. For HTTPS hosting, put the
board behind an HTTPS reverse proxy. In `MaixPy/config.py`, `CORS_ORIGIN`
must be `*` or the exact frontend origin. If your browser requests local-network
access, allow it for this app.

## Reading the display

- Red is near, blue is far, gray means no valid target (or no current frame).
  The default color scale is 0–4,000 mm. Changing it only changes colors;
  readings beyond the selected scale remain visible and use the far color.
- Status 5 and status 9 with a detected target are accepted. Status 9 cells
  have a dot to mark lower confidence; the checkbox can hide these readings.
- Select any cell to inspect native zone number, row, column, raw status, and
  detected target count. Indices start at zero. Statistics use visible valid zones.
- The device applies its configured clockwise rotation first, then horizontal
  and vertical flips in display coordinates. Check mounting
  and optical orientation with an object in a known corner.
- Frame age is the device-reported age **at response**, not a UTC timestamp.
  Sequence numbers can repeat between polls and reset when the board restarts.

Requests to `GET /api/frame` run sequentially, 100 ms after each successful
response. Failures clear the grid and retry after one second. Each request has a
four-second timeout. Readings also expire after two seconds based on reported
age or a frozen sequence, including while a later request is still pending.
Disconnecting or unmounting aborts the request and clears timers. The app
validates the documented response shape before displaying it.

Sensor resolution and ranging frequency are configured on the board, not by the
frontend. Refer to `../MaixPy/README.md` and
`../MaixPy/examples/DistanceGrid.jsx` for the source REST and display contract.

## Build and test

```sh
npm test
npm run build
npm run preview
```

Deploy the generated `dist/` directory to a static web server. The frontend calls
the supplied device URL directly; it needs no application backend. Tests cover
frame validation, filtering, orientation, sequential polling, error recovery,
stale data expiry, and cancellation. Physical sensor validation requires the board.

## Paired camera comparison

`/api/camera` supplies an atomic JPEG/base64 and detection snapshot. The viewer
polls it independently of `/api/frame`, with timeout, cancellation, stale/frozen
sequence detection and retry behavior for each stream. Camera failure clears its
image and detections while ToF continues. Green numbered boxes are encoded in the
JPEG; object details use full-image pixels. Candidates are circles, not confirmed
marble classifications. All detections are listed, including outside the displayed
comparison crop. No frames are recorded by the viewer.

Both viewports are equal squares, including on narrow screens. The stock camera
image is projected into the nominal 60° × 60° ToF viewport, cropping its wider
horizontal coverage and leaving empty vertical bands. Set **Comparison distance**
to the target's approximate axial depth to correct the nominal 60 mm horizontal
baseline. Front-view right corresponds to image-left; the second module is absent.
Adjust ToF rotation/mirroring to match physical orientation. Geometry comes from
the camera API and can be tuned in the MaixPy configuration.

This is an approximate pinhole comparison using stock lens specifications, not
calibrated registration or synchronized capture. Objects at another depth have
residual parallax; ToF zones are much coarser than camera pixels. See the MaixPy
README for assumptions, geometry, and the full camera REST contract.

## Viewing modes

Use **Viewing mode** before connecting or while connected:

- **Video + distance**: both streams, with the existing equal-sized comparison panels.
- **Video only**: full, uncropped camera image and object details; no ToF polling.
- **Distance only**: distance map and controls; no camera polling or image transfers.

Changing mode aborts the hidden stream's request and clears its polling/expiry
timers. Connection status reflects only selected streams. Selecting a stream again
starts fresh polling. These are viewer modes: acquisition and circle detection
continue on the device, and the 10 Hz camera publication limit is unchanged.

**Video acquisition** and **Video object detection** are separate device controls.
They load on connection and require the updated MaixPy service. Disabling video
also disables detection; re-enabling video starts in raw-image mode. Enable object
detection explicitly to restore boxes. Requests are confirmed by the device before
the selectors update. Controls are unavailable while disconnected or applying a
change; errors are shown without claiming success. These device-wide settings
apply to every viewer, unlike the local Viewing mode selector. Reconnect to reload
settings changed by another client. Neither control changes the publication FPS cap.


ToF **Clockwise rotation**, **Mirror horizontally**, and **Mirror vertically**
now control device settings through `/api/tof/settings`. Both flips can be active.
Deploy the updated MaixPy service to use these controls. They are disabled until
the device settings are loaded and while a change is being applied. The API
returns already-oriented matrices, so React does not rotate them again. Native
zone IDs remain available in the inspector. Changes last until device restart;
edit `TOF_ROTATION`, `TOF_FLIP_H`, and `TOF_FLIP_V` in MaixPy/config.py for startup
defaults. Camera orientation is unaffected.
