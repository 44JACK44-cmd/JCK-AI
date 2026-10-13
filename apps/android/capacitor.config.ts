import type { CapacitorConfig } from '@capacitor/cli';

// NEXUS AI Android wrapper.
// The UI is built by Vite into frontend/dist and copied into the native app.
// The backend (FastAPI) is NOT bundled: set NEXUS_BACKEND_URL (e.g.
// http://192.168.1.50:8000) to point the WebView at a machine on your LAN,
// or leave it unset to load the local assets only.
const backendUrl = process.env.NEXUS_BACKEND_URL;

const config: CapacitorConfig = {
  appId: 'com.nexus.ai',
  appName: 'NEXUS AI',
  webDir: '../../frontend/dist',
  ...(backendUrl
    ? { server: { url: backendUrl, cleartext: true } }
    : {}),
  android: {
    allowMixedContent: true,
  },
};

export default config;
