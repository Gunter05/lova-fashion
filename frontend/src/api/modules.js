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

// ── Module 7: Reports ─────────────────────────────────────────────────────────
export const listMyReports  = (cni, role) => client.get('/api/reports/me', { headers: { 'x-user-cni': cni, 'x-user-role': role } });
export const getReport      = (id, cni, role) => client.get(`/api/reports/${id}`, { headers: { 'x-user-cni': cni, 'x-user-role': role } });
