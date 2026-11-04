import { useState } from 'react';
import { cameraPlacement } from './camera.js';

export default function CameraPanel({ baseUrl, distanceMm, stream, comparison = true }) {
  const { frame, error } = stream;
  const [failedImage, setFailedImage] = useState(null);
  const imageFailed = frame && failedImage === frame.image_base64;
  const visible = imageFailed ? null : frame;
  return <section className="panel visualization camera-panel">
    <div className="panel-heading"><div><p className="eyebrow">CAMERA / MARBLE DETECTION</p><h2>Camera view</h2></div><span className="unit">{visible ? (visible.detection_enabled === false ? 'Raw video' : `${visible.objects.length} candidates`) : 'No image'}</span></div>
    <div className={`camera-stage ${comparison ? '' : 'full-camera'}`} aria-label="Camera comparison view">
      {visible && <img alt={visible.detection_enabled === false ? 'Live camera raw image' : 'Live camera with marble candidate bounding boxes'} src={`data:image/jpeg;base64,${visible.image_base64}`} style={comparison ? cameraPlacement(visible.geometry, distanceMm) : undefined} onError={() => setFailedImage(visible.image_base64)} />}
      {!visible && <div className="grid-message"><strong>{imageFailed ? 'Image could not be decoded' : error || (baseUrl ? 'Camera initializing…' : 'Camera disconnected')}</strong><span>{baseUrl ? 'Waiting for a fresh camera frame.' : 'Connect your board to see marble candidates.'}</span></div>}
    </div>
    {comparison && <p className="muted small">Nominal scale matched to the ToF field of view at {distanceMm} mm. Dark bands are outside camera coverage.</p>}
    <div className="object-info" aria-label="Detected objects">
      <p className="eyebrow">OBJECT INFO {visible && `· FRAME ${visible.sequence} · ${visible.age_ms} ms`}</p>
      {visible ? (visible.detection_enabled === false ? <p className="muted small">Object detection disabled — raw image.</p> : visible.objects.length ? <ul>{visible.objects.map(o => <li key={o.id}><strong>#{o.id + 1} {o.label}</strong><span>Box ({o.bbox.x}, {o.bbox.y}) · {o.bbox.width} × {o.bbox.height} px · radius {o.radius_px} px · edge strength {o.magnitude}</span></li>)}</ul> : <p className="muted small">No marble candidates detected.</p>) : <p className="muted small">No current detections.</p>}
    </div>
  </section>;
}
