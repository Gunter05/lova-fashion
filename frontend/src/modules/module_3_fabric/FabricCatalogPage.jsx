import { useEffect, useState } from 'react';
import { listFabrics, listCategories, getFabric, selectFabric } from '../../api/modules';

const STATUS_COLORS = {
  available:   'bg-green-100 text-green-700',
  unavailable: 'bg-amber-100 text-amber-700',
  archived:    'bg-gray-100 text-gray-500',
};

export default function FabricCatalogPage() {
  const [fabrics,    setFabrics]    = useState([]);
  const [categories, setCategories] = useState([]);
  const [search,     setSearch]     = useState('');
  const [catFilter,  setCatFilter]  = useState('');
  const [selected,   setSelected]   = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [selecting,  setSelecting]  = useState(false);
  const [error,      setError]      = useState('');
  const [info,       setInfo]       = useState('');

  useEffect(() => {
    (async () => {
      try {
        const [fRes, cRes] = await Promise.all([listFabrics(), listCategories()]);
        setFabrics(fRes.data);
        setCategories(cRes.data);
      } catch {
        setError('Impossible de charger le catalogue.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Filter on category change
  const handleCatChange = async (catId) => {
    setCatFilter(catId);
    setLoading(true);
    try {
      const res = await listFabrics(catId || undefined);
      setFabrics(res.data);
    } catch {
      setError('Erreur lors du filtrage.');
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (fabric) => {
    setSelecting(true);
    setError('');
    setInfo('');
    try {
      await selectFabric(fabric.fabric_id);
      setInfo(`"${fabric.fabric_name}" sélectionné avec succès.`);
    } catch (err) {
      const data = err?.response?.data;
      if (err?.response?.status === 409) {
        setError(`Tissu indisponible. ${data?.detail || ''}`);
      } else {
        setError(data?.detail?.message || 'Erreur lors de la sélection.');
      }
    } finally {
      setSelecting(false);
    }
  };

  const visible = fabrics.filter((f) =>
    f.fabric_name.toLowerCase().includes(search.toLowerCase())
  );

  if (loading && fabrics.length === 0) return <Spinner />;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Catalogue Tissus</h1>
        <p className="text-sm text-gray-500 mt-0.5">Parcourez et sélectionnez vos tissus.</p>
      </div>

      {error && <Alert type="error"   message={error} onClose={() => setError('')} />}
      {info  && <Alert type="success" message={info}  onClose={() => setInfo('')} />}

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          type="text"
          placeholder="Rechercher un tissu…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded-lg border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:border-gray-800 focus:ring-1 focus:ring-gray-800"
        />
        <select
          value={catFilter}
          onChange={(e) => handleCatChange(e.target.value)}
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:border-gray-800 bg-white"
        >
          <option value="">Toutes les catégories</option>
          {categories.map((c) => (
            <option key={c.category_id} value={c.category_id}>{c.category_name}</option>
          ))}
        </select>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex justify-center py-10"><div className="w-7 h-7 border-4 border-gray-200 border-t-rose-500 rounded-full animate-spin" /></div>
      ) : visible.length === 0 ? (
        <p className="text-center text-sm text-gray-400 py-10">Aucun tissu trouvé.</p>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {visible.map((f) => (
            <FabricCard key={f.fabric_id} fabric={f} onSelect={handleSelect} selecting={selecting} onClick={() => setSelected(f)} />
          ))}
        </div>
      )}

      {/* Detail panel */}
      {selected && (
        <FabricDetail fabric={selected} onClose={() => setSelected(null)} onSelect={handleSelect} selecting={selecting} />
      )}
    </div>
  );
}

function FabricCard({ fabric, onSelect, selecting, onClick }) {
  const badge = STATUS_COLORS[fabric.fabric_status] ?? 'bg-gray-100 text-gray-500';
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex flex-col">
      {/* Photo */}
      <div
        className="h-40 bg-gray-100 flex items-center justify-center overflow-hidden cursor-pointer"
        onClick={onClick}
      >
        {fabric.fabric_photo
          ? <img src={fabric.fabric_photo} alt={fabric.fabric_name} className="w-full h-full object-cover" />
          : <span className="text-gray-300 text-4xl">🧵</span>}
      </div>

      <div className="p-4 flex flex-col gap-2 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="font-semibold text-gray-900 text-sm">{fabric.fabric_name}</p>
          <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${badge}`}>
            {fabric.fabric_status}
          </span>
        </div>
        <p className="text-xs text-gray-500">{fabric.category_name}</p>
        <p className="text-sm font-bold text-gray-900 mt-auto">{fabric.fabric_unit_price?.toLocaleString('fr-FR')} FCFA/m</p>
        <button
          onClick={() => onSelect(fabric)}
          disabled={selecting || fabric.fabric_status !== 'available'}
          className="w-full mt-1 py-2 rounded-lg bg-rose-500 text-white text-xs font-semibold hover:bg-rose-600 disabled:opacity-40 transition"
        >
          Sélectionner
        </button>
      </div>
    </div>
  );
}

function FabricDetail({ fabric, onClose, onSelect, selecting }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">{fabric.fabric_name}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl font-bold">×</button>
        </div>
        {fabric.fabric_photo && (
          <img src={fabric.fabric_photo} alt={fabric.fabric_name} className="w-full h-48 object-cover rounded-xl" />
        )}
        <div className="grid grid-cols-2 gap-3 text-sm">
          <Detail label="Catégorie"    value={fabric.category_name} />
          <Detail label="Prix"         value={`${fabric.fabric_unit_price} FCFA/m`} />
          <Detail label="Élasticité"   value={`${fabric.fabric_elasticity_rate ?? '—'}`} />
          <Detail label="Poids"        value={`${fabric.fabric_weight ?? '—'} g/m²`} />
          <Detail label="Composition"  value={fabric.fabric_composition ?? '—'} />
          <Detail label="Rigidité réf" value={fabric.reference_rigidity_level ?? '—'} />
        </div>
        <button
          onClick={() => { onSelect(fabric); onClose(); }}
          disabled={selecting || fabric.fabric_status !== 'available'}
          className="w-full py-2.5 rounded-lg bg-rose-500 text-white text-sm font-semibold hover:bg-rose-600 disabled:opacity-40 transition"
        >
          Sélectionner ce tissu
        </button>
      </div>
    </div>
  );
}

function Detail({ label, value }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="text-sm font-medium text-gray-800">{value}</p>
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
