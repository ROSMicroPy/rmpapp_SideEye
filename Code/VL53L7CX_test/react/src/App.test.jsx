import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import App from './App.jsx';
import { cameraFrame } from './testFixtures.js';

afterEach(() => { cleanup(); localStorage.clear(); vi.useRealTimers(); vi.unstubAllGlobals(); });

it('connects to the entered board, renders a 4×4 frame, inspects a zone, and disconnects', async () => {
  const data = { sensor: 'VL53L7CX', rows: 4, cols: 4, sequence: 42, timestamp_ms: 123,
    age_ms: 10, units: 'mm', distance_mm: Array.from({ length: 4 }, () => [100, 200, null, 400]),
    target_status: Array.from({ length: 4 }, () => [5, 9, 0, 5]),
    targets_detected: Array.from({ length: 4 }, () => [1, 1, 0, 1]) };
  const fetch = vi.fn(async url => ({ ok: true, json: async () => url.endsWith('/api/camera') ? cameraFrame() : data }));
  vi.stubGlobal('fetch', fetch);
  render(<App />);
  expect(screen.getByRole('status').textContent).toBe('Disconnected');
  fireEvent.change(screen.getByLabelText(/DEVICE ADDRESS/), { target: { value: 'http://192.168.1.50' } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Connect sensor/ })); });
  expect(fetch.mock.calls.map(call => call[0])).toContain('http://192.168.1.50/api/frame');
  expect(screen.getByAltText(/Live camera/)).toBeTruthy();
  expect(screen.getByText('#1 marble candidate')).toBeTruthy();
  expect(screen.getByRole('status').textContent).toBe('Live');
  expect(screen.getAllByRole('button', { name: /^Zone / })).toHaveLength(16);
  const cell = screen.getByRole('button', { name: 'Zone 1, 200 millimeters' });
  fireEvent.click(cell);
  expect(cell.getAttribute('aria-pressed')).toBe('true');
  fireEvent.click(screen.getByLabelText(/Only high confidence/));
  expect(screen.getByRole('button', { name: 'Zone 1, no valid target' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Disconnect' }));
  expect(screen.getByRole('status').textContent).toBe('Disconnected');
  expect(screen.queryByRole('button', { name: /100 millimeters/ })).toBeNull();
  expect(screen.queryByAltText(/Live camera/)).toBeNull();
  expect(screen.queryByText('#1 marble candidate')).toBeNull();
});

it('switches modes while connected and cancels polling for hidden streams', async () => {
  vi.useFakeTimers();
  const fetch = vi.fn(url => url.endsWith('/settings') ? Promise.resolve({ok: true, json: async () => ({acquisition_enabled: true, detection_enabled: true})}) : new Promise(() => {}));
  const streams = () => fetch.mock.calls.filter(c => !c[0].endsWith('/settings'));
  vi.stubGlobal('fetch', fetch);
  render(<App />);
  fireEvent.change(screen.getByLabelText('Viewing mode'), { target: { value: 'video' } });
  fireEvent.change(screen.getByLabelText(/DEVICE ADDRESS/), { target: { value: 'http://device' } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Connect sensor/ })); });
  expect(streams().map(c => c[0])).toEqual(['http://device/api/camera']);
  expect(screen.queryByLabelText('Sensor distance map')).toBeNull();
  expect(screen.queryByLabelText(/Comparison distance/)).toBeNull();
  expect(document.querySelector('.full-camera')).not.toBeNull();
  const cameraSignal = streams()[0][1].signal;

  fireEvent.change(screen.getByLabelText('Viewing mode'), { target: { value: 'distance' } });
  expect(cameraSignal.aborted).toBe(true);
  expect(streams().map(c => c[0])).toEqual(['http://device/api/camera', 'http://device/api/frame']);
  expect(screen.queryByLabelText('Camera comparison view')).toBeNull();
  expect(screen.getByLabelText('Sensor distance map')).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(500); });
  expect(streams()).toHaveLength(2);

  fireEvent.change(screen.getByLabelText('Viewing mode'), { target: { value: 'both' } });
  expect(streams()[2][0]).toBe('http://device/api/camera');
  expect(screen.getByLabelText('Camera comparison view')).toBeTruthy();
  expect(screen.getByLabelText(/Comparison distance/)).toBeTruthy();
  expect(document.querySelector('.single-stream')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Disconnect' }));
  expect(streams().every(c => c[1].signal.aborted)).toBe(true);
});

it('uses camera readiness for video-only status without requesting ToF', async () => {
  const fetch = vi.fn(async () => ({ ok: true, json: async () => cameraFrame() }));
  vi.stubGlobal('fetch', fetch);
  render(<App />);
  fireEvent.change(screen.getByLabelText('Viewing mode'), { target: { value: 'video' } });
  fireEvent.change(screen.getByLabelText(/DEVICE ADDRESS/), { target: { value: 'http://device' } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Connect sensor/ })); });
  expect(screen.getByRole('status').textContent).toBe('Live');
  expect(screen.getByAltText(/Live camera/)).toBeTruthy();
  expect(fetch.mock.calls.some(c => c[0].endsWith('/api/frame'))).toBe(false);
});

it('controls device acquisition and detection and renders raw images', async () => {
  let settings = { acquisition_enabled: true, detection_enabled: true };
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/settings')) {
      if (options.method === 'POST') {
        settings = { ...settings, ...JSON.parse(options.body) };
        if (!settings.acquisition_enabled) settings.detection_enabled = false;
      }
      return { ok: true, json: async () => ({ ...settings }) };
    }
    return { ok: true, json: async () => cameraFrame({ detection_enabled: settings.detection_enabled,
      objects: settings.detection_enabled ? cameraFrame().objects : [] }) };
  });
  vi.stubGlobal('fetch', fetch);
  render(<App />);
  expect(screen.getByLabelText('Video acquisition').disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Viewing mode'), { target: { value: 'video' } });
  fireEvent.change(screen.getByLabelText(/DEVICE ADDRESS/), { target: { value: 'http://device' } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Connect sensor/ })); });
  await act(async () => { fireEvent.change(screen.getByLabelText('Video object detection'), { target: { value: 'false' } }); });
  expect(screen.getByAltText('Live camera raw image')).toBeTruthy();
  expect(screen.getByText('Object detection disabled — raw image.')).toBeTruthy();
  await act(async () => { fireEvent.change(screen.getByLabelText('Video acquisition'), { target: { value: 'false' } }); });
  expect(screen.getByLabelText('Video object detection').disabled).toBe(true);
  expect(screen.getByLabelText('Video object detection').value).toBe('false');
  expect(screen.queryByAltText(/Live camera/)).toBeNull();
  expect(screen.getByRole('status').textContent).toBe('Video disabled');
  await act(async () => { fireEvent.change(screen.getByLabelText('Video acquisition'), { target: { value: 'true' } }); });
  expect(screen.getByLabelText('Video object detection').disabled).toBe(false);
  expect(screen.getByAltText('Live camera raw image')).toBeTruthy();
  await act(async () => { fireEvent.change(screen.getByLabelText('Video object detection'), { target: { value: 'true' } }); });
  expect(screen.getByText('#1 marble candidate')).toBeTruthy();
});

it('loads device ToF orientation and updates rotation and both flips', async () => {
  let settings = { rotation: 90, flip_h: true, flip_v: false };
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/api/tof/settings')) {
      if (options.method === 'POST') settings = { ...settings, ...JSON.parse(options.body) };
      return { ok: true, json: async () => ({ ...settings }) };
    }
    return { ok: false, json: async () => ({ error: 'Sensor initializing' }) };
  });
  vi.stubGlobal('fetch', fetch);
  render(<App />);
  expect(screen.getByLabelText('Clockwise rotation').disabled).toBe(true);
  fireEvent.change(screen.getByLabelText(/DEVICE ADDRESS/), { target: { value: 'http://device' } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Connect sensor/ })); });
  expect(screen.getByLabelText('Clockwise rotation').value).toBe('90');
  expect(screen.getByLabelText('Mirror horizontally').checked).toBe(true);
  await act(async () => { fireEvent.change(screen.getByLabelText('Clockwise rotation'), { target: { value: '270' } }); });
  await act(async () => { fireEvent.click(screen.getByLabelText('Mirror vertically')); });
  await act(async () => { fireEvent.click(screen.getByLabelText('Mirror horizontally')); });
  expect(settings).toEqual({ rotation: 270, flip_h: false, flip_v: true });
  fireEvent.click(screen.getByRole('button', { name: 'Disconnect' }));
  expect(screen.getByLabelText('Mirror vertically').disabled).toBe(true);
});
