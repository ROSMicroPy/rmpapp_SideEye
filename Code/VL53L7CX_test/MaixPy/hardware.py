"""MaixCAM pin mapping and I2C bus creation."""
import time
import config


def open_i2c(frequency=None):
    from maix import err
    from maix.peripheral import i2c, pinmap

    for pin, function in ((config.I2C_SCL, "SCL"), (config.I2C_SDA, "SDA")):
        err.check_raise(pinmap.set_pin_function(pin, "I2C%d_%s" % (config.I2C_ID, function)),
                        "Cannot map %s to I2C%d_%s" % (pin, config.I2C_ID, function))
    return i2c.I2C(config.I2C_ID, i2c.Mode.MASTER,
                   freq=config.I2C_FREQUENCY if frequency is None else frequency)


def enable_sensor():
    """Keep the returned GPIO alive for the lifetime of sensor access."""
    from maix import err
    from maix.peripheral import gpio, pinmap

    name = "GPIO" + config.SENSOR_ENABLE_PIN
    err.check_raise(pinmap.set_pin_function(config.SENSOR_ENABLE_PIN, name),
                    "Cannot map sensor enable pin")
    enable = gpio.GPIO(name, gpio.Mode.OUT)
    enable.value(1)
    time.sleep(0.010)
    return enable
