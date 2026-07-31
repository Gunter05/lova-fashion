import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useLanguage } from '../../context/LanguageContext';
import { listMyReports, getReport } from '../../api/modules';

const VERDICT_CONFIG = {
  compatible: {
    badge: 'bg-[#4E6E58]/10 text-[#4E6E58] border-[#4E6E58]/20',
    icon: '✓',
    pct: 95,
  },
  partially_compatible: {
    badge: 'bg-amber-50 text-amber-700 border-amber-200',
    icon: '~',
    pct: 60,
  },
  incompatible: {
    badge: 'bg-red-50 text-red-700 border-red-200',
    icon: '✕',
    pct: 20,
  },
};

export default function ReportPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const printRef = useRef(null);
  const { t, locale } = useLanguage();

  const [reports,    setReports]    = useState([]);
  const [selected,   setSelected]   = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [detLoading, setDetLoading] = useState(false);
  const [error,      setError]      = useState('');

  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const res = await listMyReports();
        setReports(res.data.reports || []);
      } catch (err) {
        if (err?.response?.status === 403) {
          setError(t('report.onlyClientsError'));
        } else {
          setError(t('report.unableLoadReports'));
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [user, t]);

  const openReport = async (summary) => {
    setSelected(null);
    setDetLoading(true);
    try {
      const res = await getReport(summary.report_id);
      setSelected(res.data);
    } catch {
      setError(t('report.unableLoadReportDetail'));
    } finally {
      setDetLoading(false);
    }
  };

  const handlePrint = () => window.print();

  if (loading) return <Spinner />;

  return (
    <div className="space-y-5 max-w-lg mx-auto">
      {/* Hero banner */}
      <div
        className="rounded-3xl p-6 text-white relative overflow-hidden"
        style={{ background: 'linear-gradient(135deg, #2C1810 0%, #D95D39 100%)' }}
      >
        <p className="text-xs font-semibold tracking-widest uppercase text-white/60 mb-1">{t('report.bannerSubtitle')}</p>
        <h1 className="text-2xl font-extrabold leading-tight">
          {t('report.bannerTitle')}<br />
          <span className="text-white/80">{t('report.bannerTitleStyled')}</span>
        </h1>
        <p className="text-sm text-white/60 mt-2">{t('report.bannerDesc')}</p>
        <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-white/10" />
      </div>

      {error && <Alert message={error} onClose={() => setError('')} />}

      {reports.length === 0 && !loading ? (
        <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] px-8 py-12 text-center space-y-4">
          <div className="w-16 h-16 mx-auto rounded-full bg-[#FAF8F5] border-2 border-[#E8E4DF] flex items-center justify-center">
            <svg className="w-7 h-7 text-[#D95D39]" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z" />
            </svg>
          </div>
          <p className="text-sm font-semibold text-gray-700">{t('report.noReportTitle')}</p>
          <p className="text-xs text-gray-400">{t('report.noReportDesc')}</p>
          {/* Guide pas-à-pas pour orienter l'utilisateur */}
          <div className="text-left space-y-2 mt-2">
            {[
              { step: '1', label: t('report.guide.measurements'), path: '/modules/2' },
              { step: '2', label: t('report.guide.catalog'), path: '/modules/3' },
              { step: '3', label: t('report.guide.ease'), path: '/modules/5' },
              { step: '4', label: t('report.guide.compat'), path: '/modules/6' },
            ].map(({ step, label, path }) => (
              <button
                key={step}
                onClick={() => navigate(path)}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-[#F0EDE8] bg-[#FDFBF7] hover:border-[#D95D39]/30 hover:bg-[#D95D39]/3 transition text-left"
              >
                <span className="w-6 h-6 rounded-full bg-[#D95D39]/10 text-[#D95D39] text-xs font-bold flex items-center justify-center shrink-0">{step}</span>
                <span className="text-sm text-gray-700 font-medium">{label}</span>
                <span className="ml-auto text-gray-300">›</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {reports.map((r) => {
            const cfg = VERDICT_CONFIG[r.verdict] ?? { badge: 'bg-gray-100 text-gray-600', icon: '•', pct: 0 };
            return (
              <button
                key={r.report_id}
                onClick={() => openReport(r)}
                className="w-full bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5 text-left hover:shadow-md hover:border-[#D95D39]/30 transition"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${cfg.badge}`}>
                    {cfg.icon} {t(`compatibility.verdicts.${r.verdict}`)}
                  </span>
                  <span className="text-xs text-gray-400">
                    {new Date(r.generated_at).toLocaleDateString(locale === 'en' ? 'en-US' : 'fr-FR', { dateStyle: 'medium' })}
                  </span>
                </div>
                <p className="text-sm font-semibold text-gray-900">{t('report.reportCode', { code: r.report_id.slice(0, 8) })}</p>
                {r.advice && <p className="text-xs text-gray-400 mt-1 line-clamp-2">{r.advice}</p>}
              </button>
            );
          })}
        </div>
      )}

      {(selected || detLoading) && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
          <div className="bg-white rounded-t-3xl sm:rounded-2xl w-full sm:max-w-lg max-h-[92vh] overflow-y-auto">
            {detLoading ? (
              <div className="flex items-center justify-center py-20"><Spinner /></div>
            ) : selected ? (
              <ReportDetail report={selected} onClose={() => setSelected(null)} onPrint={handlePrint} printRef={printRef} t={t} />
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

function ReportDetail({ report, onClose, onPrint, printRef, t }) {
  const cfg = VERDICT_CONFIG[report.verdict] ?? { badge: 'bg-gray-100 text-gray-600', icon: '•', pct: 50 };
  const m = report.adjusted_measurements;

  return (
    <div ref={printRef} className="p-5 space-y-5">
      <div className="flex items-center justify-between print:hidden">
        <div className="w-10 h-1 rounded-full bg-gray-300 mx-auto" />
      </div>
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-900">{t('report.summary')}</h2>
        <div className="flex gap-2">
          <button onClick={onPrint} className="px-3 py-1.5 rounded-xl border border-gray-200 text-xs text-gray-500 hover:bg-gray-50">🖨</button>
          <button onClick={onClose} className="px-3 py-1.5 rounded-xl bg-gray-100 text-xs text-gray-700 hover:bg-gray-200">{t('common.close')}</button>
        </div>
      </div>

      <p className="text-xs text-gray-400">{t('report.customOutfit')}</p>

      {/* Verdict gauge */}
      <div className="bg-[#FAF8F5] rounded-2xl p-5 text-center">
        <div className="relative w-28 h-28 mx-auto mb-3">
          <svg className="w-28 h-28 -rotate-90" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="42" fill="none" stroke="#E8E4DF" strokeWidth="10" />
            <circle cx="50" cy="50" r="42" fill="none" stroke="#4E6E58" strokeWidth="10"
              strokeDasharray={`${cfg.pct * 2.64} 264`} strokeLinecap="round" />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-extrabold text-gray-900">{cfg.pct}%</span>
          </div>
        </div>
        <p className="text-sm font-semibold text-[#4E6E58]">{t(`compatibility.verdicts.${report.verdict}`)} !</p>
      </div>

      {report.advice && (
        <div className="bg-[#4E6E58]/5 border border-[#4E6E58]/15 rounded-2xl px-4 py-3">
          <p className="text-sm text-[#3A5242]">{report.advice}</p>
        </div>
      )}

      {m && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-700">{t('report.adjustedMeasurements')}</h3>
          <div className="grid grid-cols-2 gap-2">
            {[
              [t('report.chest'), m.adjusted_bust_cm, 'cm'],
              [t('report.waist'),   m.adjusted_waist_cm, 'cm'],
              [t('report.hips'),  m.adjusted_hips_cm, 'cm'],
              [t('report.elasticity'),       m.elasticity_category, ''],
            ].map(([label, val, unit]) => (
              <div key={label} className="bg-[#FAF8F5] rounded-xl p-3">
                <p className="text-xs text-gray-400">{label}</p>
                <p className="text-base font-bold text-gray-900 mt-0.5">{val ?? '—'}<span className="text-xs font-normal text-gray-400"> {unit}</span></p>
              </div>
            ))}
          </div>
        </div>
      )}

      {report.incompatible_zones?.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-gray-700">{t('compatibility.watchZones')}</h3>
          {report.incompatible_zones.map((z, i) => (
            <div key={i} className="flex gap-3 rounded-xl border border-red-100 bg-red-50 px-4 py-3">
              <span className="text-red-400 mt-0.5">⚠</span>
              <div>
                <p className="text-sm font-medium text-gray-800">{z.zone_name}</p>
                {z.reason && <p className="text-xs text-gray-400 mt-0.5">{z.reason}</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      {report.display_hints && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-gray-700">{t('report.recommendations')}</h3>
          {Object.entries(report.display_hints).map(([key, val]) => (
            <div key={key} className="flex gap-2 text-sm">
              <span className="text-[#D95D39]">›</span>
              <span className="text-gray-700"><strong className="text-gray-900">{key}:</strong> {String(val)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="text-xs text-gray-400 space-y-0.5 pt-2 border-t border-[#F0EDE8]">
        <p>{t('report.fabricId')} {report.fabric_id}</p>
        <p>{t('report.patternId')} {report.model_id ?? '—'}</p>
        <p>{t('report.adjustmentId')} {report.adjustment_id}</p>
      </div>

      <button
        onClick={onClose}
        className="w-full rounded-2xl py-3.5 text-sm font-bold text-white"
        style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
      >
        {t('report.sendBtn')}
      </button>
    </div>
  );
}

function Alert({ message, onClose }) {
  return (
    <div className="flex items-center justify-between rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
      <span>{message}</span>
      <button onClick={onClose} className="ml-4 font-bold text-red-400">×</button>
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
