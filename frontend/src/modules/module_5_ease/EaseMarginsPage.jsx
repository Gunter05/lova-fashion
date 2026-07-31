import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listSessions, listFabrics, computeAdjustment, listAdjustments } from '../../api/modules';
import { useFlow } from '../../context/FlowContext';

export default function EaseMarginsPage() {
  const navigate = useNavigate();
  const { flow, setFlow } = useFlow();

  const [sessions,    setSessions]    = useState([]);
  const [fabrics,     setFabrics]     = useState([]);
  const [adjustments, setAdjustments] = useState([]);
  const [sessionId,   setSessionId]   = useState(flow.sessionId || '');
  const [fabricId,    setFabricId]    = useState(flow.fabricId  || '');
  const [computing,   setComputing]   = useState(false);
  const [loading,     setLoading]     = useState(true);
  const [adjLoading,  setAdjLoading]  = useState(false);
  const [error,       setError]       = useState('');
  const [success,     setSuccess]     = useState('');
  const [result,      setResult]      = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [sRes, fRes] = await Promise.all([listSessions(), listFabrics()]);
        const validSessions = sRes.data.sessions?.filter((s) => s.status === 'success') || [];
        setSessions(validSessions);
        setFabrics(fRes.data || []);

        // Pré-charge l'historique si la session est déjà connue
        const preSession = flow.sessionId;
        if (preSession && validSessions.some((s) => s.session_id === preSession)) {
          setSessionId(preSession);
          try {
            const aRes = await listAdjustments(preSession);
            setAdjustments(aRes.data.adjustments || []);
          } catch { /* pas encore d'ajustements */ }
        }
      } catch {
        setError('Impossible de charger les données nécessaires.');
      } finally {
        setLoading(false);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSessionChange = async (id) => {
    setSessionId(id);
    setAdjustments([]);
    if (!id) return;
    setAdjLoading(true);
    try {
      const res = await listAdjustments(id);
      setAdjustments(res.data.adjustments || []);
    } catch { /* No adjustments yet */ }
    finally { setAdjLoading(false); }
  };

  const handleCompute = async () => {
    if (!sessionId || !fabricId) { setError('Sélectionnez une session et un tissu.'); return; }
    setComputing(true); setError(''); setSuccess(''); setResult(null);
    try {
      const res = await computeAdjustment(sessionId, fabricId);
      setResult(res.data);
      // Persiste l'adjustment_id dans le parcours utilisateur
      setFlow({ adjustmentId: res.data.adjustment_id, sessionId, fabricId });
      setSuccess('Ajustement calculé avec succès.');
      const listRes = await listAdjustments(sessionId);
      setAdjustments(listRes.data.adjustments || []);
    } catch (err) {
      const d = err?.response?.data?.detail;
      setError(typeof d === 'string' ? d : d?.message || 'Erreur lors du calcul.');
    } finally { setComputing(false); }
  };

  if (loading) return <Spinner />;

  return (
    <div className="min-h-screen bg-[#FAF8F5] px-4 py-8">
      <div className="space-y-4 max-w-lg mx-auto">
        <div>
          <h1 className="text-lg font-bold text-gray-900">Marges d&apos;Aisance</h1>
          <p className="text-xs text-gray-400 mt-0.5">Calculez les ajustements selon le tissu sélectionné.</p>
        </div>

        {/* Rappel tissu sélectionné */}
        {flow.fabricName && (
          <div className="bg-[#4E6E58]/5 border border-[#4E6E58]/20 rounded-2xl px-4 py-2.5 text-xs text-[#3A5242]">
            Tissu retenu : <span className="font-semibold">{flow.fabricName}</span>
            {flow.modelName && <> · Patron : <span className="font-semibold">{flow.modelName}</span></>}
          </div>
        )}

        {error   && <Toast type="error"   message={error}   onClose={() => setError('')} />}
        {success && <Toast type="success" message={success} onClose={() => setSuccess('')} />}

        {/* Compute form */}
        <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">Nouveau calcul</h2>

          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1.5">Session de mesures</label>
            {sessions.length === 0 ? (
              <div className="rounded-xl bg-amber-50 border border-amber-100 px-3 py-2.5 text-xs text-amber-700">
                Aucune session validée.{' '}
                <button className="underline font-semibold" onClick={() => navigate('/modules/2')}>
                  Compléter les mesures
                </button>
              </div>
            ) : (
              <select
                value={sessionId}
                onChange={(e) => handleSessionChange(e.target.value)}
                className="w-full rounded-xl border border-[#E8E4DF] px-4 py-3 text-sm bg-white focus:outline-none focus:border-[#D95D39]"
              >
                <option value="">Choisir une session…</option>
                {sessions.map((s) => (
                  <option key={s.session_id} value={s.session_id}>
                    Session du {new Date(s.created_at).toLocaleDateString('fr-FR')}{s.is_active ? ' (active)' : ''}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1.5">Tissu</label>
            <select
              value={fabricId}
              onChange={(e) => setFabricId(e.target.value)}
              className="w-full rounded-xl border border-[#E8E4DF] px-4 py-3 text-sm bg-white focus:outline-none focus:border-[#D95D39]"
            >
              <option value="">Choisir un tissu…</option>
              {fabrics.map((f) => (
                <option key={f.fabric_id} value={f.fabric_id}>{f.fabric_name} — {f.category_name}</option>
              ))}
            </select>
          </div>

          <button
            onClick={handleCompute}
            disabled={computing || !sessionId || !fabricId}
            className="w-full rounded-2xl py-3.5 text-sm font-bold text-white disabled:opacity-50 flex items-center justify-center gap-2"
            style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
          >
            {computing ? 'Calcul en cours…' : <>Calculer l&apos;aisance <span>→</span></>}
          </button>
        </div>

        {result && (
          <>
            <AdjustmentCard adj={result} />
            {/* Bouton "Continuer" — fonctionnel */}
            <button
              onClick={() => navigate('/modules/6')}
              className="w-full rounded-2xl py-3.5 text-sm font-bold text-white flex items-center justify-center gap-2"
              style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
            >
              Vérifier la compatibilité →
            </button>
          </>
        )}

        {/* Si déjà un adjustmentId dans le flow, permettre de continuer sans recalculer */}
        {!result && flow.adjustmentId && (
          <div className="bg-white rounded-2xl shadow-sm border border-[#4E6E58]/20 px-4 py-3 flex items-center justify-between">
            <p className="text-xs text-[#3A5242]">Ajustement déjà calculé.</p>
            <button
              onClick={() => navigate('/modules/6')}
              className="px-3 py-1.5 rounded-xl text-xs font-bold text-white"
              style={{ background: '#D95D39' }}
            >
              Compatibilité →
            </button>
          </div>
        )}

        {sessionId && (
          <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Historique des ajustements</h2>
            {adjLoading ? (
              <div className="flex justify-center py-4">
                <div className="w-6 h-6 border-4 border-[#F0EDE8] border-t-[#D95D39] rounded-full animate-spin" />
              </div>
            ) : adjustments.length === 0 ? (
              <p className="text-sm text-gray-400">Aucun ajustement pour cette session.</p>
            ) : (
              <div className="space-y-2">
                {adjustments.map((a) => (
                  <div
                    key={a.adjustment_id}
                    className={`flex items-center justify-between py-2.5 border-b border-[#F0EDE8] last:border-0 ${
                      a.adjustment_id === flow.adjustmentId ? 'bg-[#4E6E58]/5 rounded-xl px-2' : ''
                    }`}
                  >
                    <div>
                      <p className="text-sm font-medium text-gray-800">{a.fabric_name}</p>
                      <p className="text-xs text-gray-400">{a.elasticity_category} · {new Date(a.calculated_at).toLocaleDateString('fr-FR')}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <p className="text-xs text-gray-500">P:{a.adjusted_bust_cm}cm · T:{a.adjusted_waist_cm}cm · H:{a.adjusted_hips_cm}cm</p>
                      {a.adjustment_id !== flow.adjustmentId && (
                        <button
                          onClick={() => { setFlow({ adjustmentId: a.adjustment_id }); setSuccess('Ajustement sélectionné.'); }}
                          className="text-[10px] px-2 py-0.5 rounded-lg bg-[#D95D39]/10 text-[#D95D39] font-semibold"
                        >
                          Utiliser
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function AdjustmentCard({ adj }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-[#4E6E58]/20 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-800">Résultat — {adj.fabric_name}</h3>
        <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-[#4E6E58]/10 text-[#4E6E58]">{adj.elasticity_category}</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[
          { zone: 'Poitrine', raw: adj.bust?.raw_cm,  ease: adj.bust?.ease_cm,  adj: adj.bust?.adjusted_cm },
          { zone: 'Taille',   raw: adj.waist?.raw_cm, ease: adj.waist?.ease_cm, adj: adj.waist?.adjusted_cm },
          { zone: 'Hanches',  raw: adj.hips?.raw_cm,  ease: adj.hips?.ease_cm,  adj: adj.hips?.adjusted_cm },
        ].map(({ zone, raw, ease, adj: adjusted }) => (
          <div key={zone} className="bg-[#FAF8F5] rounded-xl p-3 text-center">
            <p className="text-xs text-gray-400 mb-1">{zone}</p>
            <p className="text-xl font-extrabold text-gray-900">{adjusted}<span className="text-xs font-normal text-gray-400"> cm</span></p>
            <p className="text-[10px] text-gray-400 mt-1">{raw}+{ease} aisance</p>
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-400">Source règles : {adj.ease_source}</p>
    </div>
  );
}

function Toast({ type, message, onClose }) {
  const s = { error: 'bg-red-50 border-red-100 text-red-700', success: 'bg-[#4E6E58]/5 border-[#4E6E58]/20 text-[#3A5242]' };
  return (
    <div className={`flex items-center justify-between rounded-2xl border px-4 py-3 text-sm ${s[type]}`}>
      <span>{message}</span>
      <button onClick={onClose} className="ml-4 font-bold opacity-60">×</button>
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
