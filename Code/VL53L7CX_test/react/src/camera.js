import { STALE_MS } from './sensor.js';

export function validateCamera(frame) {
  const integer = v => Number.isInteger(v) && v >= 0;
  const angle = v => Number.isFinite(v) && v > 0 && v < 180;
  const g = frame?.geometry;
  if (!frame || !integer(frame.sequence) || !integer(frame.timestamp_ms) ||
      !integer(frame.age_ms) || !integer(frame.width) || !frame.width ||
      !integer(frame.height) || !frame.height || frame.image_mime !== 'image/jpeg' ||
      typeof frame.image_base64 !== 'string' || !frame.image_base64.length ||
      !/^[A-Za-z0-9+/]+={0,2}$/.test(frame.image_base64) ||
      !g || ![g.camera_hfov_deg, g.camera_vfov_deg, g.tof_hfov_deg, g.tof_vfov_deg].every(angle) ||
      !Number.isFinite(g.sensor_offset_x_mm) || !Array.isArray(frame.objects) ||
      !frame.objects.every(o => o && integer(o.id) && typeof o.label === 'string' &&
        o.bbox && [o.bbox.x, o.bbox.y, o.bbox.width, o.bbox.height].every(integer) &&
        o.bbox.width > 0 && o.bbox.height > 0 && o.bbox.x + o.bbox.width <= frame.width &&
        o.bbox.y + o.bbox.height <= frame.height && Number.isFinite(o.radius_px) && o.radius_px > 0 &&
        Number.isFinite(o.magnitude))) throw new Error('Unexpected camera response');
  if (frame.age_ms >= STALE_MS) throw new Error('Camera data stale');
  return frame;
}

// Pinhole projection onto a plane parallel to the lenses. The square viewport
// spans the ToF FOV. Unobserved camera margins remain empty; never stretch to fit.
export function cameraPlacement(geometry, distanceMm) {
  const tan = degrees => Math.tan(degrees * Math.PI / 360);
  const width = tan(geometry.camera_hfov_deg) / tan(geometry.tof_hfov_deg);
  const height = tan(geometry.camera_vfov_deg) / tan(geometry.tof_vfov_deg);
  const shift = -geometry.sensor_offset_x_mm / (2 * distanceMm * tan(geometry.tof_hfov_deg));
  return { width: `${width * 100}%`, height: `${height * 100}%`,
    left: `${(0.5 - width / 2 + shift) * 100}%`, top: `${(0.5 - height / 2) * 100}%` };
}
