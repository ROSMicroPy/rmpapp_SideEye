import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook } from '@testing-library/react';
import { getZones, normalizeUrl, validateFrame } from './sensor.js';
import useSensor from './useSensor.js';

function frame(overrides = {}) {
  return { sensor: 'VL53L7CX', rows: 8, cols: 8, units: 'mm', sequence: 1, timestamp_ms: 100, age_ms: 0,
    distance_mm: Array.from({ length: 8 }, (_, r) => Array.from({ length: 8 }, (_, c) => r * 8 + c)),
    target_status: Array.from({ length: 8 }, () => Array(8).fill(5)),
    targets_detected: Array.from({ length: 8 }, () => Array(8).fill(1)), ...overrides };
}
const ok = data => ({ ok: true, json: async () => data });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('frame contract and orientation', () => {
  it('accepts both documented resolutions and rejects malformed or stale frames', () => {
    expect(validateFrame(frame()).rows).toBe(8);
    expect(validateFrame(frame({ rows: 4, cols: 4,
      distance_mm: Array.from({ length: 4 }, () => Array(4).fill(null)),
      target_status: Array.from({ length: 4 }, () => Array(4).fill(0)),
      targets_detected: Array.from({ length: 4 }, () => Array(4).fill(0)),
    })).rows).toBe(4);
    for (const patch of [{ distance_mm: [] }, { rows: 7 }, { units: 'cm' }, { age_ms: 2001 }, { age_ms: -1 }]) {
      expect(() => validateFrame(frame(patch))).toThrow();
    }
  });
  it('preserves native zone identity when rotating and mirroring', () => {
    expect(getZones(frame())[0].id).toBe(0);
    expect(getZones(frame(), 90)[0].id).toBe(56);
    expect(getZones(frame(), 180)[0].id).toBe(63);
    expect(getZones(frame(), 270)[0].id).toBe(7);
    expect(getZones(frame(), 0, true)[0].id).toBe(7);
    expect(new Set(getZones(frame(), 90, true).map(z => z.id)).size).toBe(64);
  });
  it('filters invalid, missing, and optionally lower-confidence targets', () => {
    const data = frame();
    data.target_status[0] = [5, 9, 4, 5, 5, 5, 5, 5];
    data.targets_detected[0][3] = 0;
    data.distance_mm[0][4] = null;
    expect(getZones(data).slice(0, 5).map(z => z.mm)).toEqual([0, 1, null, null, null]);
    expect(getZones(data, 0, false, true)[1].mm).toBeNull();
  });
  it('normalizes device URLs and rejects unsupported schemes', () => {
    expect(normalizeUrl(' http://192.168.1.50/// ')).toBe('http://192.168.1.50');
    expect(() => normalizeUrl('file:///tmp')).toThrow();
    expect(() => normalizeUrl('http://device/?test=1')).toThrow();
  });
});

describe('polling lifecycle', () => {
  it('clears readings on a 503 and recovers automatically', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockResolvedValueOnce(ok(frame()))
      .mockResolvedValueOnce({ ok: false, json: async () => ({ error: 'Sensor initializing' }) })
      .mockResolvedValue(ok(frame({ sequence: 2 })));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(() => useSensor('http://device'));
    await act(async () => {});
    expect(result.current.frame.sequence).toBe(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    expect(result.current.frame).toBeNull();
    expect(result.current.error).toBe('Sensor initializing');
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(result.current.frame.sequence).toBe(2);
  });
  it('does not overlap requests and aborts on cleanup', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn(() => new Promise(() => {}));
    vi.stubGlobal('fetch', fetch);
    const { unmount } = renderHook(() => useSensor('http://device'));
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(fetch).toHaveBeenCalledTimes(1);
    const signal = fetch.mock.calls[0][1].signal;
    unmount();
    expect(signal.aborted).toBe(true);
  });
  it('expires the visible grid while a subsequent request hangs', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(ok(frame())).mockImplementation(() => new Promise(() => {})));
    const { result } = renderHook(() => useSensor('http://device'));
    await act(async () => {});
    expect(result.current.frame).not.toBeNull();
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(result.current.frame).toBeNull();
    expect(result.current.error).toBe('Sensor data stale');
  });
  it('rejects a frozen sequence even if the server reports zero age', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(frame())));
    const { result } = renderHook(() => useSensor('http://device'));
    await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
    expect(result.current.frame).toBeNull();
    expect(result.current.error).toBe('Sensor data stale');
  });
});

it('uses native zone IDs without reapplying device orientation', () => {
  const data = frame();
  data.zone_ids = Array.from({length: 8}, (_, r) => Array.from({length: 8}, (_, c) => 63-r*8-c));
  const zone = getZones(validateFrame(data))[0];
  expect(zone.id).toBe(63);
  expect([zone.row, zone.col, zone.mm]).toEqual([7, 7, 0]);
  data.zone_ids[0][0] = 0;
  expect(() => validateFrame(data)).toThrow('Invalid native zone mapping');
});
