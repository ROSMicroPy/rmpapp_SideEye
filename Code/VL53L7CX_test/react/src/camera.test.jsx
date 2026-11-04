import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, renderHook, screen } from '@testing-library/react';
import { cameraPlacement, validateCamera } from './camera.js';
import { cameraFrame } from './testFixtures.js';
import CameraPanel from './CameraPanel.jsx';
import { useFrames } from './useSensor.js';

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

it('checks image, bounding boxes, geometry and freshness', () => {
  expect(validateCamera(cameraFrame()).objects).toHaveLength(1);
  for (const override of [{ image_base64: '' }, { image_mime: 'text/html' }, { age_ms: 2000 },
    { geometry: {} }, { objects: [{ id: 0, bbox: { x: 319, y: 0, width: 20, height: 20 } }] }]) {
    expect(() => validateCamera(cameraFrame(override))).toThrow();
  }
});

it('matches nominal angular scale and corrects the front-right baseline at a chosen plane', () => {
  const geometry = cameraFrame().geometry;
  const far = cameraPlacement(geometry, 2000), near = cameraPlacement(geometry, 500);
  expect(parseFloat(far.width)).toBeGreaterThan(100);
  expect(parseFloat(far.height)).toBeLessThan(100);
  expect(near.width).toBe(far.width);
  expect(parseFloat(near.left)).toBeGreaterThan(parseFloat(far.left));
  const equal = cameraPlacement({ ...geometry, camera_hfov_deg: 60, camera_vfov_deg: 60, sensor_offset_x_mm: 0 }, 1000);
  expect(equal).toEqual({ width: '100%', height: '100%', left: '0%', top: '0%' });
});

it('removes image and objects on error, then recovers with an empty scene', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({ ok: true, json: async () => cameraFrame() })
    .mockResolvedValueOnce({ ok: false, json: async () => ({ error: 'Camera disconnected' }) })
    .mockResolvedValue({ ok: true, json: async () => cameraFrame({ sequence: 2, objects: [] }) }));
  function CameraTest() {
    const stream = useFrames('http://device', '/api/camera', validateCamera, 'Camera');
    return <CameraPanel baseUrl="http://device" distanceMm={1000} stream={stream} />;
  }
  render(<CameraTest />);
  await act(async () => {});
  expect(screen.getByAltText(/Live camera/)).toBeTruthy();
  expect(screen.getByText('#1 marble candidate')).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(100); });
  expect(screen.queryByAltText(/Live camera/)).toBeNull();
  expect(screen.queryByText('#1 marble candidate')).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(screen.getByText('No marble candidates detected.')).toBeTruthy();
});

it('expires a frozen camera frame and cancels requests on disconnect', async () => {
  vi.useFakeTimers();
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => cameraFrame() });
  vi.stubGlobal('fetch', fetch);
  const { result, unmount } = renderHook(() => useFrames('http://device', '/api/camera', validateCamera, 'Camera'));
  await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
  expect(result.current.frame).toBeNull();
  expect(result.current.error).toBe('Camera data stale');
  unmount();
  expect(fetch.mock.calls.at(-1)[1].signal.aborted).toBe(true);
});
