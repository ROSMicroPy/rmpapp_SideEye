import { useState } from 'react';
import useTofSettings from './useTofSettings.js';
import useCameraSettings from './useCameraSettings.js';
import CameraPanel from './CameraPanel.jsx';
import useSensor, { useFrames } from './useSensor.js';
import { validateCamera } from './camera.js';
import { distanceColor, getZones, normalizeUrl } from './sensor.js';

function savedUrl() {
  try { return localStorage.getItem('sensor-url') || ''; } catch { return ''; }
}

export default function App() {
  const [address, setAddress] = useState(savedUrl);
  const [baseUrl, setBaseUrl] = useState('');
  const [mode, setMode] = useState('both');
  const showVideo = mode !== 'distance';
  const showDistance = mode !== 'video';
  const [formError, setFormError] = useState('');
  const tofControls = useTofSettings(baseUrl);
  const orientation = tofControls.settings || { rotation: 0, flip_h: false, flip_v: false };
  const tofControlsDisabled = !baseUrl || !tofControls.settings || tofControls.busy;
  const [strict, setStrict] = useState(false);
  const [maximum, setMaximum] = useState(4000);
  const [comparisonDistance, setComparisonDistance] = useState(1000);
  const [selected, setSelected] = useState(0);
  const { frame, error, connected } = useSensor(showDistance ? baseUrl : '');
  const cameraControls = useCameraSettings(baseUrl);
  const acquisitionDisabled = cameraControls.settings?.acquisition_enabled === false;
  const camera = useFrames(showVideo && !acquisitionDisabled && !(cameraControls.busy && cameraControls.settings) ? baseUrl : '', '/api/camera', validateCamera, 'Camera');
  const activeStreams = [showDistance && { error, connected }, showVideo && !acquisitionDisabled && camera].filter(Boolean);
  const activeError = activeStreams.map(stream => stream.error).filter(Boolean).join(" · ");
  const allConnected = activeStreams.length > 0 && activeStreams.every(stream => stream.connected);
  const zones = getZones(frame, 0, false, strict);
  const distances = zones.filter(zone => zone.mm !== null).map(zone => zone.mm);
  const zone = zones.find(zone => zone.id === selected);
  const status = !baseUrl ? 'Disconnected' : mode === 'video' && acquisitionDisabled ? 'Video disabled' : activeError ? 'Retrying connection' : allConnected ? 'Live' : 'Connecting';

  function connect(event) {
    event.preventDefault();
    try {
      const url = normalizeUrl(address);
      if (location.protocol === 'https:' && url.startsWith('http:')) {
        throw new Error('Open this app over HTTP, or use an HTTPS reverse proxy for the device.');
      }
      setFormError('');
      setBaseUrl(url);
      setAddress(url);
      try { localStorage.setItem('sensor-url', url); } catch { /* Storage is optional. */ }
    } catch (err) { setFormError(err.message || 'Enter a valid device URL.'); }
  }

  return <main>
    <header><a className="brand" href="./"><span className="brand-mark">▦</span> FIELD / <strong>DEPTH</strong></a><span className="hardware">MaixCAM <span>→</span> VL53L7CX</span></header>
    <section className="intro"><div><p className="eyebrow">TIME-OF-FLIGHT EXPLORER</p><h1>A window into distance.</h1><p className="muted">Marble candidates and multizone distance, side by side.</p></div><span className={`badge ${allConnected ? 'live' : ''}`} role="status"><i />{status}</span></section>
    <form className="connection panel" onSubmit={connect}>
      <label htmlFor="address">DEVICE ADDRESS<span>Find the IP in MaixCAM Settings or MaixVision.</span></label>
      <input id="address" type="url" required placeholder="http://192.168.1.50" value={address} onChange={e => setAddress(e.target.value)} disabled={!!baseUrl} />
      {baseUrl ? <button type="button" onClick={() => setBaseUrl('')}>Disconnect</button> : <button type="submit">Connect sensor <span aria-hidden="true">↗</span></button>}
    </form>
    <section className="panel mode-settings">
      <label htmlFor="view-mode">Viewing mode</label>
      <select id="view-mode" value={mode} onChange={e => setMode(e.target.value)}>
        <option value="both">Video + distance</option>
        <option value="video">Video only</option>
        <option value="distance">Distance only</option>
      </select>
      <span className="muted small">Only the selected streams are requested.</span>
    </section>
    <section className="panel mode-settings" aria-label="Device camera controls">
      <label htmlFor="video-acquisition">Video acquisition</label>
      <select id="video-acquisition" value={cameraControls.settings ? String(cameraControls.settings.acquisition_enabled) : ''}
        disabled={!baseUrl || cameraControls.busy || !cameraControls.settings}
        onChange={e => cameraControls.update({ acquisition_enabled: e.target.value === 'true' })}>
        <option value="" disabled>Read device settings</option><option value="true">Enable</option><option value="false">Disable</option>
      </select>
      <label htmlFor="video-detection">Video object detection</label>
      <select id="video-detection" value={cameraControls.settings ? String(cameraControls.settings.detection_enabled) : ''}
        disabled={!baseUrl || cameraControls.busy || !cameraControls.settings || acquisitionDisabled}
        onChange={e => cameraControls.update({ detection_enabled: e.target.value === 'true' })}>
        <option value="" disabled>Read device settings</option><option value="true">Enable</option><option value="false">Disable</option>
      </select>
      <span className="muted small">{cameraControls.busy ? 'Applying device settings…' : 'Controls acquisition on the device for all viewers.'}</span>
      {cameraControls.error && <span role="alert">{cameraControls.error}</span>}
    </section>
    {(formError || activeError) && <div className="error" role="alert"><strong>{formError || activeError}</strong>{activeError && <span>Check device power, the URL, Wi-Fi, and CORS settings. Retrying automatically.</span>}</div>}
    {mode === 'both' && <section className="comparison-settings panel">
      <div><strong>Right ToF module · 60 mm from lens</strong><p className="muted small">Right when looking at the lens; left module unpopulated. Nominal alignment assumes parallel optical axes. Adjust grid rotation/mirroring to match the scene.</p></div>
      <label htmlFor="comparison-distance">Comparison distance: {comparisonDistance} mm<input id="comparison-distance" type="range" min="100" max="3500" step="50" value={comparisonDistance} onChange={e => setComparisonDistance(Number(e.target.value))} /></label>
    </section>}
    <div className={`workspace ${mode !== 'both' ? 'single-stream' : ''}`}>
      {showVideo && <CameraPanel baseUrl={baseUrl} stream={acquisitionDisabled ? { frame: null, error: 'Video acquisition disabled' } : cameraControls.busy ? { frame: null, error: 'Applying camera settings…' } : camera} distanceMm={comparisonDistance} comparison={mode === 'both'} />}
      {showDistance && <section className="panel visualization">
        <div className="panel-heading"><div><p className="eyebrow">RIGHT MODULE / DISTANCE MAP</p><h2>{frame ? `${frame.rows} × ${frame.cols}` : '8 × 8'} zone view</h2></div><span className="unit">mm</span></div>
        <div className="grid-wrap">
          <div className="grid" style={{ gridTemplateColumns: `repeat(${frame?.cols || 8}, 1fr)` }} aria-label="Sensor distance map">
            {zones.map(z => <button key={z.id} type="button" className={`cell ${selected === z.id ? 'selected' : ''} ${z.status === 9 && z.mm !== null ? 'low-confidence' : ''}`} style={{ background: distanceColor(z.mm, maximum) }} onClick={() => setSelected(z.id)} aria-pressed={selected === z.id} aria-label={`Zone ${z.id}, ${z.mm === null ? 'no valid target' : `${z.mm} millimeters`}`} title={`Zone ${z.id} · row ${z.row}, column ${z.col} · status ${z.status ?? '—'}`}><span>{z.mm ?? '—'}</span></button>)}
          </div>
          {!frame && <div className="grid-message"><strong>{error ? 'Waiting for fresh data' : baseUrl ? 'Contacting sensor…' : 'Your scene starts here'}</strong><span>{baseUrl ? 'Measurements appear when the sensor is ready.' : 'Connect your board to see the distance map.'}</span></div>}
        </div>
        <div className="legend"><div className="gradient" /><div className="legend-labels"><span>Near · 0 mm</span><span>Far · {maximum.toLocaleString()} mm</span></div></div>
        <p className="map-note"><span className="swatch" /> No valid target <span className="confidence-mark">•</span> Lower confidence (status 9)</p>
      </section>}
    </div>
      {showDistance && <aside className="details">
        <section className="panel"><p className="eyebrow">FRAME SNAPSHOT</p><div className="stats"><div><span>Nearest</span><strong>{distances.length ? Math.min(...distances).toLocaleString() : '—'} <small>mm</small></strong></div><div><span>Farthest</span><strong>{distances.length ? Math.max(...distances).toLocaleString() : '—'} <small>mm</small></strong></div></div><dl><div><dt>Valid zones</dt><dd>{frame ? `${distances.length} / ${zones.length}` : '—'}</dd></div><div><dt>Frame sequence</dt><dd>{frame?.sequence ?? '—'}</dd></div><div><dt>Age at response</dt><dd>{frame ? `${frame.age_ms} ms` : '—'}</dd></div></dl></section>
        <section className="panel controls"><p className="eyebrow">DISPLAY SETTINGS</p><label htmlFor="scale">Distance scale <span>{maximum.toLocaleString()} mm</span></label><input id="scale" type="range" min="500" max="8000" step="100" value={maximum} onChange={e => setMaximum(Number(e.target.value))} /><label htmlFor="rotation">Clockwise rotation</label><select id="rotation" value={orientation.rotation} disabled={tofControlsDisabled} onChange={e => tofControls.update({ rotation: Number(e.target.value) })}>{[0, 90, 180, 270].map(degrees => <option key={degrees} value={degrees}>{degrees}°</option>)}</select><label className="check"><input type="checkbox" checked={orientation.flip_h} disabled={tofControlsDisabled} onChange={e => tofControls.update({ flip_h: e.target.checked })} /> Mirror horizontally</label><label className="check"><input type="checkbox" checked={orientation.flip_v} disabled={tofControlsDisabled} onChange={e => tofControls.update({ flip_v: e.target.checked })} /> Mirror vertically</label>{tofControls.error && <p role="alert">{tofControls.error}</p>}<label className="check"><input type="checkbox" checked={strict} onChange={e => setStrict(e.target.checked)} /> Only high confidence (status 5)</label><p className="muted small">Device orientation: clockwise rotation, then horizontal/vertical flips. Check with an object in a known corner.</p></section>
        <section className="panel"><p className="eyebrow">ZONE INSPECTOR</p><h2>Zone {zone?.id ?? '—'} <span className="muted small">/ zero-based</span></h2><dl><div><dt>Native row / column</dt><dd>{zone ? `${zone.row} / ${zone.col}` : '—'}</dd></div><div><dt>Distance</dt><dd>{zone?.mm != null ? `${zone.mm} mm` : '—'}</dd></div><div><dt>Target status</dt><dd>{zone?.status ?? '—'}</dd></div><div><dt>Targets detected</dt><dd>{zone?.targets ?? '—'}</dd></div></dl><p className="muted small">Select a cell to inspect its reading.</p></section>
      </aside>}
    <footer><span><span className="footer-dot" /> VL53L7CX · Multizone depth monitor</span><span>HTTP / REST · Local network</span></footer>
  </main>;
}
