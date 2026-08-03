import axios from 'axios';

const TOKEN_KEY = 'lova_token';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  // Do NOT set a default Content-Type here.
  // For JSON requests Axios sets it automatically.
  // For multipart/form-data (file uploads) the browser must set it
  // with the correct boundary — any default here would override that.
});

// Request interceptor — attach Bearer token when available
client.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // For FormData payloads, remove any Content-Type so the browser
    // sets multipart/form-data with the correct boundary automatically.
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type'];
    } else if (!config.headers['Content-Type']) {
      config.headers['Content-Type'] = 'application/json';
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor — on an expired/invalid token, clear it and send the
// user back to /login instead of leaving the page stuck on a failed request.
// Skip this for the auth endpoints themselves: a 401 from /auth/login means
// "wrong credentials", not "session expired" — that should stay on the page
// so the form can show the error, not force a redirect.
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const url = error.config?.url || '';
    const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/register');

    if (status === 401 && !isAuthEndpoint) {
      localStorage.removeItem(TOKEN_KEY);
      if (window.location.pathname !== '/login') {
        window.location.assign('/login');
      }
    }

    return Promise.reject(error);
  }
);

export default client;