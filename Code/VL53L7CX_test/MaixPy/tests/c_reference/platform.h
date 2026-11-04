#ifndef VL53_PLATFORM_H
#define VL53_PLATFORM_H
#include <stdint.h>
#include <string.h>
typedef struct { uint16_t address; } VL53L7CX_Platform;
#define VL53L7CX_NB_TARGET_PER_ZONE 1U
#define VL53L7CX_DISABLE_AMBIENT_PER_SPAD
#define VL53L7CX_DISABLE_NB_SPADS_ENABLED
#define VL53L7CX_DISABLE_SIGNAL_PER_SPAD
#define VL53L7CX_DISABLE_RANGE_SIGMA_MM
#define VL53L7CX_DISABLE_REFLECTANCE_PERCENT
#define VL53L7CX_DISABLE_MOTION_INDICATOR
#define SWAP_UINT16(x) (x)
#define SWAP_UINT32(x) (x)
uint8_t VL53L7CX_RdByte(VL53L7CX_Platform *, uint16_t, uint8_t *);
uint8_t VL53L7CX_WrByte(VL53L7CX_Platform *, uint16_t, uint8_t);
uint8_t VL53L7CX_RdMulti(VL53L7CX_Platform *, uint16_t, uint8_t *, uint32_t);
uint8_t VL53L7CX_WrMulti(VL53L7CX_Platform *, uint16_t, uint8_t *, uint32_t);
void VL53L7CX_SwapBuffer(uint8_t *, uint16_t);
uint8_t VL53L7CX_WaitMs(VL53L7CX_Platform *, uint32_t);
#endif
