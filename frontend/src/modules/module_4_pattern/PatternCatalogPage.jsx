import { useEffect, useState } from 'react';
import { listModels, getModel } from '../../api/modules';

const GARMENT_TYPES = ['', 'Dress', 'Shirt', 'Pants', 'Skirt', 'Jacket', 'Suit'];
const STATUS_COLORS = {
  Published: 'bg-green-100 text-green-700',
  Draft:     'bg-amber-100 text-amber-700',
  Archived:  'bg-gray-100 text-gray-500',
};

export default function PatternCatalogPage() {
  const [models,   setModels]   = useState([]);
  const [selected, setSelected] = useState(null);
  const [filter,   setFilter]   = useState('');
  const [search,   setSearch]   = useState('');
  const [loading,  setLoading]  = useState(true);
  const [detail,   setDetail]   = useState(null);
  const [detLoading, setDetLoading] = useState(false);
  const [error,    setError]    = useState('');

  useEffect(() => { loadModels(); }, []);

  const loadModels = async (garment_type) => {
    setLoading(true);
    try {
      const res = await listModels(garment_type || undefined);
      setModels(res.data.items || []);
    } catch {
      setError('Impossible de charger le catalogue des patrons.');
    } finally {
      setLoading(false);
    }
  };

  const handleFilter = (type) => {
    setFilter(type);
    loadModels(type);
  };

  const openDetail = async (model) => {
    setSelected(model);
    setDetail(null);
    setDetLoading(true);
    try {
      const res = await getModel(model.model_id);
      setDetail(res.data);
    } catch {
      setError('Impossible de charger les détails du patron.');
    } finally {
      setDetLoading(false);
    }
  };

  const visible = models.filter((m) =>
    m.model_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Catalogue Patrons</h1>
        <p className="text-sm text-gray-500 mt-0.5">Explorez les modèles de vêtements disponibles.</p>
      </div>

      {error && <Alert message={error} onClose={() => setError('')} />}

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          type="text"
          placeholder="Rechercher un patron…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded-lg border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:border-gray-800 focus:ring-1 focus:ring-gray-800"
        />
        <div className="flex gap-2 flex-wrap">
          {GARMENT_TYPES.map((t) => (
            <button
              key={t}
              onClick={() => handleFilter(t)}
              className={[
                'px-3 py-1.5 rounded-lg text-xs font-medium border transition',
                filter === t
                  ? 'bg-gray-900 text-white border-gray-900'
                  : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400',
              ].join(' ')}
            >
              {t || 'Tous'}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex justify-center py-10">
          <div className="w-7 h-7 border-4 border-gray-200 border-t-rose-500 rounded-full animate-spin" />
        </div>
      ) : visible.length === 0 ? (
        <p className="text-center text-sm text-gray-400 py-10">Aucun patron trouvé.</p>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {visible.map((m) => (
            <ModelCard key={m.model_id} model={m} onClick={() => openDetail(m)} />
          ))}
        </div>
      )}

      {/* Detail modal */}
      {selected && (
        <ModelDetail
          model={selected}
          detail={detail}
          loading={detLoading}
          onClose={() => { setSelected(null); setDetail(null); }}
        />
      )}
    </div>
  );
}

function ModelCard({ model, onClick }) {
  const badge = STATUS_COLORS[model.status] ?? 'bg-gray-100 text-gray-600';
  return (
    <button
      onClick={onClick}
      className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden text-left hover:shadow-md transition flex flex-col"
    >
      <div className="h-40 bg-gradient-to-br from-rose-50 to-gray-100 flex items-center justify-center overflow-hidden">
        {model.photo_url
          ? <img src={model.photo_url} alt={model.model_name} className="w-full h-full object-cover" />
          : <span className="text-5xl">👗</span>}
      </div>
      <div className="p-4 flex flex-col gap-1.5 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="font-semibold text-gray-900 text-sm">{model.model_name}</p>
          <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${badge}`}>
            {model.status}
          </span>
        </div>
        <p className="text-xs text-gray-500">{model.garment_type} · {model.cut_type}</p>
        <p className="text-xs text-gray-400 mt-auto">Version {model.version}</p>
      </div>
    </button>
  );
}

function ModelDetail({ model, detail, loading, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 space-y-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">{model.model_name}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl font-bold">×</button>
        </div>

        {model.photo_url && (
          <img src={model.photo_url} alt={model.model_name} className="w-full h-48 object-cover rounded-xl" />
        )}

        {loading ? (
          <div className="flex justify-center py-6">
            <div className="w-6 h-6 border-4 border-gray-200 border-t-rose-500 rounded-full animate-spin" />
          </div>
        ) : detail ? (
          <>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <D label="Type"        value={detail.garment_type} />
              <D label="Coupe"       value={detail.cut_type} />
              <D label="Statut"      value={detail.status} />
              <D label="Version"     value={detail.version} />
            </div>
            {detail.description && (
              <p className="text-sm text-gray-600">{detail.description}</p>
            )}
            {detail.zones?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 mb-2">Zones critiques</p>
                <div className="flex flex-wrap gap-1.5">
                  {detail.zones.map((z) => (
                    <span key={z.zone_id} className="px-2 py-0.5 rounded-full bg-rose-50 text-rose-600 text-xs font-medium">
                      {z.zone_name}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {detail.fabrics?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 mb-2">Tissus compatibles</p>
                <div className="flex flex-wrap gap-1.5">
                  {detail.fabrics.map((f) => (
                    <span key={f.fabric_id} className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 text-xs">
                      {f.fabric_name}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}

function D({ label, value }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="text-sm font-medium text-gray-800">{value}</p>
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
