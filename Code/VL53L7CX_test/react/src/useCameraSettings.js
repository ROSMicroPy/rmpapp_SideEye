import useDeviceSettings from './useDeviceSettings.js';

function validate(data) {
  if (typeof data?.acquisition_enabled !== 'boolean' || typeof data?.detection_enabled !== 'boolean' ||
      (!data.acquisition_enabled && data.detection_enabled)) throw new Error('Camera controls require updated MaixPy firmware');
  return data;
}

export default function useCameraSettings(baseUrl) {
  return useDeviceSettings(baseUrl, '/api/camera/settings', validate);
}
