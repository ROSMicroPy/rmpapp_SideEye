export const STALE_MS = 2000;

export function normalizeUrl(value) {
  const url = new URL(value.trim());
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('Enter an HTTP or HTTPS device URL without credentials, a query, or a fragment.');
  }
  return url.href.replace(/\/+$/, '');
}

export function validateFrame(frame) {
  const side = frame?.rows;
  const grid = (values, valid) => Array.isArray(values) && values.length === side &&
    values.every(row => Array.isArray(row) && row.length === side && row.every(valid));
  const nonnegative = value => Number.isInteger(value) && value >= 0;
  if (frame?.sensor !== 'VL53L7CX' || ![4, 8].includes(side) || frame.cols !== side ||
      frame.units !== 'mm' || !nonnegative(frame.sequence) || !nonnegative(frame.timestamp_ms) ||
      !nonnegative(frame.age_ms) || !grid(frame.distance_mm, v => v === null || nonnegative(v)) ||
      !grid(frame.target_status, nonnegative) || !grid(frame.targets_detected, nonnegative)) {
    throw new Error('Unexpected sensor response. Check the device URL and firmware.');
  }
  if (frame.zone_ids !== undefined && (!grid(frame.zone_ids, v => nonnegative(v) && v < side * side) ||
      new Set(frame.zone_ids.flat()).size !== side * side)) throw new Error('Invalid native zone mapping');
  if (frame.age_ms >= STALE_MS) throw new Error('Sensor data stale');
  return frame;
}

export function getZones(frame, rotation = 0, flip = false, strict = false) {
  const side = frame?.rows || 8;
  return Array.from({ length: side * side }, (_, index) => {
    let row = Math.floor(index / side);
    let col = flip ? side - 1 - index % side : index % side;
    for (let turn = 0; turn < rotation / 90; turn++) [row, col] = [side - 1 - col, row];
    const status = frame?.target_status[row][col];
    const targets = frame?.targets_detected[row][col];
    const raw = frame?.distance_mm[row][col] ?? null;
    const id = frame?.zone_ids?.[row]?.[col] ?? row * side + col;
    return { id, row: Math.floor(id / side), col: id % side, status, targets,
      mm: targets > 0 && (status === 5 || (!strict && status === 9)) ? raw : null };
  });
}

export function distanceColor(mm, maximum) {
  return mm === null ? '#303a40' : `hsl(${Math.min(1, Math.max(0, mm / maximum)) * 240} 75% 32%)`;
}
