import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listSessions, listAdjustments, listModels, createVerification } from '../../api/modules';
import { useFlow } from '../../context/FlowContext';
import { useLanguage } from '../../context/LanguageContext';

const VERDICT_CONFIG = {
  compatible: {
    gauge: '#4E6E58',
    pct: 95,
  },
  partially_compatible: {
    gauge: '#D97706',
    pct: 55,
  },
  incompatible: {
    gauge: '#EF4444',
    pct: 20,
  },
};

export default function CompatibilityPage() {
  const navigate = useNavigate();
  const { flow, setFlow } = useFlow();
  const { t, locale } = useLanguage();

  const [sessions,    setSessions]    = useState([]);
  const [adjustments, setAdjustments] = useState([]);
  const [models,      setModels]      = useState([]);

  // Pré-rempli depuis le FlowContext
  const [sessionId,   setSessionId]   = useState(flow.sessionId    || '');
  const [adjId,       setAdjId]       = useState(flow.adjustmentId || '');
  const [fabricId,    setFabricId]    = useState(flow.fabricId     || '');
  const [modelId,     setModelId]     = useState(flow.modelId      || '');

  const [result,      setResult]      = useState(null);
  const [loading,     setLoading]     = useState(true);
  const [checking,    setChecking]    = useState(false);
  const [adjLoading,  setAdjLoading]  = useState(false);
  const [error,       setError]       = useState('');

  useEffect(() => {
    (async () => {
      try {
        const [sRes, mRes] = await Promise.all([listSessions(), listModels()]);
        setSessions(sRes.data.sessions?.filter((s) => s.status === 'success') || []);
        setModels(mRes.data.items || []);

        // Pré-charge les ajustements si session déjà connue
        if (flow.sessionId) {
          try {
            const aRes = await listAdjustments(flow.sessionId);
            setAdjustments(aRes.data.adjustments || []);
          } catch { /* pas encore */ }
        }
      } catch {
        setError(t('compatibility.unableLoadData'));
      } finally {
        setLoading(false);
      }
    })();
  }, [t]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSessionChange = async (id) => {
    setSessionId(id); setAdjId(''); setResult(null); setAdjustments([]);
    if (!id) return;
    setAdjLoading(true);
    try {
      const res = await listAdjustments(id);
      setAdjustments(res.data.adjustments || []);
      // Pré-sélectionne l'ajustement du flow si disponible
      if (flow.adjustmentId && (res.data.adjustments || []).some((a) => a.adjustment_id === flow.adjustmentId)) {
        setAdjId(flow.adjustmentId);
        // Récupère le fabric_id depuis l'ajustement
        const a = (res.data.adjustments || []).find((a) => a.adjustment_id === flow.adjustmentId);
        if (a?.fabric_id) setFabricId(a.fabric_id);
      }
    } catch { setError('Impossible de charger les ajustements.'); }
    finally { setAdjLoading(false); }
  };

  const handleCheck = async () => {
    if (!sessionId || !adjId || !modelId) {
      setError('Sélectionnez une session, un ajustement et un patron.'); return;
    }

    // Récupère le fabric_id depuis l'ajustement sélectionné (ou le flow)
    const adj = adjustments.find((a) => a.adjustment_id === adjId);
    const usedFabricId = adj?.fabric_id || fabricId || flow.fabricId;
    if (!usedFabricId) { setError('Impossible de déterminer le tissu. Revenez au catalogue.'); return; }

    setChecking(true); setError(''); setResult(null);
    try {
      // Appel correct vers le vrai moteur de compatibilité (Module 6)
      const res = await createVerification(sessionId, usedFabricId, modelId);
      const verification = res.data;
      setResult(verification);
      // Persiste l'ID de vérification dans le parcours
      setFlow({ verificationId: verification.verification_id || verification.id });
    } catch (err) {
      const d = err?.response?.data?.detail;
      setError(typeof d === 'string' ? d : d?.message || 'Erreur lors de la vérification.');
    } finally { setChecking(false); }
  };

  if (loading) return <Spinner />;

  return (
    <div className="min-h-screen bg-[#FAF8F5] px-4 py-6">
      <div className="space-y-4 max-w-lg mx-auto">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{t('compatibility.title')}</h1>
          <p className="text-xs text-gray-400 mt-0.5">{t('compatibility.subtitle')}</p>
        </div>

        {/* Rappel sélections en cours */}
        {(flow.fabricName || flow.modelName) && (
          <div className="bg-[#4E6E58]/5 border border-[#4E6E58]/20 rounded-2xl px-4 py-2.5 text-xs text-[#3A5242] space-y-0.5">
            {flow.fabricName && <p>{t('catalog.selected.fabric')} <span className="font-semibold">{flow.fabricName}</span></p>}
            {flow.modelName  && <p>{t('catalog.selected.pattern')} <span className="font-semibold">{flow.modelName}</span></p>}
          </div>
        )}

        {error && (
          <div className="flex items-center justify-between rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>{error}</span>
            <button onClick={() => setError('')} className="ml-4 font-bold text-red-400">×</button>
          </div>
        )}

        <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">{t('compatibility.selection')}</h2>

          {/* Session */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1.5">{t('compatibility.measureSession')}</label>
            {sessions.length === 0 ? (
              <div className="rounded-xl bg-amber-50 border border-amber-100 px-3 py-2.5 text-xs text-amber-700">
                {t('compatibility.noValidatedSession')}{' '}
                <button className="underline font-semibold" onClick={() => navigate('/modules/2')}>
                  {t('compatibility.completeMeasurements')}
                </button>
              </div>
            ) : (
              <select
                value={sessionId}
                onChange={(e) => handleSessionChange(e.target.value)}
                className="w-full rounded-xl border border-[#E8E4DF] px-4 py-3 text-sm bg-white focus:outline-none focus:border-[#D95D39]"
              >
                <option value="">{t('compatibility.chooseSession')}</option>
                {sessions.map((s) => (
                  <option key={s.session_id} value={s.session_id}>
                    {locale === 'en' ? `Session of ${new Date(s.created_at).toLocaleDateString('en-US')}` : `Session du ${new Date(s.created_at).toLocaleDateString('fr-FR')}`}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Ajustement */}
          {sessionId && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">{t('compatibility.adjustmentLabel')}</label>
              {adjLoading ? (
                <p className="text-xs text-gray-400 py-2">{t('common.loading')}</p>
              ) : adjustments.length === 0 ? (
                <div className="rounded-xl bg-amber-50 border border-amber-100 px-3 py-2.5 text-xs text-amber-700">
                  {t('compatibility.noAdjustment')}{' '}
                  <button className="underline font-semibold" onClick={() => navigate('/modules/5')}>
                    {t('compatibility.calculateEaseBtn')}
                  </button>
                </div>
              ) : (
                <select
                  value={adjId}
                  onChange={(e) => {
                    setAdjId(e.target.value);
                    const a = adjustments.find((a) => a.adjustment_id === e.target.value);
                    if (a?.fabric_id) setFabricId(a.fabric_id);
                  }}
                  className="w-full rounded-xl border border-[#E8E4DF] px-4 py-3 text-sm bg-white focus:outline-none focus:border-[#D95D39]"
                >
                  <option value="">{t('compatibility.chooseAdjustment')}</option>
                  {adjustments.map((a) => (
                    <option key={a.adjustment_id} value={a.adjustment_id}>
                      {a.fabric_name} — {a.elasticity_category}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          {/* Patron */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1.5">{t('compatibility.patternLabel')}</label>
            {models.length === 0 ? (
              <div className="rounded-xl bg-amber-50 border border-amber-100 px-3 py-2.5 text-xs text-amber-700">
                {t('compatibility.noPatternAvailable')}{' '}
                <button className="underline font-semibold" onClick={() => navigate('/modules/3')}>
                  {t('compatibility.choosePatternBtn')}
                </button>
              </div>
            ) : (
              <select
                value={modelId}
                onChange={(e) => setModelId(e.target.value)}
                className="w-full rounded-xl border border-[#E8E4DF] px-4 py-3 text-sm bg-white focus:outline-none focus:border-[#D95D39]"
              >
                <option value="">{t('compatibility.choosePatternOption')}</option>
                {models.map((m) => (
                  <option key={m.model_id} value={m.model_id}>{m.model_name} — {t(`types.${m.garment_type}`)}</option>
                ))}
              </select>
            )}
          </div>

          <button
            onClick={handleCheck}
            disabled={checking || !adjId || !modelId}
            className="w-full rounded-2xl py-3.5 text-sm font-bold text-white disabled:opacity-50 flex items-center justify-center gap-2"
            style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
          >
            {checking ? t('compatibility.verifying') : <>{t('compatibility.checkBtn')} <span>→</span></>}
          </button>
        </div>

        {result && <CompatibilityResult result={result} onContinue={() => navigate('/modules/7')} t={t} />}
      </div>
    </div>
  );
}

function CompatibilityResult({ result, onContinue, t }) {
  // Le backend renvoie un verdict direct (compatible / partially_compatible / incompatible)
  const verdict = result.verdict || 'compatible';
  const cfg     = VERDICT_CONFIG[verdict] ?? VERDICT_CONFIG.compatible;

  return (
    <div className="space-y-4">
      {/* Compatibility gauge card */}
      <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5 text-center">
        <p className="text-xs text-gray-400 mb-1">{t('compatibility.gaugeLabel')}</p>
        {result.fabric_name && <p className="text-xs text-gray-500 mb-4">{result.fabric_name}</p>}
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
          {verdict === 'compatible' ? t('compatibility.verdicts.excellent') : t(`compatibility.verdicts.${verdict}`)}
        </p>
        {result.advice && (
          <p className="text-xs text-gray-400 mt-2 max-w-xs mx-auto">{result.advice}</p>
        )}
      </div>

      {/* Détail zones incompatibles */}
      {result.incompatible_zones?.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5 space-y-2">
          <h3 className="text-sm font-semibold text-gray-700">{t('compatibility.watchZones')}</h3>
          {result.incompatible_zones.map((z, i) => (
            <div key={i} className="flex gap-3 rounded-xl border border-red-100 bg-red-50 px-4 py-3">
              <span className="text-red-400 mt-0.5 shrink-0">⚠</span>
              <div>
                <p className="text-sm font-medium text-gray-800">{z.zone_name}</p>
                {z.reason && <p className="text-xs text-gray-400 mt-0.5">{z.reason}</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Bouton "Continuer" — maintenant fonctionnel */}
      <button
        onClick={onContinue}
        className="w-full rounded-2xl py-3.5 text-sm font-bold text-white flex items-center justify-center gap-2"
        style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
      >
        {t('compatibility.seeSummaryBtn')}
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
