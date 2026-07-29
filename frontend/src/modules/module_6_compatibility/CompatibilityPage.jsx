import { useEffect, useState } from 'react';
import { listSessions, listAdjustments, getAdjustment } from '../../api/modules';

const VERDICT_CONFIG = {
  compatible: {
    label: 'Compatible ✓',
    color: 'bg-[#4E6E58]/10 text-[#4E6E58] border-[#4E6E58]/20',
    gauge: '#4E6E58',
    pct: 95,
  },
  partially_compatible: {
    label: 'Partiellement compatible',
    color: 'bg-amber-50 text-amber-700 border-amber-200',
    gauge: '#D97706',
    pct: 55,
  },
  incompatible: {
    label: 'Incompatible ✗',
    color: 'bg-red-50 text-red-700 border-red-200',
    gauge: '#EF4444',
    pct: 20,
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
    setSessionId(id); setAdjId(''); setResult(null); setAdjustments([]);
    if (!id) return;
    setAdjLoading(true);
    try {
      const res = await listAdjustments(id);
      setAdjustments(res.data.adjustments || []);
    } catch { setError('Impossible de charger les ajustements.'); }
    finally { setAdjLoading(false); }
  };

  const handleCheck = async () => {
    if (!adjId) { setError('Sélectionnez un ajustement.'); return; }
    setChecking(true); setError(''); setResult(null);
    try {
      const res = await getAdjustment(adjId);
      setResult(res.data);
    } catch (err) {
      setError(err?.response?.data?.detail?.message || 'Erreur lors de la vérification.');
    } finally { setChecking(false); }
  };

  if (loading) return <Spinner />;

  return (
    <div className="min-h-screen bg-[#FAF8F5] px-4 py-6">
      <div className="space-y-4 max-w-lg mx-auto">
        <div>
          <h1 className="text-lg font-bold text-gray-900">Compatibilité</h1>
          <p className="text-xs text-gray-400 mt-0.5">Vérifiez la compatibilité tissu / patron / morphologie.</p>
        </div>

        {error && (
          <div className="flex items-center justify-between rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>{error}</span>
            <button onClick={() => setError('')} className="ml-4 font-bold text-red-400">×</button>
          </div>
        )}

        <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">Sélection</h2>

          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1.5">Session de mesures</label>
            {sessions.length === 0 ? (
              <div className="rounded-xl bg-amber-50 border border-amber-100 px-3 py-2.5 text-xs text-amber-700">
                Aucune session validée. Complétez les modules 2 et 5 d&apos;abord.
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
                    Session du {new Date(s.created_at).toLocaleDateString('fr-FR')}
                  </option>
                ))}
              </select>
            )}
          </div>

          {sessionId && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">Ajustement (tissu)</label>
              {adjLoading ? (
                <p className="text-xs text-gray-400 py-2">Chargement…</p>
              ) : adjustments.length === 0 ? (
                <div className="rounded-xl bg-amber-50 border border-amber-100 px-3 py-2.5 text-xs text-amber-700">
                  Aucun ajustement. Calculez les marges d&apos;aisance d&apos;abord.
                </div>
              ) : (
                <select
                  value={adjId}
                  onChange={(e) => setAdjId(e.target.value)}
                  className="w-full rounded-xl border border-[#E8E4DF] px-4 py-3 text-sm bg-white focus:outline-none focus:border-[#D95D39]"
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
            className="w-full rounded-2xl py-3.5 text-sm font-bold text-white disabled:opacity-50 flex items-center justify-center gap-2"
            style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
          >
            {checking ? 'Vérification…' : <>Voir la compatibilité <span>→</span></>}
          </button>
        </div>

        {result && <CompatibilityResult adj={result} />}
      </div>
    </div>
  );
}

function CompatibilityResult({ adj }) {
  const zones = adj.bust && adj.waist && adj.hips ? [
    { name: 'Poitrine', ease: adj.bust.ease_cm,  raw: adj.bust.raw_cm,  val: adj.bust.adjusted_cm },
    { name: 'Taille',   ease: adj.waist.ease_cm, raw: adj.waist.raw_cm, val: adj.waist.adjusted_cm },
    { name: 'Hanches',  ease: adj.hips.ease_cm,  raw: adj.hips.raw_cm,  val: adj.hips.adjusted_cm },
  ] : [];

  const hasNegEase  = zones.some((z) => z.ease < 0);
  const hasLowEase  = zones.some((z) => z.ease < 2 && z.ease >= 0);
  const verdict     = hasNegEase ? 'incompatible' : hasLowEase ? 'partially_compatible' : 'compatible';
  const cfg         = VERDICT_CONFIG[verdict];

  return (
    <div className="space-y-4">
      {/* Compatibility gauge card */}
      <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5 text-center">
        <p className="text-xs text-gray-400 mb-1">Compatibilité</p>
        <p className="text-xs text-gray-500 mb-4">{adj.fabric_name}</p>
        <div className="relative w-32 h-32 mx-auto mb-3">
          <svg className="w-32 h-32 -rotate-90" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="42" fill="none" stroke="#F0EDE8" strokeWidth="10" />
            <circle cx="50" cy="50" r="42" fill="none" stroke={cfg.gauge} strokeWidth="10"
              strokeDasharray={`${cfg.pct * 2.64} 264`} strokeLinecap="round" />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-3xl font-extrabold text-gray-900">{cfg.pct}%</span>
          </div>
        </div>
        <p className="text-sm font-bold" style={{ color: cfg.gauge }}>
          {verdict === 'compatible' ? 'Excellent choix !' : cfg.label}
        </p>
      </div>

      {/* Zone breakdown */}
      <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5 space-y-3">
        {zones.map((z) => {
          const ok  = z.ease >= 2;
          const low = z.ease < 2 && z.ease >= 0;
          const neg = z.ease < 0;
          const iconColor = ok ? '#4E6E58' : low ? '#D97706' : '#EF4444';
          const labels = {
            Poitrine: 'Harmonie des matières',
            Taille:   'Confort & aisance',
            Hanches:  'Retombée du tissu',
          };
          const descs = {
            Poitrine: ok ? 'Excellente'              : low ? 'Vérifier'           : 'Problème détecté',
            Taille:   ok ? 'Optimisé automatiquement' : low ? 'Ajustement requis'  : 'Ajustement critique',
            Hanches:  ok ? 'Parfait pour ce modèle'  : low ? 'Vérifier'           : 'Incompatible',
          };
          return (
            <div key={z.name} className="flex items-center justify-between py-2 border-b border-[#F0EDE8] last:border-0">
              <div className="flex items-center gap-2">
                <span
                  className="w-5 h-5 rounded-full flex items-center justify-center text-white text-xs shrink-0"
                  style={{ background: iconColor }}
                >
                  {ok ? '✓' : low ? '~' : '✕'}
                </span>
                <div>
                  <p className="text-sm font-medium text-gray-800">{labels[z.name] ?? z.name}</p>
                  <p className="text-xs text-gray-400">{z.raw}+{z.ease} cm</p>
                </div>
              </div>
              <span className="text-xs font-semibold" style={{ color: iconColor }}>
                {descs[z.name]}
              </span>
            </div>
          );
        })}
      </div>

      {adj.data_integrity_warning && (
        <div className="rounded-2xl bg-amber-50 border border-amber-100 px-4 py-3 text-xs text-amber-700">
          ⚠️ La session source n&apos;est plus en état de succès.
        </div>
      )}

      <button
        className="w-full rounded-2xl py-3.5 text-sm font-bold text-white"
        style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
      >
        Continuer vers le récapitulatif →
      </button>
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
