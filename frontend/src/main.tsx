import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from '@/app';
import { BackendBootGate } from '@/components/system/backend-boot-gate';
import '@/styles/globals.css';

// register service worker for offline support. skip inside tauri:
// the webview loads from tauri://localhost, which is not a secure
// context the service-worker spec recognises, and there is nothing
// useful to cache offline when the sidecar is bundled in-process.
const isTauriWebview =
  typeof (window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ !==
  'undefined';
if (
  'serviceWorker' in navigator &&
  import.meta.env.PROD &&
  !isTauriWebview
) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // sw registration failed — app works without it
    });
  });
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BackendBootGate>
      <App />
    </BackendBootGate>
  </StrictMode>,
);
