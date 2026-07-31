import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  createSession, listSessions, getSessionStatus,
  setStature, triggerProcess, uploadPhoto,
} from '../../api/modules';
import { useFlow } from '../../context/FlowContext';
import { useLanguage } from '../../context/LanguageContext';

const STATUS_CONFIG = {
  empty:      { color: 'bg-gray-100 text-gray-500',      dot: 'bg-gray-400' },
  processing: { color: 'bg-blue-50 text-blue-600',       dot: 'bg-blue-500' },
  success:    { color: 'bg-[#4E6E58]/10 text-[#4E6E58]', dot: 'bg-[#4E6E58]' },
  failed:     { color: 'bg-red-50 text-red-600',         dot: 'bg-red-500' },
};

export default function MeasurementsPage() {
  const navigate = useNavigate();
  const { setFlow } = useFlow();
  const { t, locale } = useLanguage();

  const [sessions,   setSessions]   = useState([]);
  const [selected,   setSelected]   = useState(null);
  const [stature,    setStatureVal] = useState('');
  const [loading,    setLoading]    = useState(true);
  const [creating,   setCreating]   = useState(false);
  const [processing, setProcessing] = useState(false);
  const [polling,    setPolling]    = useState(false);
  const [error,      setError]      = useState('');
  const [success,    setSuccess]    = useState('');

  const getStatusLabel = (status) => {
    switch (status) {
      case 'empty': return locale === 'en' ? 'Empty' : 'Vide';
      case 'processing': return locale === 'en' ? 'Processing' : 'En traitement';
      case 'success': return locale === 'en' ? 'Success' : 'Succès';
      case 'failed': return locale === 'en' ? 'Failed' : 'Échoué';
      default: return status;
    }
  };

  // Photo upload state
  const [photoFront,   setPhotoFront]   = useState(null); // File
  const [photoSide,    setPhotoSide]    = useState(null); // File
  const [uploadingF,   setUploadingF]   = useState(false);
  const [uploadingS,   setUploadingS]   = useState(false);
  const [uploadedF,    setUploadedF]    = useState(false);
  const [uploadedS,    setUploadedS]    = useState(false);
  const frontInputRef = useRef(null);
  const sideInputRef  = useRef(null);

  const loadStatus = async (id) => {
    const res = await getSessionStatus(id);
    setSelected(res.data);
    return res.data;
  };

  const loadSessions = async () => {
    setLoading(true);
    try {
      const res = await listSessions();
      setSessions(res.data.sessions || []);
      const active = (res.data.sessions || []).find((s) => s.is_active);
      if (active) await loadStatus(active.session_id);
    } catch {
      setError(t('measurements.unableLoadSessions'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadSessions();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCreate = async () => {
    setCreating(true); setError('');
    setUploadedF(false); setUploadedS(false);
    setPhotoFront(null); setPhotoSide(null);
    try {
      const res = await createSession();
      await loadSessions();
      await loadStatus(res.data.session_id);
      setSuccess(t('measurements.newSessionCreated'));
    } catch { setError('Failed to create session.'); }
    finally { setCreating(false); }
  };

  const handlePhotoUpload = async (view, file) => {
    if (!selected?.session_id || !file) return;
    const setter = view === 'front' ? setUploadingF : setUploadingS;
    const doneSetter = view === 'front' ? setUploadedF : setUploadedS;
    setter(true); setError('');
    try {
      await uploadPhoto(selected.session_id, view, file);
      doneSetter(true);
      setSuccess(view === 'front' ? t('measurements.frontPhotoUploaded') : t('measurements.sidePhotoUploaded'));
    } catch (err) {
      const d = err?.response?.data?.detail;
      setError(typeof d === 'string' ? d : d?.message || `Error uploading photo ${view}.`);
    } finally {
      setter(false);
    }
  };

  const handleProcess = async () => {
    if (!selected?.session_id) return;
    const st = parseFloat(stature);
    if (!stature || isNaN(st) || st < 100 || st > 250) {
      setError(t('measurements.statureError')); return;
    }
    setProcessing(true); setError('');
    try {
      await setStature(selected.session_id, st);
      await triggerProcess(selected.session_id);
      setSuccess(t('measurements.processingStarted'));
      pollStatus(selected.session_id);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((d) => d.msg).join(', ') : detail?.message || 'Failed to start.');
    } finally { setProcessing(false); }
  };

  const pollStatus = (id) => {
    setPolling(true);
    const iv = setInterval(async () => {
      try {
        const data = await loadStatus(id);
        if (data.status === 'success' || data.status === 'failed') {
          clearInterval(iv); setPolling(false); await loadSessions();
        }
      } catch { clearInterval(iv); setPolling(false); }
    }, 3000);
  };

  const handleContinue = () => {
    // Enregistre l'ID de session dans le FlowContext avant de naviguer
    setFlow({ sessionId: selected.session_id });
    navigate('/modules/3');
  };

  if (loading) return <Spinner />;
  const m = selected?.measurements;

  return (
    <div className="space-y-5 max-w-lg mx-auto">
      {/* Steps banner */}
      <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5">
        <h1 className="text-lg font-bold text-gray-900 mb-1">{t('measurements.title')}</h1>
        <p className="text-xs text-gray-400 mb-4">{t('measurements.subtitle')}</p>
        <div className="space-y-3">
          {[
            { icon: '🧍', title: t('measurements.tips.straight.title'), desc: t('measurements.tips.straight.desc') },
            { icon: '👕', title: t('measurements.tips.fitting.title'), desc: t('measurements.tips.fitting.desc') },
            { icon: '📱', title: t('measurements.tips.waist.title'), desc: t('measurements.tips.waist.desc') },
          ].map(({ icon, title, desc }) => (
            <div key={title} className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#FAF8F5] flex items-center justify-center text-lg shrink-0">{icon}</div>
              <div>
                <p className="text-sm font-semibold text-gray-800">{title}</p>
                <p className="text-xs text-gray-400">{desc}</p>
              </div>
            </div>
          ))}
        </div>
        <button
          onClick={handleCreate}
          disabled={creating}
          className="w-full mt-4 rounded-2xl py-3.5 text-sm font-bold text-white flex items-center justify-center gap-2 disabled:opacity-60"
          style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
        >
          {creating ? '…' : <>{t('measurements.btnStart')} <span>→</span></>}
        </button>
      </div>

      {error   && <Toast type="error"   message={error}   onClose={() => setError('')} />}
      {success && <Toast type="success" message={success} onClose={() => setSuccess('')} />}

      {sessions.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">{t('measurements.captureSessions')}</h2>
          <div className="space-y-2">
            {sessions.map((s) => {
              const cfg = STATUS_CONFIG[s.status] ?? STATUS_CONFIG.empty;
              return (
                <button
                  key={s.session_id}
                  onClick={() => loadStatus(s.session_id)}
                  className={`w-full flex items-center justify-between px-4 py-3 rounded-xl border text-left transition ${
                    selected?.session_id === s.session_id
                      ? 'border-[#D95D39]/30 bg-[#D95D39]/5'
                      : 'border-[#F0EDE8] hover:border-[#E8E4DF]'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
                    <span className="text-sm text-gray-700 font-medium">
                      {new Date(s.created_at).toLocaleDateString(locale === 'en' ? 'en-US' : 'fr-FR')}
                      {s.is_active && <span className="ml-2 text-xs text-[#D95D39]">({t('common.active')})</span>}
                    </span>
                  </div>
                  <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${cfg.color}`}>{getStatusLabel(s.status)}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {selected && (
        <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700">{t('measurements.sessionDetail')}</h2>
            {polling && (
              <span className="flex items-center gap-1.5 text-xs text-blue-500">
                <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                {t('measurements.analyzing')}
              </span>
            )}
          </div>

          {(selected.status === 'empty' || selected.status === 'failed') && (
            <div className="space-y-4">
              <p className="text-xs text-gray-500">
                {t('measurements.instructions')}
              </p>

              {selected.status === 'failed' && selected.failure_reason && (
                <p className="text-xs text-red-600 bg-red-50 rounded-xl px-3 py-2">
                  {t('measurements.failureReason')} {selected.failure_reason}
                </p>
              )}

              {/* Photo uploads */}
              <div className="grid grid-cols-2 gap-3">
                {/* Photo face */}
                <div>
                  <input
                    ref={frontInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) { setPhotoFront(f); handlePhotoUpload('front', f); }
                    }}
                  />
                  <button
                    onClick={() => frontInputRef.current?.click()}
                    disabled={uploadingF}
                    className={`w-full rounded-xl border-2 border-dashed py-4 flex flex-col items-center gap-1.5 text-xs font-medium transition ${
                      uploadedF
                        ? 'border-[#4E6E58] bg-[#4E6E58]/5 text-[#4E6E58]'
                        : 'border-[#E8E4DF] text-gray-400 hover:border-[#D95D39] hover:text-[#D95D39]'
                    }`}
                  >
                    {uploadingF ? (
                      <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    ) : uploadedF ? (
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    ) : (
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                      </svg>
                    )}
                    {uploadedF ? `${t('measurements.frontPhoto')} ✓` : photoFront ? photoFront.name.slice(0, 12) + '…' : t('measurements.frontPhoto')}
                  </button>
                </div>

                {/* Photo profil */}
                <div>
                  <input
                    ref={sideInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) { setPhotoSide(f); handlePhotoUpload('side', f); }
                    }}
                  />
                  <button
                    onClick={() => sideInputRef.current?.click()}
                    disabled={uploadingS}
                    className={`w-full rounded-xl border-2 border-dashed py-4 flex flex-col items-center gap-1.5 text-xs font-medium transition ${
                      uploadedS
                        ? 'border-[#4E6E58] bg-[#4E6E58]/5 text-[#4E6E58]'
                        : 'border-[#E8E4DF] text-gray-400 hover:border-[#D95D39] hover:text-[#D95D39]'
                    }`}
                  >
                    {uploadingS ? (
                      <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    ) : uploadedS ? (
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    ) : (
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                      </svg>
                    )}
                    {uploadedS ? `${t('measurements.sidePhoto')} ✓` : photoSide ? photoSide.name.slice(0, 12) + '…' : t('measurements.sidePhoto')}
                  </button>
                </div>
              </div>

              {/* Stature + lancer */}
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-600 mb-1">{t('measurements.height')}</label>
                  <input
                    type="number"
                    min={100}
                    max={250}
                    value={stature}
                    onChange={(e) => setStatureVal(e.target.value)}
                    placeholder={locale === 'en' ? 'e.g. 170' : 'Ex: 170'}
                    className="w-full rounded-xl border border-[#E8E4DF] px-4 py-3 text-sm focus:outline-none focus:border-[#D95D39] bg-white"
                  />
                </div>
                <button
                  onClick={handleProcess}
                  disabled={processing || polling}
                  className="px-5 py-3 rounded-xl text-sm font-semibold text-white disabled:opacity-50"
                  style={{ background: '#D95D39' }}
                >
                  {processing ? '…' : t('measurements.processBtn')}
                </button>
              </div>
            </div>
          )}

          {selected.status === 'success' && m && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <span className="w-5 h-5 rounded-full bg-[#4E6E58] flex items-center justify-center text-white text-xs">✓</span>
                <p className="text-sm font-semibold text-[#4E6E58]">{t('measurements.estimatedMeasurements')}</p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {[
                  [t('measurements.chest'), m.tour_poitrine_cm],
                  [t('measurements.waist'), m.tour_taille_cm],
                  [t('measurements.hips'), m.tour_hanches_cm],
                  [t('measurements.arm'), m.longueur_bras_cm],
                  [t('measurements.height'), m.hauteur_cm],
                ].map(([label, val]) => (
                  <div key={label} className="bg-[#FAF8F5] rounded-xl p-3 flex items-center justify-between">
                    <p className="text-xs text-gray-400">{label}</p>
                    <p className="text-sm font-bold text-gray-900">
                      {val ?? '—'} <span className="text-xs font-normal text-gray-400">cm</span>
                    </p>
                  </div>
                ))}
              </div>
              {/* Bouton "Continuer" — maintenant fonctionnel */}
              <button
                onClick={handleContinue}
                className="w-full mt-4 rounded-2xl py-3.5 text-sm font-bold text-white flex items-center justify-center gap-2"
                style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
              >
                {t('measurements.chooseFabricPattern')}
              </button>
            </div>
          )}
        </div>
      )}

      {sessions.length === 0 && !loading && (
        <div className="text-center py-12 text-gray-400">
          <p className="text-sm">{t('measurements.noSessions')}</p>
        </div>
      )}
    </div>
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
      <button onClick={onClose} className="ml-4 font-bold opacity-60 hover:opacity-100">×</button>
    </div>
  );
}

function Spinner() {
  return (
    <div className="flex items-center justify-center min-h-[40vh]">
      <div className="w-8 h-8 border-4 border-[#F0EDE8] border-t-[#D95D39] rounded-full animate-spin" />
    </div>
  );
}
