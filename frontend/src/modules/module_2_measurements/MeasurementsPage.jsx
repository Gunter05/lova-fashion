import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  createSession,
  uploadPhoto,
  setStature,
  triggerProcess,
  getSessionStatus,
  listSessions,
} from '../../api/modules';
import { useFlow } from '../../context/FlowContext';
import { useLanguage } from '../../context/LanguageContext';

// ─── Error parsing utility ────────────────────────────────────────────────────
/**
 * Extracts a human-readable message from an Axios error.
 * Handles the three response shapes the backend can return:
 *   1. { detail: "string" }                       — HTTPException
 *   2. { detail: [{field, message}, ...] }        — 422 field-level list
 *   3. { detail: "...", errors: [{loc, msg},...]} — RequestValidationError wrapper
 *   4. Network error (no response)
 */
function extractErrorMessage(err, t) {
  // Log the full error for debugging
  console.error('[MeasurementsPage] API error:', err?.response?.status, err?.response?.data);

  const data   = err?.response?.data;
  const detail = data?.detail;

  // Shape 3: wrapper with `errors` array (RequestValidationError from main.py handler)
  if (data?.errors && Array.isArray(data.errors)) {
    const msgs = data.errors
      .map((e) => e.msg || e.message || JSON.stringify(e))
      .filter(Boolean);
    return msgs.length ? msgs.join(' — ') : (detail || t('common.error'));
  }

  // Shape 2: array of field-level errors
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => d.message || d.msg || JSON.stringify(d)).filter(Boolean);
    return msgs.length ? msgs.join(' — ') : t('common.error');
  }

  // Shape 1: plain string
  if (typeof detail === 'string' && detail.trim()) return detail;

  // Network error
  if (!err?.response) return 'Erreur réseau. Vérifiez votre connexion.';

  return t('common.error');
}

/**
 * Converts any image File to a JPEG Blob via canvas.
 * This ensures the backend always receives image/jpeg, regardless of the
 * original format (HEIC, HEIF, WebP, PNG from camera, etc.).
 * Falls back to the original file if conversion fails.
 */
async function toJpegBlob(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width  = img.naturalWidth;
        canvas.height = img.naturalHeight;
        canvas.getContext('2d').drawImage(img, 0, 0);
        canvas.toBlob(
          (blob) => {
            URL.revokeObjectURL(url);
            if (blob) {
              // Give the blob a proper filename so content-type is set correctly
              resolve(new File([blob], 'photo.jpg', { type: 'image/jpeg' }));
            } else {
              resolve(file);
            }
          },
          'image/jpeg',
          0.92,
        );
      } catch {
        URL.revokeObjectURL(url);
        resolve(file);
      }
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
    img.src = url;
  });
}

// ─── Constants ────────────────────────────────────────────────────────────────
const POLL_INTERVAL_MS = 3000;

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function MeasurementsPage() {
  const navigate = useNavigate();
  const { flow, setFlow } = useFlow();
  const { t } = useLanguage();

  const [sessions,        setSessions]        = useState([]);
  const [activeSession,   setActiveSession]   = useState(null);
  const [sessionStatus,   setSessionStatus]   = useState(null);
  const [statureValue,    setStatureValue]    = useState('');
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [launching,       setLaunching]       = useState(false);
  const [uploadingFront,  setUploadingFront]  = useState(false);
  const [uploadingProfile,setUploadingProfile]= useState(false);
  const [polling,         setPolling]         = useState(false);
  const [error,           setError]           = useState('');
  const [info,            setInfo]            = useState('');
  const [captureModal,    setCaptureModal]    = useState(null); // 'front' | 'profile' | null
  const pollRef = useRef(null);

  // ── Load sessions on mount ──────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const res = await listSessions();
        const list = res.data?.sessions || [];
        setSessions(list);
        // Restore active session from FlowContext if still valid
        if (flow.sessionId) {
          const match = list.find((s) => s.session_id === flow.sessionId);
          if (match) {
            setActiveSession(match);
            // Fetch full status to get photo URLs and measurements
            try {
              const statusRes = await getSessionStatus(flow.sessionId);
              setSessionStatus(statusRes.data);
              // Resume polling if still processing
              if (statusRes.data.status === 'processing') {
                // startPolling is not available here yet — handled via a flag
              }
            } catch {
              setSessionStatus(match);
            }
          }
        }
      } catch {
        setError(t('measurements.unableLoadSessions'));
      } finally {
        setLoadingSessions(false);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Polling ─────────────────────────────────────────────────────────────────
  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    setPolling(false);
  }, []);

  const startPolling = useCallback((sessionId) => {
    stopPolling();
    setPolling(true);
    pollRef.current = setInterval(async () => {
      try {
        const res = await getSessionStatus(sessionId);
        setSessionStatus(res.data);
        if (res.data.status === 'success' || res.data.status === 'failed') {
          stopPolling();
        }
      } catch { stopPolling(); }
    }, POLL_INTERVAL_MS);
  }, [stopPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  // ── Resume polling if restored session is still processing ─────────────────
  useEffect(() => {
    if (sessionStatus?.status === 'processing' && activeSession && !pollRef.current) {
      startPolling(activeSession.session_id);
    }
  }, [sessionStatus?.status, activeSession, startPolling]);

  // ── Start a new session (no API call yet — just open the capture flow) ──────
  const handleStart = useCallback(async () => {
    setError(''); setInfo('');
    try {
      const res = await createSession();
      const sess = res.data;
      setActiveSession(sess);
      setSessionStatus(sess);
      setFlow({ sessionId: sess.session_id });
      setInfo(t('measurements.newSessionCreated'));
    } catch (err) {
      setError(err?.response?.data?.detail || t('common.error'));
    }
  }, [setFlow, t]);

  // ── Upload a photo (from file or from camera blob) ──────────────────────────
  const handlePhotoFile = useCallback(async (view, file) => {
    if (!activeSession) return;
    const setter = view === 'front' ? setUploadingFront : setUploadingProfile;
    setter(true); setError('');
    try {
      // Convert to JPEG so the backend always receives a supported MIME type
      // (handles HEIC, HEIF, WebP, and other camera formats)
      const jpegFile = await toJpegBlob(file);
      await uploadPhoto(activeSession.session_id, view, jpegFile);
      setInfo(view === 'front' ? t('measurements.frontPhotoUploaded') : t('measurements.sidePhotoUploaded'));
      // Refresh status to know which photos are uploaded
      const res = await getSessionStatus(activeSession.session_id);
      setSessionStatus(res.data);
    } catch (err) {
      setError(extractErrorMessage(err, t));
    } finally {
      setter(false);
    }
  }, [activeSession, t]);

  // ── Launch estimation ────────────────────────────────────────────────────────
  const handleLaunch = useCallback(async () => {
    if (!activeSession) return;
    setError(''); setInfo('');
    const stature = parseFloat(statureValue);
    if (!statureValue || isNaN(stature) || stature < 100 || stature > 250) {
      setError(t('measurements.statureError')); return;
    }
    setLaunching(true);
    try {
      await setStature(activeSession.session_id, stature);
      await triggerProcess(activeSession.session_id);
      setInfo(t('measurements.processingStarted'));
      startPolling(activeSession.session_id);
    } catch (err) {
      setError(extractErrorMessage(err, t));
    } finally {
      setLaunching(false);
    }
  }, [activeSession, statureValue, startPolling, t]);

  // ── Computed helpers ─────────────────────────────────────────────────────────
  const hasFront   = Boolean(sessionStatus?.front_photo_url   ?? activeSession?.front_photo_url);
  const hasProfile = Boolean(sessionStatus?.profile_photo_url ?? activeSession?.profile_photo_url);
  const status     = sessionStatus?.status ?? activeSession?.status;
  const canLaunch  = hasFront && hasProfile && status !== 'processing' && status !== 'success';

  // ── Landing screen (no active session) ──────────────────────────────────────
  if (!activeSession) {
    return (
      <div className="space-y-5 max-w-lg mx-auto" style={{ background: '#FDFBF7', minHeight: '100vh' }}>
        <div className="pt-2">
          <h1 className="text-lg font-bold text-gray-900">{t('measurements.title')}</h1>
          <p className="text-xs text-gray-400 mt-0.5">{t('measurements.subtitle')}</p>
        </div>

        {/* Tips */}
        <div className="grid grid-cols-3 gap-3">
          {[
            { key: 'straight',  icon: '🧍' },
            { key: 'fitting',   icon: '👕' },
            { key: 'waist',     icon: '📱' },
          ].map(({ key, icon }) => (
            <div key={key} className="bg-white rounded-2xl border border-[#F0EDE8] p-3 text-center shadow-sm">
              <div className="text-2xl mb-1">{icon}</div>
              <p className="text-xs font-semibold text-gray-800">{t(`measurements.tips.${key}.title`)}</p>
              <p className="text-[10px] text-gray-400 mt-0.5 leading-tight">{t(`measurements.tips.${key}.desc`)}</p>
            </div>
          ))}
        </div>

        {error && <Toast type="error" message={error} onClose={() => setError('')} />}

        {/* CTA */}
        <button
          onClick={handleStart}
          className="w-full py-4 rounded-2xl text-sm font-bold text-white shadow-md"
          style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
        >
          {t('measurements.btnStart')}
        </button>

        {/* Past sessions */}
        {loadingSessions ? <Spinner /> : sessions.length > 0 && (
          <div className="bg-white rounded-2xl border border-[#F0EDE8] p-4 shadow-sm">
            <h2 className="text-xs font-semibold text-gray-500 mb-3 uppercase tracking-wide">{t('measurements.captureSessions')}</h2>
            <div className="space-y-2">
              {sessions.map((s) => (
                <button key={s.session_id} onClick={() => { setActiveSession(s); setSessionStatus(s); setFlow({ sessionId: s.session_id }); }}
                  className="w-full flex items-center justify-between px-3 py-2.5 rounded-xl bg-[#FDFBF7] border border-[#F0EDE8] hover:border-[#D95D39]/40 transition">
                  <span className="text-xs text-gray-600">{new Date(s.created_at).toLocaleDateString()}</span>
                  <StatusBadge status={s.status} />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── Active session screen ────────────────────────────────────────────────────
  return (
    <div className="space-y-4 max-w-lg mx-auto" style={{ background: '#FDFBF7', minHeight: '100vh' }}>
      {/* Header */}
      <div className="flex items-center justify-between pt-1">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{t('measurements.sessionDetail')}</h1>
          <StatusBadge status={status} />
        </div>
        <button onClick={() => { setActiveSession(null); setSessionStatus(null); setFlow({ sessionId: null }); stopPolling(); }}
          className="text-xs text-gray-400 underline underline-offset-2">
          ← {t('measurements.btnStart')}
        </button>
      </div>

      {error && <Toast type="error"   message={error}   onClose={() => setError('')} />}
      {info  && <Toast type="success" message={info}    onClose={() => setInfo('')}  />}

      {/* Success state */}
      {status === 'success' && sessionStatus?.measurements && (
        <MeasurementResults measurements={sessionStatus.measurements} t={t} onContinue={() => navigate('/modules/3')} />
      )}

      {/* Failed state */}
      {status === 'failed' && (
        <div className="bg-red-50 border border-red-100 rounded-2xl p-4 space-y-1">
          <p className="text-sm font-semibold text-red-700">{t('measurements.failureReason')}</p>
          <p className="text-xs text-red-600">{sessionStatus?.failure_reason || '—'}</p>
        </div>
      )}

      {/* Processing state */}
      {(status === 'processing' || polling) && (
        <div className="bg-white border border-[#F0EDE8] rounded-2xl p-5 flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-4 border-[#F0EDE8] border-t-[#D95D39] rounded-full animate-spin" />
          <p className="text-sm text-gray-500">{t('measurements.analyzing')}</p>
        </div>
      )}

      {/* Photo capture cards */}
      {status !== 'success' && (
        <div className="grid grid-cols-2 gap-3">
          <PhotoSlot
            label={t('measurements.frontPhoto')}
            hasPhoto={hasFront}
            uploading={uploadingFront}
            onCapture={() => setCaptureModal('front')}
          />
          <PhotoSlot
            label={t('measurements.sidePhoto')}
            hasPhoto={hasProfile}
            uploading={uploadingProfile}
            onCapture={() => setCaptureModal('profile')}
          />
        </div>
      )}

      {/* Stature + launch */}
      {status !== 'success' && status !== 'processing' && (
        <div className="bg-white rounded-2xl border border-[#F0EDE8] p-4 shadow-sm space-y-3">
          <label className="block text-xs font-medium text-gray-500">{t('measurements.height')}</label>
          <input type="number" min={100} max={250} placeholder="170"
            value={statureValue} onChange={(e) => setStatureValue(e.target.value)}
            className="w-full rounded-xl border border-[#E8E4DF] px-4 py-2.5 text-sm focus:outline-none focus:border-[#D95D39] bg-white" />
          <button onClick={handleLaunch} disabled={!canLaunch || launching}
            className="w-full py-3.5 rounded-2xl text-sm font-bold text-white disabled:opacity-40 transition"
            style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}>
            {launching ? t('measurements.processingBtn') : t('measurements.processBtn')}
          </button>
        </div>
      )}

      {/* Capture modal */}
      {captureModal && (
        <CaptureModal
          view={captureModal}
          t={t}
          onFile={(file) => { handlePhotoFile(captureModal, file); setCaptureModal(null); }}
          onClose={() => setCaptureModal(null)}
        />
      )}
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

/** Card representing one photo slot (front or profile). */
function PhotoSlot({ label, hasPhoto, uploading, onCapture }) {
  return (
    <button onClick={onCapture} disabled={uploading}
      className={`bg-white rounded-2xl border p-4 flex flex-col items-center gap-2 shadow-sm transition hover:shadow-md ${hasPhoto ? 'border-[#4E6E58]/40' : 'border-[#F0EDE8]'}`}>
      <div className={`w-12 h-12 rounded-full flex items-center justify-center text-xl ${hasPhoto ? 'bg-[#4E6E58]/10' : 'bg-[#F5F0EA]'}`}>
        {uploading ? (
          <div className="w-5 h-5 border-2 border-[#D95D39] border-t-transparent rounded-full animate-spin" />
        ) : hasPhoto ? '✅' : '📷'}
      </div>
      <p className="text-xs font-semibold text-gray-700 text-center leading-tight">{label}</p>
      {hasPhoto && <p className="text-[10px] text-[#4E6E58] font-medium">✓ ajoutée</p>}
    </button>
  );
}

/**
 * Modal that offers the user two options per photo view:
 *   1. Take a photo with the camera (via <input capture="environment">)
 *   2. Upload an existing file from their device
 */
function CaptureModal({ view, t, onFile, onClose }) {
  const { locale } = useLanguage();
  const cameraRef = useRef(null);
  const fileRef   = useRef(null);

  const handleChange = (e) => {
    const file = e.target.files?.[0];
    if (file) onFile(file);
    e.target.value = '';
  };

  const label = view === 'front' ? t('measurements.frontPhoto') : t('measurements.sidePhoto');
  const isFr  = locale === 'fr';

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center" onClick={onClose}>
      <div className="bg-white rounded-t-3xl sm:rounded-3xl w-full sm:max-w-sm p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        {/* Handle */}
        <div className="w-10 h-1 rounded-full bg-gray-300 mx-auto sm:hidden" />

        <h3 className="text-base font-bold text-gray-900 text-center">{label}</h3>
        <p className="text-xs text-gray-400 text-center">
          {isFr ? 'Comment souhaitez-vous ajouter cette photo ?' : 'How would you like to add this photo?'}
        </p>

        {/* Option 1 — Camera */}
        <button
          onClick={() => cameraRef.current?.click()}
          className="w-full flex items-center gap-4 p-4 rounded-2xl border border-[#F0EDE8] bg-[#FDFBF7] hover:border-[#D95D39]/40 transition">
          <div className="w-10 h-10 rounded-full bg-[#D95D39]/10 flex items-center justify-center text-xl">📸</div>
          <div className="text-left">
            <p className="text-sm font-semibold text-gray-800">
              {isFr ? 'Prendre une photo' : 'Take a photo'}
            </p>
            <p className="text-xs text-gray-400">
              {isFr ? 'Utiliser directement la caméra' : 'Use your camera directly'}
            </p>
          </div>
        </button>
        {/* hidden camera input */}
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={handleChange} />

        {/* Divider */}
        <div className="flex items-center gap-2 text-gray-300">
          <div className="flex-1 h-px bg-gray-200" />
          <span className="text-xs">{t('common.or')}</span>
          <div className="flex-1 h-px bg-gray-200" />
        </div>

        {/* Option 2 — File upload */}
        <button
          onClick={() => fileRef.current?.click()}
          className="w-full flex items-center gap-4 p-4 rounded-2xl border border-[#F0EDE8] bg-[#FDFBF7] hover:border-[#D95D39]/40 transition">
          <div className="w-10 h-10 rounded-full bg-[#4E6E58]/10 flex items-center justify-center text-xl">🖼️</div>
          <div className="text-left">
            <p className="text-sm font-semibold text-gray-800">
              {isFr ? 'Téléverser une photo' : 'Upload a photo'}
            </p>
            <p className="text-xs text-gray-400">
              {isFr ? 'Choisir depuis la galerie' : 'Choose from your gallery'}
            </p>
          </div>
        </button>
        {/* hidden file input */}
        <input ref={fileRef} type="file" accept="image/jpeg,image/png" className="hidden" onChange={handleChange} />

        {/* Cancel */}
        <button onClick={onClose} className="w-full py-3 rounded-2xl text-sm font-medium text-gray-400 bg-[#F5F0EA]">
          {t('common.close')}
        </button>
      </div>
    </div>
  );
}

/** Displays the estimated measurements once the session succeeds. */
function MeasurementResults({ measurements, t, onContinue }) {
  const rows = [
    { label: t('measurements.chest'), value: measurements.bust_cm },
    { label: t('measurements.waist'), value: measurements.waist_cm },
    { label: t('measurements.hips'),  value: measurements.hips_cm },
  ];
  return (
    <div className="bg-white rounded-2xl border border-[#4E6E58]/30 p-5 shadow-sm space-y-4">
      <h2 className="text-sm font-semibold text-[#3A5242]">{t('measurements.estimatedMeasurements')}</h2>

      {/* Silhouette badge */}
      {measurements.silhouette_code && (
        <span className="inline-block px-3 py-1 rounded-full bg-[#D95D39]/10 text-[#D95D39] text-xs font-bold">
          {measurements.silhouette_code}
        </span>
      )}

      <div className="grid grid-cols-3 gap-3">
        {rows.map(({ label, value }) => (
          <div key={label} className="bg-[#FDFBF7] rounded-2xl p-3 text-center border border-[#F0EDE8]">
            <p className="text-lg font-extrabold text-gray-900">{Number(value).toFixed(1)}</p>
            <p className="text-[10px] text-gray-400 mt-0.5">cm</p>
            <p className="text-[10px] font-medium text-gray-600 mt-1 leading-tight">{label}</p>
          </div>
        ))}
      </div>

      <button onClick={onContinue}
        className="w-full py-3.5 rounded-2xl text-sm font-bold text-white"
        style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}>
        {t('measurements.chooseFabricPattern')}
      </button>
    </div>
  );
}

/** Small colored badge showing session status. */
function StatusBadge({ status }) {
  const map = {
    empty:      { bg: 'bg-gray-100',       text: 'text-gray-500',   label: 'Vide' },
    processing: { bg: 'bg-yellow-50',      text: 'text-yellow-600', label: 'En cours' },
    success:    { bg: 'bg-[#4E6E58]/10',   text: 'text-[#3A5242]',  label: 'Succès' },
    failed:     { bg: 'bg-red-50',         text: 'text-red-600',    label: 'Échec' },
  };
  const s = map[status] || map.empty;
  return (
    <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  );
}

function Toast({ type, message, onClose }) {
  const s = {
    error:   'bg-red-50 border-red-100 text-red-700',
    success: 'bg-[#4E6E58]/5 border-[#4E6E58]/20 text-[#3A5242]',
  };
  return (
    <div className={`flex items-center justify-between rounded-2xl border px-4 py-3 text-sm ${s[type]}`}>
      <span>{message}</span>
      <button onClick={onClose} className="ml-4 font-bold opacity-60">×</button>
    </div>
  );
}

function Spinner() {
  return (
    <div className="flex items-center justify-center min-h-[20vh]">
      <div className="w-8 h-8 border-4 border-[#F0EDE8] border-t-[#D95D39] rounded-full animate-spin" />
    </div>
  );
}
