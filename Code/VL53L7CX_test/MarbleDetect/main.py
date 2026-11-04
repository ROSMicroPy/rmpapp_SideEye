"""Live, model-free marble candidate detection for MaixCAM / MaixPy v4."""

import time


# Tune these values for the marble size, camera distance, and lighting.
WIDTH = 320
HEIGHT = 240
CAMERA_FPS = 60  # Requested capture rate; detection/display FPS will be lower.
EXPOSURE_US = 1000  # Short exposure freezes motion; None enables auto exposure.
GAIN = None  # Keep the camera's gain unless explicitly set (manual exposure).
MIN_RADIUS = 5  # Pixels in the captured image, not physical marble size.
MAX_RADIUS = 45
CIRCLE_THRESHOLD = 2000  # Lower finds weaker edges; higher rejects more noise.
RADIUS_STEP = 2
BOX_PADDING = 3


def detect_marbles(frame):
    """Find all visible circular candidates, independent of motion or color."""
    circles = frame.find_circles(
        x_stride=2, y_stride=2, threshold=CIRCLE_THRESHOLD,
        x_margin=4, y_margin=4, r_margin=4,
        r_min=MIN_RADIUS, r_max=MAX_RADIUS, r_step=RADIUS_STEP,
    )
    # Reflections and internal patterns can give several concentric circles.
    # Keep the strongest candidate at each center, retaining adjacent marbles.
    selected = []
    for circle in sorted(circles, key=lambda c: c.magnitude(), reverse=True):
        if any(
            (circle.x() - other.x()) ** 2 + (circle.y() - other.y()) ** 2
            < (0.6 * max(circle.r(), other.r())) ** 2
            for other in selected
        ):
            continue
        selected.append(circle)
    return selected


def bounding_box(circle, width, height):
    """Return a padded rectangle clipped to the captured image."""
    radius = circle.r() + BOX_PADDING
    left = max(0, circle.x() - radius)
    top = max(0, circle.y() - radius)
    right = min(width - 1, circle.x() + radius)
    bottom = min(height - 1, circle.y() + radius)
    return left, top, right - left + 1, bottom - top + 1


def main():
    # Import here so geometry and filtering can also be checked on a desktop.
    from maix import app, camera, display, image

    disp = display.Display()
    cam = camera.Camera(WIDTH, HEIGHT, image.Format.FMT_RGB888, fps=CAMERA_FPS)
    try:
        cam.skip_frames(15)
        if EXPOSURE_US is not None:
            cam.exposure(EXPOSURE_US)
            if GAIN is not None:
                cam.gain(GAIN)
        else:
            cam.exp_mode(camera.AeMode.Auto)
        cam.skip_frames(5)
        started = time.monotonic()
        frames = 0
        fps = 0.0
        while not app.need_exit():
            frame = cam.read()
            if frame is None:
                time.sleep(0.005)
                continue
            circles = detect_marbles(frame)
            for circle in circles:
                x, y, w, h = bounding_box(circle, frame.width(), frame.height())
                frame.draw_rect(x, y, w, h, image.COLOR_GREEN, thickness=2)
            frame.draw_string(
                4, 4, "Marbles: {}  FPS: {:.1f}".format(len(circles), fps),
                image.COLOR_GREEN,
            )
            disp.show(frame)
            frames += 1
            elapsed = time.monotonic() - started
            if elapsed >= 1.0:
                fps = frames / elapsed
                frames = 0
                started = time.monotonic()
    finally:
        cam.close()


if __name__ == "__main__":
    main()
