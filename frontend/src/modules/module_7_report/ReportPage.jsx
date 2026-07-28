import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { listMyReports, getReport } from '../../api/modules';

const VERDICT_CONFIG = {
  compatible: {
    label: 'Compatible',
    badge: 'bg-green-100 text-green-800 border-green-200',
    icon: '✅',
  },
  partially_compatible: {
    label: 'Partiellement compatible',
    badge: 'bg-amber-100 text-amber-800 border-amber-200',
    icon: '⚠️',
  },
  incompatible: {
    label: 'Incompatible',
    badge: 'bg-red-100 text-red-800 border-red-200',
    icon: '❌',
  },
};

export default function ReportPage() {
  const { user } = useAuth();
  const printRef = useRef(null);

  const [reports,  setReports]  = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [detLoading, setDetLoading] = useState(false);
  const [error,    setError]    = useState('');

  useEffect(() => {
    if (!user?.cni) return;
    (async () => {
      try {
        const res = await listMyReports();
        setReports(res.data.reports || []);
      } catch (err) {
        if (err?.response?.status === 403) {
          setError('Seuls les clients peuvent consulter leurs rapports ici.');
        } else {
          setError('Impossible de charger les rapports.');
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [user]);

  const openReport = async (summary) => {
    setSelected(null);
    setDetLoading(true);
    try {
      const res = await getReport(summary.report_id);
      setSelected(res.data);
    } catch {
      setError('Impossible de charger le rapport.');
    } finally {
      setDetLoading(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  if (loading) return <Spinner />;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Rapport Final</h1>
        <p className="text-sm text-gray-500 mt-0.5">Synthèse complète : mesures · tissu · patron · compatibilité.</p>
      </div>

      {error && <Alert message={error} onClose={() => setError('')} />}

      {/* Report list */}
      {reports.length === 0 && !loading ? (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 px-10 py-14 text-center space-y-3">
          <div className="w-16 h-16 mx-auto rounded-full bg-rose-50 border-2 border-rose-200 flex items-center justify-center">
            <span className="text-2xl font-extrabold text-rose-400">7</span>
          </div>
          <p className="text-sm text-gray-500">Aucun rapport généré pour le moment.</p>
          <p className="text-xs text-gray-400">Complétez les modules 1 à 6 pour générer votre premier rapport automatiquement.</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-4">
          {reports.map((r) => {
            const cfg = VERDICT_CONFIG[r.verdict] ?? { label: r.verdict, badge: 'bg-gray-100 text-gray-600', icon: '📄' };
            return (
              <button
                key={r.report_id}
                onClick={() => openReport(r)}
                className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 text-left hover:shadow-md hover:border-rose-200 transition flex flex-col gap-2"
              >
                <div className="flex items-center justify-between">
                  <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full border ${cfg.badge}`}>
                    {cfg.icon} {cfg.label}
                  </span>
                  <span className="text-xs text-gray-400">
                    {new Date(r.generated_at).toLocaleDateString('fr-FR', { dateStyle: 'medium' })}
                  </span>
                </div>
                <p className="text-sm font-semibold text-gray-900">Rapport #{r.report_id.slice(0, 8)}…</p>
                {r.advice && (
                  <p className="text-xs text-gray-500 line-clamp-2">{r.advice}</p>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Detail modal */}
      {(selected || detLoading) && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            {detLoading ? (
              <div className="flex items-center justify-center py-20">
                <div className="w-8 h-8 border-4 border-gray-200 border-t-rose-500 rounded-full animate-spin" />
              </div>
            ) : selected ? (
              <ReportDetail
                report={selected}
                onClose={() => setSelected(null)}
                onPrint={handlePrint}
                printRef={printRef}
              />
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

function ReportDetail({ report, onClose, onPrint, printRef }) {
  const cfg = VERDICT_CONFIG[report.verdict] ?? { label: report.verdict, badge: 'bg-gray-100 text-gray-600', icon: '📄' };
  const m = report.adjusted_measurements;

  return (
    <div ref={printRef} className="p-6 space-y-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between print:hidden">
        <h2 className="text-lg font-bold text-gray-900">Rapport de confection</h2>
        <div className="flex gap-2">
          <button
            onClick={onPrint}
            className="px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-700 hover:bg-gray-50 transition"
          >
            🖨 Imprimer
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-gray-900 text-white text-sm hover:bg-gray-700 transition"
          >
            Fermer
          </button>
        </div>
      </div>

      {/* Report header */}
      <div className="border border-gray-100 rounded-xl p-4 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-500">Rapport #{report.report_id.slice(0, 8)}…</p>
          <p className="text-sm text-gray-500">
            {new Date(report.generated_at).toLocaleDateString('fr-FR', { dateStyle: 'long' })}
          </p>
        </div>
        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-sm font-semibold ${cfg.badge}`}>
          <span>{cfg.icon}</span>
          <span>{cfg.label}</span>
        </div>
        {report.advice && (
          <p className="text-sm text-gray-700 pt-1">{report.advice}</p>
        )}
      </div>

      {/* Adjusted measurements */}
      {m && (
        <Section title="Mesures ajustées">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {[
              ['Poitrine',     m.adjusted_bust_cm],
              ['Taille',       m.adjusted_waist_cm],
              ['Hanches',      m.adjusted_hips_cm],
              ['Élasticité',   m.elasticity_category],
              ['Source règles', m.ease_source],
            ].map(([label, val]) => (
              <div key={label} className="bg-gray-50 rounded-xl p-3 text-center">
                <p className="text-xs text-gray-400">{label}</p>
                <p className="text-base font-bold text-gray-900 mt-0.5">{val ?? '—'}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Incompatible zones */}
      {report.incompatible_zones?.length > 0 && (
        <Section title="Zones incompatibles">
          <div className="space-y-2">
            {report.incompatible_zones.map((z, i) => (
              <div key={i} className="flex items-start gap-3 rounded-xl border border-red-100 bg-red-50 px-4 py-3">
                <span className="text-red-500">⚠</span>
                <div className="text-sm">
                  <p className="font-medium text-gray-800">{z.zone_name}</p>
                  {z.reason && <p className="text-xs text-gray-500 mt-0.5">{z.reason}</p>}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Display hints */}
      {report.display_hints && (
        <Section title="Recommandations">
          <div className="space-y-2">
            {Object.entries(report.display_hints).map(([key, val]) => (
              <div key={key} className="flex gap-2 text-sm">
                <span className="text-gray-400">›</span>
                <span className="text-gray-700"><strong className="text-gray-900">{key}:</strong> {String(val)}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* IDs reference */}
      <div className="text-xs text-gray-400 space-y-0.5 pt-2 border-t border-gray-100">
        <p>Tissu ID : {report.fabric_id}</p>
        <p>Patron ID : {report.model_id ?? '—'}</p>
        <p>Ajustement ID : {report.adjustment_id}</p>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-3">{title}</h3>
      {children}
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
