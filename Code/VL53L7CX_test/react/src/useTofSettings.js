import useDeviceSettings from './useDeviceSettings.js';

function validate(data) {
  if (![0, 90, 180, 270].includes(data?.rotation) || typeof data?.flip_h !== 'boolean' ||
      typeof data?.flip_v !== 'boolean') throw new Error('ToF controls require updated MaixPy firmware');
  return data;
}
export default function useTofSettings(baseUrl) {
  return useDeviceSettings(baseUrl, '/api/tof/settings', validate);
}
