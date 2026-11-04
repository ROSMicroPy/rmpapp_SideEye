import { useEffect, useRef, useState } from 'react';

export default function useDeviceSettings(baseUrl, endpoint, validate) {
  const [state, setState] = useState({ settings: null, busy: false, error: '' });
  const connection = useRef(null);
  useEffect(() => {
    const session = { controller: new AbortController(), updating: false };
    connection.current = session;
    setState({ settings: null, busy: !!baseUrl, error: '' });
    if (baseUrl) request('GET', undefined, session);
    return () => { session.controller.abort(); connection.current = null; };
  }, [baseUrl, endpoint, validate]);

  async function request(method, values, session) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    session.controller.signal.addEventListener('abort', abort);
    const timeout = setTimeout(abort, 5000);
    try {
      const response = await fetch(`${baseUrl}${endpoint}`, {
        method, signal: controller.signal, cache: 'no-store',
        ...(method === 'POST' ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values) } : {}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      const settings = validate(data);
      if (connection.current === session) setState({ settings, busy: false, error: '' });
    } catch (error) {
      if (connection.current === session) setState(previous => ({ ...previous, busy: false,
        error: error.name === 'AbortError' ? 'Device control request timed out; reconnect to read device settings.' : error.message }));
    } finally {
      clearTimeout(timeout);
      session.controller.signal.removeEventListener('abort', abort);
      session.updating = false;
    }
  }
  function update(values) {
    const session = connection.current;
    if (!baseUrl || !session || session.updating || state.busy || !state.settings) return;
    session.updating = true;
    setState(previous => ({ ...previous, busy: true, error: '' }));
    request('POST', values, session);
  }
  return { ...state, update };
}
