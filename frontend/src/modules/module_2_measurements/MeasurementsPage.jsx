import { useEffect, useState } from 'react';
import {
  createSession, listSessions, getSessionStatus,
  setStature, triggerProcess,
} from '../../api/modules';

const STATUS_CONFIG = {
  empty:      { label: 'Vide',          color: 'bg-gray-100 text-gray-500',      dot: 'bg-gray-400' },
  processing: { label: 'En traitement', color: 'bg-blue-50 text-blue-600',       dot: 'bg-blue-500' },
  success:    { label: 'Succès',        color: 'bg-[#4E6E58]/10 text-[#4E6E58]', dot: 'bg-[#4E6E58]' },
  failed:     { label: 'Échoué',        color: 'bg-red-50 text-red-600',         dot: 'bg-red-500' },
};

export default function MeasurementsPage() {
  const [sessions,   setSessions]   = useState([]);
  const [selected,   setSelected]   = useState(null);
  const [stature,    setStatureVal] = useState('');
  const [loading,    setLoading]    = useState(true);
  const [creating,   setCreating]   = useState(false);
  const [processing, setProcessing] = useState(false);
  const [polling,    setPolling]    = useState(false);
  const [error,      setError]      = useState('');
  const [success,    setSuccess]    = useState('');

  useEffect(() => { loadSessions(); }, []);

  const loadSessions = async () => {
    setLoading(true);
    try {
      const res = await listSessions();
      setSessions(res.data.sessions || []);
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

  const handleCreate = async () => {
    setCreating(true); setError('');
    try {
      const res = await createSession();
      await loadSessions();
      await loadStatus(res.data.session_id);
      setSuccess('Nouvelle session créée.');
    } catch { setError('Échec de la création de la session.'); }
    finally { setCreating(false); }
  };

  const handleProcess = async () => {
    if (!selected?.session_id) return;
    const st = parseFloat(stature);
    if (!stature || isNaN(st) || st < 100 || st > 250) {
      setError('Veuillez saisir une stature valide (100–250 cm).'); return;
    }
    setProcessing(true); setError('');
    try {
      await setStature(selected.session_id, st);
      await triggerProcess(selected.session_id);
      setSuccess('Traitement lancé.');
      pollStatus(selected.session_id);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((d) => d.msg).join(', ') : detail?.message || 'Échec du lancement.');
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

  if (loading) return <Spinner />;
  const m = selected?.measurements;

  return (
    <div className="space-y-5 max-w-lg mx-auto">
      {/* Steps banner */}
      <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5">
        <h1 className="text-lg font-bold text-gray-900 mb-1">Mon Atelier de mesures</h1>
        <p className="text-xs text-gray-400 mb-4">Pour des mesures précises, suivez ces 3 conseils.</p>
        <div className="space-y-3">
          {[
            { icon: '🧍', title: 'Tenez-vous droit', desc: 'Gardez le dos droit et les épaules relâchées.' },
            { icon: '👕', title: 'Portez des vêtements près du corps', desc: 'Évitez les vêtements amples ou épais.' },
            { icon: '📱', title: "Posez le téléphone au niveau de la taille', desc: 'Demandez à quelqu'un de vous aider. " },
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
          {creating ? '…' : <>Commencer <span>→</span></>}
        </button>
      </div>

      {error   && <Toast type="error"   message={error}   onClose={() => setError('')} />}
      {success && <Toast type="success" message={success} onClose={() => setSuccess('')} />}

      {sessions.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Sessions de capture</h2>
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
                      {new Date(s.created_at).toLocaleDateString('fr-FR')}
                      {s.is_active && <span className="ml-2 text-xs text-[#D95D39]">(active)</span>}
                    </span>
                  </div>
                  <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${cfg.color}`}>{cfg.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {selected && (
        <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700">Détail de la session</h2>
            {polling && (
              <span className="flex items-center gap-1.5 text-xs text-blue-500">
                <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                Analyse en cours…
              </span>
            )}
          </div>

          {(selected.status === 'empty' || selected.status === 'failed') && (
            <div className="space-y-3">
              <p className="text-xs text-gray-500">Téléversez vos deux photos (face &amp; profil), puis renseignez votre stature.</p>
              {selected.status === 'failed' && selected.failure_reason && (
                <p className="text-xs text-red-600 bg-red-50 rounded-xl px-3 py-2">
                  Motif d'échec : {selected.failure_reason}
                </p>
              )}
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-600 mb-1">Stature (cm)</label>
                  <input
                    type="number"
                    min={100}
                    max={250}
                    value={stature}
                    onChange={(e) => setStatureVal(e.target.value)}
                    placeholder="Ex: 170"
                    className="w-full rounded-xl border border-[#E8E4DF] px-4 py-3 text-sm focus:outline-none focus:border-[#D95D39] bg-white"
                  />
                </div>
                <button
                  onClick={handleProcess}
                  disabled={processing || polling}
                  className="px-5 py-3 rounded-xl text-sm font-semibold text-white disabled:opacity-50"
                  style={{ background: '#D95D39' }}
                >
                  {processing ? '…' : 'Lancer'}
                </button>
              </div>
            </div>
          )}

          {selected.status === 'success' && m && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <span className="w-5 h-5 rounded-full bg-[#4E6E58] flex items-center justify-center text-white text-xs">✓</span>
                <p className="text-sm font-semibold text-[#4E6E58]">Vos mesures estimées</p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {[
                  ['Tour de poitrine', m.tour_poitrine_cm],
                  ['Tour de taille',   m.tour_taille_cm],
                  ['Tour de hanches',  m.tour_hanches_cm],
                  ['Longueur de bras', m.longueur_bras_cm],
                  ['Stature',          m.hauteur_cm],
                ].map(([label, val]) => (
                  <div key={label} className="bg-[#FAF8F5] rounded-xl p-3 flex items-center justify-between">
                    <p className="text-xs text-gray-400">{label}</p>
                    <p className="text-sm font-bold text-gray-900">
                      {val ?? '—'} <span className="text-xs font-normal text-gray-400">cm</span>
                    </p>
                  </div>
                ))}
              </div>
              <button
                className="w-full mt-4 rounded-2xl py-3.5 text-sm font-bold text-white"
                style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
              >
                Continuer →
              </button>
            </div>
          )}
        </div>
      )}

      {sessions.length === 0 && !loading && (
        <div className="text-center py-12 text-gray-400">
          <p className="text-sm">Aucune session. Appuyez sur "Commencer" pour débuter.</p>
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
