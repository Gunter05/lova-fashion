import { useEffect, useState } from 'react';
import { listSessions, listAdjustments, getAdjustment } from '../../api/modules';

const VERDICT_CONFIG = {
  compatible: {
    label: 'Compatible ✓',
    color: 'bg-green-100 text-green-800 border-green-200',
    icon: '✅',
  },
  partially_compatible: {
    label: 'Partiellement compatible',
    color: 'bg-amber-100 text-amber-800 border-amber-200',
    icon: '⚠️',
  },
  incompatible: {
    label: 'Incompatible ✗',
    color: 'bg-red-100 text-red-800 border-red-200',
    icon: '❌',
  },
};

export default function CompatibilityPage() {
  const [sessions,    setSessions]    = useState([]);
  const [adjustments, setAdjustments] = useState([]);
  const [sessionId,   setSessionId]   = useState('');
  const [adjId,       setAdjId]       = useState('');
  const [result,      setResult]      = useState(null);
  const [loading,     setLoading]     = useState(true);
  const [checking,    setChecking]    = useState(false);
  const [adjLoading,  setAdjLoading]  = useState(false);
  const [error,       setError]       = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await listSessions();
        setSessions(res.data.sessions?.filter((s) => s.status === 'success') || []);
      } catch {
        setError('Impossible de charger les sessions.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleSessionChange = async (id) => {
    setSessionId(id);
    setAdjId('');
    setResult(null);
    setAdjustments([]);
    if (!id) return;
    setAdjLoading(true);
    try {
      const res = await listAdjustments(id);
      setAdjustments(res.data.adjustments || []);
    } catch {
      setError('Impossible de charger les ajustements.');
    } finally {
      setAdjLoading(false);
    }
  };

  const handleCheck = async () => {
    if (!adjId) { setError('Sélectionnez un ajustement.'); return; }
    setChecking(true);
    setError('');
    setResult(null);
    try {
      const res = await getAdjustment(adjId);
      // The adjustment itself contains the compatibility information via zones
      setResult(res.data);
    } catch (err) {
      setError(err?.response?.data?.detail?.message || 'Erreur lors de la vérification.');
    } finally {
      setChecking(false);
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Compatibilité</h1>
        <p className="text-sm text-gray-500 mt-0.5">Vérifiez la compatibilité tissu / patron / morphologie.</p>
      </div>

      {error && <Alert message={error} onClose={() => setError('')} />}

      {/* Selector */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 className="text-base font-semibold text-gray-800">Sélection</h2>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Session de mesures</label>
          {sessions.length === 0 ? (
            <p className="text-sm text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
              Aucune session validée. Complétez les modules 2 et 5 d'abord.
            </p>
          ) : (
            <select
              value={sessionId}
              onChange={(e) => handleSessionChange(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm bg-white focus:outline-none focus:border-gray-800"
            >
              <option value="">Choisir une session…</option>
              {sessions.map((s) => (
                <option key={s.session_id} value={s.session_id}>
                  Session du {new Date(s.created_at).toLocaleDateString('fr-FR')}
                </option>
              ))}
            </select>
          )}
        </div>

        {sessionId && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Ajustement (tissu)</label>
            {adjLoading ? (
              <p className="text-sm text-gray-400">Chargement…</p>
            ) : adjustments.length === 0 ? (
              <p className="text-sm text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
                Aucun ajustement pour cette session. Calculez les marges d'aisance d'abord.
              </p>
            ) : (
              <select
                value={adjId}
                onChange={(e) => setAdjId(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm bg-white focus:outline-none focus:border-gray-800"
              >
                <option value="">Choisir un ajustement…</option>
                {adjustments.map((a) => (
                  <option key={a.adjustment_id} value={a.adjustment_id}>
                    {a.fabric_name} — {a.elasticity_category}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        <button
          onClick={handleCheck}
          disabled={checking || !adjId}
          className="px-5 py-2.5 rounded-lg bg-gray-900 text-white text-sm font-semibold hover:bg-gray-700 disabled:opacity-50 transition"
        >
          {checking ? 'Vérification…' : 'Vérifier la compatibilité'}
        </button>
      </div>

      {/* Result */}
      {result && <CompatibilityResult adj={result} />}
    </div>
  );
}

function CompatibilityResult({ adj }) {
  // The adjustment endpoint returns zone-level data we can use to show compatibility
  const zones = adj.bust && adj.waist && adj.hips ? [
    { name: 'Poitrine', ease: adj.bust.ease_cm,  raw: adj.bust.raw_cm,  adj: adj.bust.adjusted_cm },
    { name: 'Taille',   ease: adj.waist.ease_cm, raw: adj.waist.raw_cm, adj: adj.waist.adjusted_cm },
    { name: 'Hanches',  ease: adj.hips.ease_cm,  raw: adj.hips.raw_cm,  adj: adj.hips.adjusted_cm },
  ] : [];

  // Simple compatibility inference from ease values
  const hasNegEase = zones.some((z) => z.ease < 0);
  const hasLowEase = zones.some((z) => z.ease < 2 && z.ease >= 0);
  const verdict = hasNegEase ? 'incompatible' : hasLowEase ? 'partially_compatible' : 'compatible';
  const cfg = VERDICT_CONFIG[verdict];

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-5">
      {/* Verdict banner */}
      <div className={`flex items-center gap-3 rounded-xl border px-4 py-3 ${cfg.color}`}>
        <span className="text-xl">{cfg.icon}</span>
        <div>
          <p className="font-semibold text-sm">{cfg.label}</p>
          <p className="text-xs opacity-75">
            Tissu : {adj.fabric_name} · Élasticité : {adj.elasticity_category}
          </p>
        </div>
      </div>

      {/* Advice */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Analyse par zone</h3>
        <div className="space-y-3">
          {zones.map((z) => {
            const status = z.ease < 0 ? 'red' : z.ease < 2 ? 'amber' : 'green';
            const colors = {
              green: 'bg-green-50 border-green-200',
              amber: 'bg-amber-50 border-amber-200',
              red:   'bg-red-50 border-red-200',
            };
            const msg = z.ease < 0
              ? 'Aisance négative — tissu trop rigide pour cette zone'
              : z.ease < 2
              ? 'Aisance faible — vérifiez l\'élasticité du tissu'
              : 'Aisance suffisante';
            return (
              <div key={z.name} className={`rounded-xl border px-4 py-3 ${colors[status]}`}>
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-gray-800">{z.name}</p>
                  <p className="text-sm font-bold text-gray-900">{z.adj} cm</p>
                </div>
                <div className="flex items-center justify-between mt-1">
                  <p className="text-xs text-gray-500">{z.raw} brut + {z.ease} aisance</p>
                  <p className="text-xs text-gray-600">{msg}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {adj.data_integrity_warning && (
        <p className="text-xs text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
          ⚠️ Avertissement d'intégrité : la session source n'est plus en état de succès.
        </p>
      )}
    </div>
  );
}

function Alert({ message, onClose }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
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
