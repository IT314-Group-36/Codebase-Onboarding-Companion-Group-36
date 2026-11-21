import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '30s',
};

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:8000';

export default function () {

  // Test 1: Health endpoint
  let health = http.get(`${BASE_URL}/health`);

  check(health, {
    'Health returns 200': (r) => r.status === 200,
  });

  // Test 2: Readiness endpoint
  let ready = http.get(`${BASE_URL}/ready`);

  check(ready, {
    'Readiness returns 200': (r) => r.status === 200,
  });

  // Test 3: Authentication configuration
  let auth = http.get(`${BASE_URL}/auth/config`);

  check(auth, {
    'Auth config returns 200': (r) => r.status === 200,
  });

  sleep(1);
}
