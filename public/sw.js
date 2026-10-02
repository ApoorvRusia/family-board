// Minimal service worker: enables "install as app" without aggressive caching,
// so updates always show up immediately.
self.addEventListener('fetch', () => {});
