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

export default client;
