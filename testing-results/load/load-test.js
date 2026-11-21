import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 10 },
    { duration: '1m', target: 10 },
    { duration: '30s', target: 25 },
    { duration: '1m', target: 25 },
    { duration: '30s', target: 50 },
    { duration: '1m', target: 50 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
  },
};

const BASE_URL = 'http://api:8000';

export default function () {
  const endpoints = [
    '/health',
    '/ready',
    '/auth/config',
  ];

  for (const endpoint of endpoints) {
    const response = http.get(`${BASE_URL}${endpoint}`);

    check(response, {
      [`${endpoint} status is 200`]: (r) => r.status === 200,
    });
  }

  sleep(1);
}
