import client from './client';

/**
 * Authenticate an existing user.
 * @param {string} email
 * @param {string} mot_de_passe
 * @returns {Promise} Axios response
 */
export const login = (email, mot_de_passe) =>
  client.post('/api/auth/login', { email, mot_de_passe });

/**
 * Register a new user account.
 * @param {Object} data - Registration payload (email, password, name, role, …)
 * @returns {Promise} Axios response
 */
export const register = (data) =>
  client.post('/api/auth/register', data);
