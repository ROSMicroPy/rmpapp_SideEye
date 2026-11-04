export function cameraFrame(overrides = {}) {
  return { sequence: 1, timestamp_ms: 100, age_ms: 0, width: 320, height: 180,
    image_mime: 'image/jpeg', image_base64: '/9j/2Q==',
    geometry: { camera_hfov_deg: 81, camera_vfov_deg: 51, tof_hfov_deg: 60, tof_vfov_deg: 60, sensor_offset_x_mm: -60 },
    objects: [{ id: 0, label: 'marble candidate', bbox: { x: 50, y: 40, width: 20, height: 20 }, radius_px: 7, magnitude: 2500 }],
    ...overrides };
}
