import { useEffect, useState } from 'react';
import {
  createSession, listSessions, getSessionStatus,
  setStature, triggerProcess,
} from '../../api/modules';

const STATUS_LABELS = {
  empty:      { label: 'Vide',        color: 'bg-gray-100 text-gray-600' },
  processing: { label: 'En traitement', color: 'bg-blue-100 text-blue-700' },
  success:    { label: 'Succès',      color: 'bg-green-100 text-green-700' },
  failed:     { label: 'Échoué',      color: 'bg-red-100 text-red-700' },
};

export default function MeasurementsPage() {
  const [sessions,  setSessions]  = useState([]);
  const [selected,  setSelected]  = useState(null);   // session status object
  const [stature,   setStatureVal] = useState('');
  const [loading,   setLoading]   = useState(true);
  const [creating,  setCreating]  = useState(false);
  const [processing, setProcessing] = useState(false);
  const [polling,   setPolling]   = useState(false);
  const [error,     setError]     = useState('');
  const [success,   setSuccess]   = useState('');

  // ── Initial load ───────────────────────────────────────────────────────────
  useEffect(() => { loadSessions(); }, []);

  const loadSessions = async () => {
    setLoading(true);
    try {
      const res = await listSessions();
      setSessions(res.data.sessions || []);
      // Auto-select the active session
      const active = (res.data.sessions || []).find((s) => s.is_active);
      if (active) await loadStatus(active.session_id);
    } catch {
      setError('Impossible de charger les sessions.');
    } finally {
      setLoading(false);
    }
  };

  const loadStatus = async (id) => {
    const res = await getSessionStatus(id);
    setSelected(res.data);
    return res.data;
  };

  // ── Create new session ─────────────────────────────────────────────────────
  const handleCreate = async () => {
    setCreating(true);
    setError('');
    try {
      const res = await createSession();
      await loadSessions();
      await loadStatus(res.data.session_id);
      setSuccess('Nouvelle session créée.');
    } catch {
      setError('Échec de la création de la session.');
    } finally {
      setCreating(false);
    }
  };

  // ── Set stature & trigger processing ──────────────────────────────────────
  const handleProcess = async () => {
    if (!selected?.session_id) return;
    const st = parseFloat(stature);
    if (!stature || isNaN(st) || st < 100 || st > 250) {
      setError('Veuillez saisir une stature valide (100–250 cm).');
      return;
    }
    setProcessing(true);
    setError('');
    try {
      await setStature(selected.session_id, st);
      await triggerProcess(selected.session_id);
      setSuccess('Traitement lancé. Résultats disponibles dans quelques secondes.');
      pollStatus(selected.session_id);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(
        Array.isArray(detail)
          ? detail.map((d) => d.msg).join(', ')
          : detail?.message || 'Échec du lancement du traitement.',
      );
    } finally {
      setProcessing(false);
    }
  };

  // ── Poll until done ────────────────────────────────────────────────────────
  const pollStatus = (id) => {
    setPolling(true);
    const iv = setInterval(async () => {
      try {
        const data = await loadStatus(id);
        if (data.status === 'success' || data.status === 'failed') {
          clearInterval(iv);
          setPolling(false);
          await loadSessions();
        }
      } catch {
        clearInterval(iv);
        setPolling(false);
      }
    }, 3000);
  };

  if (loading) return <Spinner />;

  const m = selected?.measurements;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Mesures Corporelles</h1>
          <p className="text-sm text-gray-500 mt-0.5">Capturez vos mesures via photos + stature.</p>
        </div>
        <button
          onClick={handleCreate}
          disabled={creating}
          className="px-4 py-2 rounded-lg bg-rose-500 text-white text-sm font-semibold hover:bg-rose-600 disabled:opacity-50 transition"
        >
          {creating ? '…' : '+ Nouvelle session'}
        </button>
      </div>

      {error   && <Alert type="error"   message={error}   onClose={() => setError('')} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess('')} />}

      {/* Session list */}
      {sessions.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Sessions de capture</h2>
          <div className="space-y-2">
            {sessions.map((s) => {
              const badge = STATUS_LABELS[s.status] ?? { label: s.status, color: 'bg-gray-100 text-gray-600' };
              return (
                <button
                  key={s.session_id}
                  onClick={() => loadStatus(s.session_id)}
                  className={[
                    'w-full flex items-center justify-between px-4 py-3 rounded-xl border text-left transition',
                    selected?.session_id === s.session_id
                      ? 'border-rose-300 bg-rose-50'
                      : 'border-gray-100 hover:border-gray-200',
                  ].join(' ')}
                >
                  <span className="text-sm text-gray-700 font-medium">
                    Session — {new Date(s.created_at).toLocaleDateString('fr-FR')}
                    {s.is_active && <span className="ml-2 text-xs text-rose-500">(active)</span>}
                  </span>
                  <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${badge.color}`}>
                    {badge.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Session detail */}
      {selected && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-800">Détail de la session</h2>
            {polling && (
              <span className="flex items-center gap-1.5 text-xs text-blue-600">
                <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" /> Traitement en cours…
              </span>
            )}
          </div>

          {/* Status */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <InfoRow label="Statut" value={STATUS_LABELS[selected.status]?.label ?? selected.status} />
            <InfoRow label="Créée le" value={new Date(selected.created_at).toLocaleString('fr-FR')} />
          </div>

          {/* Stature + process (only for empty/failed) */}
          {(selected.status === 'empty' || selected.status === 'failed') && (
            <div className="pt-2 border-t border-gray-100 space-y-3">
              <p className="text-sm text-gray-600">
                Téléversez vos deux photos (face & profil) via l'API, puis renseignez votre stature pour lancer l'estimation.
              </p>
              {selected.status === 'failed' && selected.failure_reason && (
                <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
                  Motif d'échec : {selected.failure_reason}
                </p>
              )}
              <div className="flex gap-3 items-end">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Stature (cm)</label>
                  <input
                    type="number"
                    min={100}
                    max={250}
                    value={stature}
                    onChange={(e) => setStatureVal(e.target.value)}
                    placeholder="Ex: 170"
                    className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:outline-none focus:border-gray-800 focus:ring-1 focus:ring-gray-800"
                  />
                </div>
                <button
                  onClick={handleProcess}
                  disabled={processing || polling}
                  className="px-5 py-2.5 rounded-lg bg-gray-900 text-white text-sm font-semibold hover:bg-gray-700 disabled:opacity-50 transition"
                >
                  {processing ? '…' : 'Lancer l\'estimation'}
                </button>
              </div>
            </div>
          )}

          {/* Results */}
          {selected.status === 'success' && m && (
            <div className="pt-2 border-t border-gray-100">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Mesures estimées</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[
                  ['Tour poitrine', m.tour_poitrine_cm, 'cm'],
                  ['Tour taille',   m.tour_taille_cm,   'cm'],
                  ['Tour hanches',  m.tour_hanches_cm,  'cm'],
                  ['Longueur bras', m.longueur_bras_cm, 'cm'],
                  ['Stature',       m.hauteur_cm,       'cm'],
                ].map(([label, val, unit]) => (
                  <div key={label} className="rounded-xl border border-gray-100 bg-gray-50 px-4 py-3 text-center">
                    <p className="text-2xl font-bold text-gray-900">{val ?? '—'}<span className="text-sm font-normal text-gray-500 ml-0.5">{unit}</span></p>
                    <p className="text-xs text-gray-500 mt-0.5">{label}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {sessions.length === 0 && !loading && (
        <div className="text-center py-16 text-gray-400">
          <p className="text-sm">Aucune session. Créez-en une pour commencer.</p>
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="text-sm font-medium text-gray-900">{value}</p>
    </div>
  );
}

function Alert({ type, message, onClose }) {
  const s = { error: 'bg-red-50 border-red-200 text-red-700', success: 'bg-green-50 border-green-200 text-green-700' };
  return (
    <div className={`flex items-center justify-between rounded-lg border px-4 py-3 text-sm ${s[type]}`}>
      <span>{message}</span>
      <button onClick={onClose} className="ml-4 font-bold">×</button>
    </div>
  );
}

function Spinner() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 border-4 border-gray-200 border-t-rose-500 rounded-full animate-spin" />
    </div>
  );
}
