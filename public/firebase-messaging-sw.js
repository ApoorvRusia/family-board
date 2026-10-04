/* Family Board: background push handler for due-date digests.
   Browsers deliver push here when the app is closed; the message is shown
   as a system notification. Pair with the site's notification settings. */
importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyAdF6OOfDklYdw-bN7DF_RciW-1hm1Maq4",
  authDomain: "family-board-25583.firebaseapp.com",
  projectId: "family-board-25583",
  storageBucket: "family-board-25583.firebasestorage.app",
  messagingSenderId: "847195748663",
  appId: "1:847195748663:web:cd014b2d061b6165df42b2"
});

const messaging = firebase.messaging();
messaging.onBackgroundMessage(payload => {
  const n = payload.notification || {};
  self.registration.showNotification(n.title || 'Family Board', {
    body: n.body || '',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    data: { url: '/' }
  });
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(clients.openWindow(url));
});
