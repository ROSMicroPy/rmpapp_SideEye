# MarbleDetect

Live MaixCAM application for MaixPy v4. Run `main.py` to display the camera
image with green bounding boxes around circular marble candidates, a current
candidate count, and measured processing/display FPS. No model files or extra
Python packages are needed. The requested `MaixPy/MarbleDetect` directory is
separate from the repository's existing `MaxiPy` directory.

## Run on the camera

1. Connect MaixCAM to MaixVision and open `main.py`.
2. Run the script on the device. Use MaixVision's stop control to stop it.
3. To keep it on the camera, use MaixVision's application installation feature
   with `main.py` as the entry script. Alternatively copy it to the device and
   run `python3 /path/to/main.py` in a device terminal.

This is the Linux-based MaixPy v4 API, not legacy K210 MaixPy firmware.

## Scene and tuning

Use bright, diffuse lighting, a plain contrasting background, and focus the
camera at the marble's working distance. Begin with one stationary marble.
Settings are at the top of `main.py`:

| Setting | Purpose |
| --- | --- |
| `MIN_RADIUS`, `MAX_RADIUS` | Expected marble radius in camera pixels; defaults cover diameters of 10–90 pixels. Narrow this range to improve speed and reject unrelated circles. |
| `CIRCLE_THRESHOLD` | Start at 2000. Lower gradually if marbles are missed; raise if background circles are detected. |
| `EXPOSURE_US` | Default 1000 µs limits motion blur. Try 500 µs for faster swings with brighter lighting. Set to `None` for automatic exposure, which can blur motion. |
| `GAIN` | Optional manual gain when short exposure is too dark. More gain adds image noise; adding light is preferable. |
| `CAMERA_FPS` | Requests 60 FPS from the camera. The displayed FPS measures the actual loop, including detection and display; 60 FPS is not guaranteed. |
| `WIDTH`, `HEIGHT` | Higher resolution helps small marbles but increases processing time. Retune radius limits after changing resolution. |

The detector searches the whole image every frame, including when nothing is
moving. Multiple circles produce independent boxes; no background learning or
motion trigger is needed. Short exposure helps preserve the circular outline of
a swinging marble. Boxes use current detections with no smoothing delay or stale
predictions. A missed detection temporarily removes the box.

This is geometric detection, not a trained marble classifier. Other round objects
can be detected. Transparent marbles with faint outlines, strong reflections,
heavy motion blur, overlapping marbles, and marbles partly outside the image can
be missed. Duplicate suppression can merge heavily overlapping candidates.
Cluttered scenes may require a marble-specific trained model and sample images.
The application displays live video; it does not save photos or recordings.

## Device acceptance check

- Empty scene: verify zero candidates and adjust threshold/background if needed.
- Stationary: leave a marble in place for 30 seconds and check box stability.
- Swinging: swing a suspended marble through the view, including the fastest
  part of its arc. Adjust lighting/exposure until the outline stays sharp.
- Multiple: place several separated marbles in view, then swing one while the
  others remain still. Check the count and boxes for all visible marbles.
- Removal: remove every marble and check that all boxes disappear immediately.
- Record displayed FPS and missed detections for the actual scene.

Desktop checks cannot establish camera detection accuracy or on-device speed.

API references: [circle detection and drawing](https://en.wiki.sipeed.com/maixpy/api/maix/image.html),
[camera API](https://en.wiki.sipeed.com/maixpy/api/maix/camera.html),
[exposure configuration](https://en.wiki.sipeed.com/maixpy/doc/en/vision/camera.html).
