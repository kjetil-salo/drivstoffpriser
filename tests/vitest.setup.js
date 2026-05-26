// Node.js v22+ has a built-in localStorage that requires --localstorage-file.
// Replace it with a simple in-memory mock so list.js can be imported cleanly.
import { vi } from 'vitest';

const store = {};
vi.stubGlobal('localStorage', {
    getItem: (k) => store[k] ?? null,
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
    clear: () => { Object.keys(store).forEach(k => delete store[k]); },
});
