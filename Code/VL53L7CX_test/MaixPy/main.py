"""MaixCAM VL53L7CX sensor and asyncio REST application."""
import asyncio
from hardware import open_i2c, enable_sensor
import config
from api import HTTPServer, State, ticks_ms, ticks_diff


def validate_config():
    if config.CAMERA_PUBLISH_HZ <= 0 or not 51 <= config.CAMERA_JPEG_QUALITY <= 100:
        raise ValueError("Invalid camera publish rate or JPEG quality")
    if config.RESOLUTION not in (16, 64):
        raise ValueError("RESOLUTION must be 16 or 64")
    if not 1 <= config.RANGING_HZ <= (15 if config.RESOLUTION == 64 else 60):
        raise ValueError("Invalid RANGING_HZ for resolution")
    if "\r" in config.CORS_ORIGIN or "\n" in config.CORS_ORIGIN:
        raise ValueError("Invalid CORS_ORIGIN")
    if config.STALE_AFTER_MS < 1000 // config.RANGING_HZ:
        raise ValueError("STALE_AFTER_MS is shorter than a frame period")


async def sample(state):
    sensor = None
    bus = None
    enable = None
    try:
        from vl53l7cx import VL53L7CX, CorruptFrameError, DRIVER_VERSION
    except ImportError:
        state.error = "vl53l7cx.py missing; upload driver and sensor data per README"
        print(state.error)
        return
    print('VL53L7CX driver:', DRIVER_VERSION, 'I2C requested Hz:', config.I2C_FREQUENCY)
    while True:
        try:
            enable = enable_sensor()
            bus = open_i2c()
            state.error = "Sensor initializing"
            print("Initializing VL53L7CX (firmware upload may take several seconds)")
            # Initialization is synchronous; HTTP pauses during this step.
            sensor = VL53L7CX(bus, config.SENSOR_ADDRESS)
            sensor.start(config.RESOLUTION, config.RANGING_HZ)
            print('Sensor initialized; zones:', config.RESOLUTION, 'Hz:', config.RANGING_HZ,
                  'ready poll ms: 5')
            last = ticks_ms()
            corrupt_count = 0
            while True:
                try:
                    result = sensor.read()
                except CorruptFrameError as exc:
                    # Wait for a subsequent acquisition before reinitializing.
                    # Never publish the rejected frame or label cached data live.
                    state.error = str(exc)
                    corrupt_count += 1
                    if corrupt_count == 1:
                        print('Discarded frame:', exc)
                    result = None
                if result is not None:
                    state.publish(result)
                    last = ticks_ms()
                    if corrupt_count:
                        print('Sensor recovered; discarded reads:', corrupt_count)
                        corrupt_count = 0
                elif ticks_diff(ticks_ms(), last) > config.STALE_AFTER_MS:
                    raise OSError('Sensor stopped delivering valid frames; discarded reads=%d; last error=%s' %
                                  (corrupt_count, state.error))
                # Match the successful standalone diagnostic. Readiness polling
                # is independent of acquisition frequency: a slower check can
                # leave an available frame waiting longer under HTTP load.
                # Yield to the REST server between checks; never busy-wait.
                await asyncio.sleep(0.005)
        except Exception as exc:
            state.error = str(exc)
            print("Sensor:", exc)
        finally:
            if sensor is not None:
                try:
                    sensor.stop()
                except Exception:
                    pass
                sensor = None
            bus = None
            if enable is not None:
                enable.value(0)
                enable = None
        await asyncio.sleep(config.SENSOR_RETRY_MS / 1000)


async def main():
    validate_config()
    from maix import app
    from marble_detect.service import CameraService
    camera = CameraService(config)
    state = State(config, camera)
    http = HTTPServer(state)
    server = await asyncio.start_server(http.handle, config.HTTP_HOST, config.HTTP_PORT, backlog=4)
    print("REST API listening on %s:%d; viewer URL: http://<device-ip>:%d" %
          (config.HTTP_HOST, config.HTTP_PORT, config.HTTP_PORT))
    camera.start()
    tasks = [asyncio.create_task(sample(state))]
    try:
        while not app.need_exit():
            await asyncio.sleep(0.1)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        server.close()
        await server.wait_closed()
        camera.stop()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
