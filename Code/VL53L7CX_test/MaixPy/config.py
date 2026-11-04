"""MaixCAM defaults. Networking is configured in the device Settings app."""
I2C_ID = 5
I2C_SCL = "A15"
I2C_SDA = "A27"
I2C_FREQUENCY = 400_000  # Requested rate; I2C5 timing is controlled by the OS driver.
SENSOR_ENABLE_PIN = "A24"  # Active-high enable / LPn
SENSOR_ADDRESS = 0x29  # 7-bit address
RESOLUTION = 64  # 64 = 8x8, 16 = 4x4
RANGING_HZ = 10  # 1-15 for 8x8; 1-60 for 4x4
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 80
CORS_ORIGIN = "*"
STALE_AFTER_MS = 2000
SENSOR_RETRY_MS = 5000

# Camera detection is independent of the distance sensor.
CAMERA_ENABLED = True
CAMERA_PUBLISH_HZ = 10
CAMERA_JPEG_QUALITY = 80
CAMERA_STALE_AFTER_MS = 2000
CAMERA_RETRY_SECONDS = 5
# Physical mounting, viewed from in front of the camera looking at its lens.
SENSOR_POSITION = "right"
# Nominal GC4653 stock lens; 16:9 capture preserves the native aspect ratio.
CAMERA_HFOV_DEG = 81.0
CAMERA_VFOV_DEG = 51.0
TOF_HFOV_DEG = 60.0
TOF_VFOV_DEG = 60.0
# Camera coordinates: +x is image-right. Front-view right is image-left.
SENSOR_OFFSET_X_MM = -60.0

# Applied clockwise first, then flips along the displayed horizontal/vertical axes.
TOF_ROTATION = 0  # 0, 90, 180, 270 degrees
TOF_FLIP_H = False
TOF_FLIP_V = False
