import { useEffect, useState } from 'react';
import { STALE_MS, validateFrame } from './sensor.js';

export default function useSensor(baseUrl) {
  return useFrames(baseUrl, '/api/frame', validateFrame, 'Sensor');
}

export function useFrames(baseUrl, endpoint, validate, source) {
  const [state, setState] = useState({ frame: null, error: '', connected: false });
  useEffect(() => {
    let stopped = false;
    let pollTimer;
    let expiryTimer;
    let controller;
    let lastSequence;
    let lastNewFrame = 0;
    setState({ frame: null, error: '', connected: false });
    if (!baseUrl) return;

    async function poll() {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 4000);
      let delay = 100;
      try {
        const response = await fetch(`${baseUrl}${endpoint}`, { signal: controller.signal, cache: 'no-store' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        const frame = validate(data);
        const now = performance.now();
        if (frame.sequence !== lastSequence) {
          lastSequence = frame.sequence;
          lastNewFrame = now;
        }
        const remaining = Math.min(STALE_MS - frame.age_ms, STALE_MS - (now - lastNewFrame));
        if (remaining <= 0) throw new Error(`${source} data stale`);
        if (!stopped) {
          clearTimeout(expiryTimer);
          setState({ frame, error: '', connected: true });
          expiryTimer = setTimeout(() => {
            if (!stopped) setState({ frame: null, error: `${source} data stale`, connected: false });
          }, remaining);
        }
      } catch (error) {
        delay = 1000;
        if (!stopped) {
          clearTimeout(expiryTimer);
          setState({ frame: null, connected: false,
            error: error.name === 'AbortError' ? `${source} request timed out` : error.message });
        }
      } finally {
        clearTimeout(timeout);
        if (!stopped) pollTimer = setTimeout(poll, delay);
      }
    }
    poll();
    return () => {
      stopped = true;
      clearTimeout(pollTimer);
      clearTimeout(expiryTimer);
      controller?.abort();
    };
  }, [baseUrl, endpoint, validate, source]);
  return state;
}
