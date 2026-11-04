/* Host-only harness for comparing the Python port with ST's unmodified ULD. */
#include "vl53l7cx_api.h"
typedef int (*bus_hook)(int, uint16_t, uint8_t *, uint32_t);
static bus_hook hook;
static VL53L7CX_Configuration dev;
static VL53L7CX_ResultsData result;
void ref_reset(bus_hook callback) { memset(&dev, 0, sizeof(dev)); hook = callback; }
static uint8_t transfer(int read, uint16_t reg, uint8_t *data, uint32_t size) {
    while (size) {
        uint32_t n = size > 256 ? 256 : size;
        if (hook(read, reg, data, n)) { return 255; }
        reg += n; data += n; size -= n;
    }
    return 0;
}
uint8_t VL53L7CX_RdMulti(VL53L7CX_Platform *p, uint16_t r, uint8_t *b, uint32_t n) {
    (void)p; return transfer(1, r, b, n);
}
uint8_t VL53L7CX_WrMulti(VL53L7CX_Platform *p, uint16_t r, uint8_t *b, uint32_t n) {
    (void)p; return transfer(0, r, b, n);
}
uint8_t VL53L7CX_RdByte(VL53L7CX_Platform *p, uint16_t r, uint8_t *b) {
    return VL53L7CX_RdMulti(p, r, b, 1);
}
uint8_t VL53L7CX_WrByte(VL53L7CX_Platform *p, uint16_t r, uint8_t b) {
    return VL53L7CX_WrMulti(p, r, &b, 1);
}
void VL53L7CX_SwapBuffer(uint8_t *b, uint16_t n) {
    for (uint16_t i = 0; i < n; i += 4) {
        uint8_t a = b[i], c = b[i + 1];
        b[i] = b[i + 3]; b[i + 1] = b[i + 2]; b[i + 2] = c; b[i + 3] = a;
    }
}
uint8_t VL53L7CX_WaitMs(VL53L7CX_Platform *p, uint32_t ms) { (void)p; (void)ms; return 0; }
int ref_init(void) {
    uint8_t alive;
    int status = vl53l7cx_is_alive(&dev, &alive);
    return status || !alive ? 255 : vl53l7cx_init(&dev);
}
int ref_start(int zones, int hz) {
    int status = vl53l7cx_set_resolution(&dev, zones);
    status |= vl53l7cx_set_ranging_frequency_hz(&dev, hz);
    return status | vl53l7cx_start_ranging(&dev);
}
int ref_stop(void) { return vl53l7cx_stop_ranging(&dev); }
int ref_read(int16_t *distances, uint8_t *statuses, uint8_t *targets, int zones) {
    uint8_t ready;
    int status = vl53l7cx_check_data_ready(&dev, &ready);
    if (status) { return status; }
    if (!ready) { return -1; }
    status = vl53l7cx_get_ranging_data(&dev, &result);
    memcpy(distances, result.distance_mm, zones * sizeof(int16_t));
    memcpy(statuses, result.target_status, zones);
    memcpy(targets, result.nb_target_detected, zones);
    return status;
}
