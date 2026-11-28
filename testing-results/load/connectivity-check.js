import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 1,
  duration: '10s',
};

export default function () {
  const endpoints = ['/health', '/ready', '/auth/config'];

  for (const endpoint of endpoints) {
    const response = http.get(`http://api:8000${endpoint}`);

    check(response, {
      [`${endpoint} returns 200`]: (r) => r.status === 200,
    });
  }
}
