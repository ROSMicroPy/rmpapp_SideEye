# Marble detection module

Self-contained integration of the original `MarbleDetect/main.py` circle-based
example. Nothing imports or reads files from the original directory; it can be
removed later. Run the parent project's `main.py` to start camera and ToF together.

`detector.py` retains full-image circle search, strongest-first concentric-circle
suppression, clipped bounding boxes, and exposure/radius/threshold settings.
Capture is now 320×180 (16:9) to preserve the stock GC4653 sensor aspect for nominal
field-of-view comparison. Retune radius limits and exposure on the actual scene.
Default exposure is 1000 microseconds; set `EXPOSURE_US = None` for auto exposure.
No model or external Python package is required.

`service.py` owns the camera in one worker thread, warms up, detects, draws green
numbered boxes, encodes JPEG, and atomically publishes image plus object metadata.
The worker retries camera errors independently of ToF and closes the camera on
exit. REST handlers only read its cache. There is no display ownership conflict:
the React viewer displays the annotated image; the old standalone LCD loop is not
started. Images are held in memory, not recorded to disk.

Each object is a **marble candidate**, not a semantic classification. Other round
objects may trigger detections; transparent/blurred/overlapping marbles can be
missed. `magnitude` is circle edge strength, not confidence or probability. Object
IDs are local to a frame, not tracking IDs. Boxes and circles use full capture
pixel coordinates with origin at the top left, before browser comparison cropping.

Camera capture requests 60 FPS; publication is capped at 10 FPS by default, and
actual processing speed depends on hardware. The bounded cache always replaces
the previous frame. Backend and viewer reject stale snapshots after two seconds.

Device acceptance: check empty, stationary, moving, and multiple-marble scenes;
verify removal clears boxes; measure latency and tune exposure in working light.
For alignment, use a known-distance target and check ToF orientation before tuning
nominal lens FoV or baseline values in the parent `config.py`.
