from maix import i2c, pinmap, sys, err, gpio





scl_pin_name = "A15"
scl_i2c_name = "I2C5_SCL"
sda_pin_name = "A27"
sda_i2c_name = "I2C5_SDA"
i2c_id = 5

# set pinmap
err.check_raise(pinmap.set_pin_function(scl_pin_name, scl_i2c_name), "set pin failed")
err.check_raise(pinmap.set_pin_function(sda_pin_name, sda_i2c_name), "set pin failed")

err.check_raise(
    pinmap.set_pin_function("A24", "GPIOA24"),
    "Failed to configure A24"
)

enable = gpio.GPIO("GPIOA24", gpio.Mode.OUT)

# Disable VL53L7CX I2C
enable.value(0)

# Enable VL53L7CX I2C
enable.value(1)


bus = i2c.I2C(i2c_id, i2c.Mode.MASTER)
slaves = bus.scan()
print("find slaves:")
for s in slaves:
    print(f"{s}[0x{s:02x}]")