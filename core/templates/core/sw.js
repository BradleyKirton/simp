const CACHE_NAME = 'offline-page-cache-v1';
const OFFLINE_PAGE = '/sw/';

self.addEventListener('install', (event) => {
	event.waitUntil(
		caches.open(CACHE_NAME).then((cache) => {
			return cache.add(OFFLINE_PAGE);
		})
	);
});

self.addEventListener('fetch', (event) => {
	if (event.request.mode !== 'navigate') return;
	event.respondWith(
		fetch(event.request).catch(() => {
			return caches.match(OFFLINE_PAGE);
		})
	);
});