/**
 * API helpers for all module endpoints.
 * All calls go through the Axios client which auto-injects the Bearer token.
 */
import client from './client';

// ── Module 1: Profile ─────────────────────────────────────────────────────────
export const getMyProfile    = ()           => client.get('/api/users/me');
export const updateMyProfile = (data)       => client.patch('/api/users/me', data);
export const uploadProfilePhoto = (file) => {
  const fd = new FormData();
  fd.append('file', file);
  return client.post('/api/users/me/photos', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};
export const getPhotoHistory = ()           => client.get('/api/users/me/photos');

// ── Module 2: Measurements ────────────────────────────────────────────────────
export const createSession    = ()                      => client.post('/api/measurements/sessions');
export const listSessions     = ()                      => client.get('/api/measurements/sessions');
export const getSessionStatus = (id)                    => client.get(`/api/measurements/sessions/${id}/status`);
export const setStature       = (id, stature_cm)        => client.patch(`/api/measurements/sessions/${id}/stature`, { stature_cm });
export const triggerProcess   = (id)                    => client.post(`/api/measurements/sessions/${id}/process`);
export const uploadPhoto      = (id, view, file) => {
  const fd = new FormData();
  fd.append('file', file);
  return client.put(`/api/measurements/sessions/${id}/photos/${view}`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

// ── Module 3: Fabric Catalog ──────────────────────────────────────────────────
export const listFabrics       = (categoryId) => client.get('/api/fabrics', { params: categoryId ? { category_id: categoryId } : {} });
export const getFabric         = (id)         => client.get(`/api/fabrics/${id}`);
export const selectFabric      = (id)         => client.post(`/api/fabrics/${id}/select`);
export const listCategories    = ()           => client.get('/api/categories');

// ── Module 4: Pattern Catalog ─────────────────────────────────────────────────
export const listModels  = (garment_type) => client.get('/api/models', { params: garment_type ? { garment_type } : {} });
export const getModel    = (id)           => client.get(`/api/models/${id}`);

// ── Module 5: Ease Margins ────────────────────────────────────────────────────
export const computeAdjustment    = (session_id, fabric_id) => client.post('/api/ease/adjustments', { session_id, fabric_id });
export const getAdjustment        = (id)                    => client.get(`/api/ease/adjustments/${id}`);
export const listAdjustments      = (session_id)            => client.get(`/api/ease/sessions/${session_id}/adjustments`);

// ── Module 6: Compatibility Engine ───────────────────────────────────────────

/**
 * Trigger a full compatibility evaluation (fabric × pattern × body shape).
 * @param {string} session_id   - UUID of the measurement session
 * @param {string} fabric_id    - UUID of the chosen fabric
 * @param {string} model_id     - UUID of the chosen garment pattern
 * @returns {Promise} 201 VerdictEvaluationResponse
 */
export const createVerification = (session_id, fabric_id, model_id) =>
  client.post('/api/compatibility/verifications', { session_id, fabric_id, model_id });

/**
 * Retrieve an existing compatibility evaluation.
 * @param {string} id - UUID of the evaluation
 * @returns {Promise} 200 VerdictEvaluationResponse
 */
export const getVerification = (id) =>
  client.get(`/api/compatibility/verifications/${id}`);

// Admin-only — compatibility rules management
export const listCompatibilityRules  = ()           => client.get('/api/compatibility/compatibility-rules');
export const createCompatibilityRule = (data)       => client.post('/api/compatibility/compatibility-rules', data);
export const updateCompatibilityRule = (id, data)   => client.patch(`/api/compatibility/compatibility-rules/${id}`, data);

// ── Module 7: Reports ─────────────────────────────────────────────────────────
export const listMyReports  = ()    => client.get('/api/reports/me');
export const getReport      = (id)  => client.get(`/api/reports/${id}`);
