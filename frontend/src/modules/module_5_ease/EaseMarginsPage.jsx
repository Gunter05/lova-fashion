import { useEffect, useState } from 'react';
import { listSessions, listFabrics, computeAdjustment, listAdjustments } from '../../api/modules';

export default function EaseMarginsPage() {
  const [sessions,     setSessions]     = useState([]);
  const [fabrics,      setFabrics]      = useState([]);
  const [adjustments,  setAdjustments]  = useState([]);
  const [sessionId,    setSessionId]    = useState('');
  const [fabricId,     setFabricId]     = useState('');
  const [computing,    setComputing]    = useState(false);
  const [loading,      setLoading]      = useState(true);
  const [adjLoading,   setAdjLoading]   = useState(false);
  const [error,        setError]        = useState('');
  const [success,      setSuccess]      = useState('');
  const [result,       setResult]       = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [sRes, fRes] = await Promise.all([listSessions(), listFabrics()]);
        setSessions(sRes.data.sessions?.filter((s) => s.status === 'success') || []);
        setFabrics(fRes.data || []);
      } catch {
        setError('Impossible de charger les données nécessaires.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Load adjustments when session changes
  const handleSessionChange = async (id) => {
    setSessionId(id);
    setAdjustments([]);
    if (!id) return;
    setAdjLoading(true);
    try {
      const res = await listAdjustments(id);
      setAdjustments(res.data.adjustments || []);
    } catch {
      // No adjustments yet — ignore
    } finally {
      setAdjLoading(false);
    }
  };

  const handleCompute = async () => {
    if (!sessionId || !fabricId) {
      setError('Sélectionnez une session et un tissu.');
      return;
    }
    setComputing(true);
    setError('');
    setSuccess('');
    setResult(null);
    try {
      const res = await computeAdjustment(sessionId, fabricId);
      setResult(res.data);
      setSuccess('Ajustement calculé avec succès.');
      // Reload adjustment list
      const listRes = await listAdjustments(sessionId);
      setAdjustments(listRes.data.adjustments || []);
    } catch (err) {
      const d = err?.response?.data?.detail;
      setError(typeof d === 'string' ? d : d?.message || 'Erreur lors du calcul.');
    } finally {
      setComputing(false);
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Marges d'Aisance</h1>
        <p className="text-sm text-gray-500 mt-0.5">Calculez les marges d'aisance selon le tissu sélectionné.</p>
      </div>

      {error   && <Alert type="error"   message={error}   onClose={() => setError('')} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess('')} />}

      {/* Compute form */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 className="text-base font-semibold text-gray-800">Nouveau calcul</h2>

        {/* Session selector */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Session de mesures (succès)</label>
          {sessions.length === 0 ? (
            <p className="text-sm text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
              Aucune session avec mesures réussies. Complétez le module 2 d'abord.
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
                  {s.is_active ? ' (active)' : ''}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Fabric selector */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Tissu</label>
          <select
            value={fabricId}
            onChange={(e) => setFabricId(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm bg-white focus:outline-none focus:border-gray-800"
          >
            <option value="">Choisir un tissu…</option>
            {fabrics.map((f) => (
              <option key={f.fabric_id} value={f.fabric_id}>
                {f.fabric_name} — {f.category_name}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={handleCompute}
          disabled={computing || !sessionId || !fabricId}
          className="px-5 py-2.5 rounded-lg bg-gray-900 text-white text-sm font-semibold hover:bg-gray-700 disabled:opacity-50 transition"
        >
          {computing ? 'Calcul en cours…' : 'Calculer l\'aisance'}
        </button>
      </div>

      {/* Result card */}
      {result && <AdjustmentCard adj={result} />}

      {/* History */}
      {sessionId && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-base font-semibold text-gray-800 mb-3">Historique des ajustements</h2>
          {adjLoading ? (
            <div className="flex justify-center py-4">
              <div className="w-6 h-6 border-4 border-gray-200 border-t-rose-500 rounded-full animate-spin" />
            </div>
          ) : adjustments.length === 0 ? (
            <p className="text-sm text-gray-400">Aucun ajustement pour cette session.</p>
          ) : (
            <div className="space-y-3">
              {adjustments.map((a) => (
                <AdjustmentSummaryRow key={a.adjustment_id} adj={a} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AdjustmentCard({ adj }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-rose-100 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-gray-800">Résultat — {adj.fabric_name}</h3>
        <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">{adj.elasticity_category}</span>
      </div>
      <div className="grid grid-cols-3 gap-4">
        {[
          { zone: 'Poitrine', raw: adj.bust?.raw_cm, ease: adj.bust?.ease_cm, adj: adj.bust?.adjusted_cm },
          { zone: 'Taille',   raw: adj.waist?.raw_cm, ease: adj.waist?.ease_cm, adj: adj.waist?.adjusted_cm },
          { zone: 'Hanches',  raw: adj.hips?.raw_cm, ease: adj.hips?.ease_cm, adj: adj.hips?.adjusted_cm },
        ].map(({ zone, raw, ease, adj: adjusted }) => (
          <div key={zone} className="bg-gray-50 rounded-xl p-4 text-center">
            <p className="text-xs text-gray-500 mb-2">{zone}</p>
            <p className="text-xl font-bold text-gray-900">{adjusted}<span className="text-xs font-normal text-gray-500"> cm</span></p>
            <p className="text-xs text-gray-400 mt-1">{raw} + {ease} aisance</p>
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-400">Source règles : {adj.ease_source}</p>
    </div>
  );
}

function AdjustmentSummaryRow({ adj }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0 text-sm">
      <div>
        <p className="font-medium text-gray-800">{adj.fabric_name}</p>
        <p className="text-xs text-gray-400">{adj.elasticity_category} · {new Date(adj.calculated_at).toLocaleDateString('fr-FR')}</p>
      </div>
      <div className="text-right text-xs text-gray-600">
        <p>P: {adj.adjusted_bust_cm}cm · T: {adj.adjusted_waist_cm}cm · H: {adj.adjusted_hips_cm}cm</p>
      </div>
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
