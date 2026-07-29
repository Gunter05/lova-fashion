import { useEffect, useState } from 'react';
import { listFabrics, listCategories, selectFabric, listModels, getModel } from '../../api/modules';

const FALLBACK_IMG = 'https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=800';

const STATUS_CONFIG = {
  available:   { label: 'Disponible', cls: 'bg-[#4E6E58]/10 text-[#4E6E58]' },
  unavailable: { cls: 'bg-amber-50 text-amber-700', label: 'Indisponible' },
  archived:    { cls: 'bg-gray-100 text-gray-400',  label: 'Archivé' },
};
const GARMENT_TYPES = ['', 'Dress', 'Shirt', 'Trousers', 'Skirt', 'Jacket', 'Coat', 'Suit'];
const TYPE_LABELS = {
  '': 'Tous', Dress: 'Robe', Shirt: 'Chemise', Trousers: 'Pantalon',
  Skirt: 'Jupe', Jacket: 'Veste', Coat: 'Manteau', Suit: 'Costume',
};

export default function CatalogPage() {
  const [activeTab,   setActiveTab]   = useState('TISSUS');

  // ── Fabric state ──
  const [fabrics,    setFabrics]    = useState([]);
  const [categories, setCategories] = useState([]);
  const [catFilter,  setCatFilter]  = useState('');
  const [fabSearch,  setFabSearch]  = useState('');
  const [selFabric,  setSelFabric]  = useState(null);
  const [selecting,  setSelecting]  = useState(false);
  const [fabLoad,    setFabLoad]    = useState(true);

  // ── Model state ──
  const [models,      setModels]      = useState([]);
  const [typeFilter,  setTypeFilter]  = useState('');
  const [modSearch,   setModSearch]   = useState('');
  const [selModel,    setSelModel]    = useState(null);
  const [selModelDet, setSelModelDet] = useState(null);
  const [modLoad,     setModLoad]     = useState(true);
  const [modDetLoad,  setModDetLoad]  = useState(false);

  // ── Shared ──
  const [error, setError] = useState('');
  const [info,  setInfo]  = useState('');

  useEffect(() => {
    (async () => {
      try {
        const [fRes, cRes] = await Promise.all([listFabrics(), listCategories()]);
        setFabrics(fRes.data);
        setCategories(cRes.data);
      } catch { setError('Impossible de charger les tissus.'); }
      finally { setFabLoad(false); }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await listModels(typeFilter || undefined);
        setModels(res.data.items || []);
      } catch { setError('Impossible de charger les modèles.'); }
      finally { setModLoad(false); }
    })();
  }, [typeFilter]);

  const handleCatChange = async (catId) => {
    setCatFilter(catId); setFabLoad(true);
    try {
      const res = await listFabrics(catId || undefined);
      setFabrics(res.data);
    } catch { setError('Erreur lors du filtrage.'); }
    finally { setFabLoad(false); }
  };

  const handleSelectFabric = async (fabric) => {
    setSelecting(true); setError(''); setInfo('');
    try {
      await selectFabric(fabric.fabric_id);
      setInfo(`"${fabric.fabric_name}" sélectionné avec succès.`);
    } catch (err) {
      const data = err?.response?.data;
      setError(err?.response?.status === 409
        ? `Tissu indisponible. ${data?.detail || ''}`
        : data?.detail?.message || 'Erreur lors de la sélection.');
    } finally { setSelecting(false); }
  };

  const openModelDetail = async (model) => {
    setSelModel(model); setSelModelDet(null); setModDetLoad(true);
    try {
      const res = await getModel(model.model_id);
      setSelModelDet(res.data);
    } catch { setError('Impossible de charger les détails du patron.'); }
    finally { setModDetLoad(false); }
  };

  const visibleFabrics = fabrics.filter((f) =>
    f.fabric_name.toLowerCase().includes(fabSearch.toLowerCase())
  );
  const visibleModels = models.filter((m) =>
    m.model_name.toLowerCase().includes(modSearch.toLowerCase())
  );

  return (
    <div className="space-y-4 max-w-lg mx-auto" style={{ background: '#FDFBF7', minHeight: '100vh' }}>
      {/* Header */}
      <div className="flex items-center justify-between pt-1">
        <div>
          <h1 className="text-lg font-bold text-gray-900">Choisissez votre modèle</h1>
          <p className="text-xs text-gray-400 mt-0.5">et votre tissu</p>
        </div>
        <button className="w-8 h-8 rounded-full bg-white shadow-sm border border-[#F0EDE8] flex items-center justify-center text-gray-400">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
          </svg>
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-[#F0EDE8] rounded-xl p-1">
        {['MODÈLES', 'TISSUS'].map((tab) => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={`flex-1 py-2 rounded-lg text-xs font-bold transition ${activeTab === tab ? 'bg-white shadow-sm text-[#D95D39]' : 'text-gray-400'}`}
          >{tab}</button>
        ))}
      </div>

      {error && <Toast type="error"   message={error} onClose={() => setError('')} />}
      {info  && <Toast type="success" message={info}  onClose={() => setInfo('')} />}

      {/* ── TISSUS tab ── */}
      {activeTab === 'TISSUS' && (
        <>
          {/* Category filter pills */}
          <div className="flex gap-2 overflow-x-auto pb-1">
            <button onClick={() => handleCatChange('')}
              className={`shrink-0 px-3 py-1.5 rounded-xl text-xs font-semibold border transition ${!catFilter ? 'bg-[#D95D39] text-white border-[#D95D39]' : 'bg-white text-gray-500 border-[#E8E4DF]'}`}
            >Tous</button>
            {categories.map((c) => (
              <button key={c.category_id} onClick={() => handleCatChange(c.category_id)}
                className={`shrink-0 px-3 py-1.5 rounded-xl text-xs font-semibold border transition ${catFilter === c.category_id ? 'bg-[#D95D39] text-white border-[#D95D39]' : 'bg-white text-gray-500 border-[#E8E4DF]'}`}
              >{c.category_name}</button>
            ))}
          </div>
          <SearchBox value={fabSearch} onChange={setFabSearch} placeholder="Rechercher un tissu…" />
          {fabLoad ? <Spinner /> : visibleFabrics.length === 0
            ? <p className="text-center text-sm text-gray-400 py-8">Aucun tissu trouvé.</p>
            : <div className="grid grid-cols-2 gap-3">
                {visibleFabrics.map((f) => (
                  <FabricCard key={f.fabric_id} fabric={f} onSelect={handleSelectFabric} selecting={selecting} onClick={() => setSelFabric(f)} />
                ))}
              </div>
          }
          {selFabric && (
            <FabricDetail fabric={selFabric} onClose={() => setSelFabric(null)} onSelect={handleSelectFabric} selecting={selecting} />
          )}
        </>
      )}

      {/* ── MODÈLES tab ── */}
      {activeTab === 'MODÈLES' && (
        <>
          {/* Type filter pills */}
          <div className="flex gap-2 overflow-x-auto pb-1">
            {GARMENT_TYPES.map((t) => (
              <button key={t} onClick={() => setTypeFilter(t)}
                className={`shrink-0 px-3 py-1.5 rounded-xl text-xs font-semibold border transition ${typeFilter === t ? 'bg-[#D95D39] text-white border-[#D95D39]' : 'bg-white text-gray-500 border-[#E8E4DF]'}`}
              >{TYPE_LABELS[t] ?? t}</button>
            ))}
          </div>
          <SearchBox value={modSearch} onChange={setModSearch} placeholder="Rechercher un modèle…" />
          {modLoad ? <Spinner /> : visibleModels.length === 0
            ? <p className="text-center text-sm text-gray-400 py-8">Aucun modèle trouvé.</p>
            : <div className="grid grid-cols-2 gap-3">
                {visibleModels.map((m) => (
                  <ModelCard key={m.model_id} model={m} onClick={() => openModelDetail(m)} />
                ))}
              </div>
          }
          {selModel && (
            <ModelDetail model={selModel} detail={selModelDet} loading={modDetLoad}
              onClose={() => { setSelModel(null); setSelModelDet(null); }} />
          )}
        </>
      )}
    </div>
  );
}

// ── Shared sub-components ────────────────────────────────────────────────────

function SearchBox({ value, onChange, placeholder }) {
  return (
    <div className="relative">
      <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-300" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
      <input type="text" placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full pl-9 pr-4 py-2.5 rounded-xl bg-white border border-[#E8E4DF] text-sm focus:outline-none focus:border-[#D95D39]" />
    </div>
  );
}

function FabricCard({ fabric, onSelect, selecting, onClick }) {
  const isAvailable = fabric.fabric_status === 'available';
  const imgSrc = fabric.fabric_photo || FALLBACK_IMG;
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] overflow-hidden flex flex-col cursor-pointer hover:shadow-md transition" onClick={onClick}>
      <div className="aspect-square bg-[#F5F0EA] overflow-hidden relative">
        <img src={imgSrc} alt={fabric.fabric_name} className="w-full h-full object-cover"
          onError={(e) => { e.currentTarget.src = FALLBACK_IMG; }} />
        {isAvailable && (
          <span className="absolute top-2 right-2 text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#4E6E58] text-white">Souple</span>
        )}
      </div>
      <div className="p-3 flex flex-col gap-1 flex-1">
        <p className="text-sm font-semibold text-gray-900 leading-tight">{fabric.fabric_name}</p>
        <p className="text-xs text-gray-400">{fabric.category_name}</p>
        <p className="text-sm font-bold text-gray-800 mt-auto">{fabric.fabric_unit_price?.toLocaleString('fr-FR')} FCFA/m</p>
        <button onClick={(e) => { e.stopPropagation(); onSelect(fabric); }} disabled={selecting || !isAvailable}
          className="w-full mt-1 py-2 rounded-xl text-xs font-bold text-white disabled:opacity-40 transition"
          style={{ background: isAvailable ? '#D95D39' : '#ccc' }}>
          Choisir ce tissu
        </button>
      </div>
    </div>
  );
}

function FabricDetail({ fabric, onClose, onSelect, selecting }) {
  const imgSrc = fabric.fabric_photo || FALLBACK_IMG;
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center" onClick={onClose}>
      <div className="bg-white rounded-t-3xl sm:rounded-3xl w-full sm:max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="w-10 h-1 rounded-full bg-gray-300 mx-auto sm:hidden" />
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">{fabric.fabric_name}</h3>
          <button onClick={onClose} className="text-gray-300 hover:text-gray-500 text-2xl font-light">×</button>
        </div>
        <img src={imgSrc} alt={fabric.fabric_name} className="w-full h-44 object-cover rounded-2xl"
          onError={(e) => { e.currentTarget.src = FALLBACK_IMG; }} />
        <p className="text-sm text-gray-600 leading-relaxed">
          {fabric.fabric_composition ? `Tissu doux et lumineux avec un beau tombé fluide. Composition ${fabric.fabric_composition.toLowerCase()}.` : 'Tissu de haute qualité.'}
        </p>
        <div className="grid grid-cols-2 gap-3">
          {[
            ['Composition', fabric.fabric_composition ?? '—'],
            ['Élasticité',  fabric.fabric_elasticity_rate != null ? `${fabric.fabric_elasticity_rate}%` : '—'],
            ['Poids',       fabric.fabric_weight ? `${fabric.fabric_weight} g/m²` : '—'],
            ['Prix',        `${fabric.fabric_unit_price?.toLocaleString('fr-FR')} FCFA/m`],
          ].map(([label, val]) => (
            <div key={label} className="bg-[#FDFBF7] rounded-2xl p-3">
              <p className="text-xs text-gray-400">{label}</p>
              <p className="text-sm font-semibold text-gray-800 mt-0.5">{val}</p>
            </div>
          ))}
        </div>
        <button onClick={() => { onSelect(fabric); onClose(); }} disabled={selecting || fabric.fabric_status !== 'available'}
          className="w-full py-3.5 rounded-2xl text-sm font-bold text-white disabled:opacity-40"
          style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}>
          Choisir ce tissu
        </button>
      </div>
    </div>
  );
}

function ModelCard({ model, onClick }) {
  const imgSrc = model.photo_url || FALLBACK_IMG;
  return (
    <button onClick={onClick} className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] overflow-hidden text-left hover:shadow-md transition flex flex-col">
      <div className="aspect-square bg-gradient-to-br from-[#FDFBF7] to-[#F0EDE8] overflow-hidden relative">
        <img src={imgSrc} alt={model.model_name} className="w-full h-full object-cover"
          onError={(e) => { e.currentTarget.src = FALLBACK_IMG; }} />
      </div>
      <div className="p-3 flex flex-col gap-1 flex-1">
        <p className="text-sm font-semibold text-gray-900 leading-tight">{model.model_name}</p>
        <div className="flex flex-wrap gap-1 mt-0.5">
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#D95D39]/10 text-[#D95D39] font-medium">{model.garment_type}</span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#F0EDE8] text-gray-500 font-medium">{model.cut_type}</span>
        </div>
        <button className="w-full mt-auto py-2 rounded-xl text-xs font-bold text-white" style={{ background: '#D95D39' }}>
          Voir le modèle
        </button>
      </div>
    </button>
  );
}

function ModelDetail({ model, detail, loading, onClose }) {
  const imgSrc = (detail?.photo_url || model.photo_url) || FALLBACK_IMG;
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center" onClick={onClose}>
      <div className="bg-white rounded-t-3xl sm:rounded-3xl w-full sm:max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="w-10 h-1 rounded-full bg-gray-300 mx-auto sm:hidden" />
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">{model.model_name}</h3>
          <button onClick={onClose} className="text-gray-300 hover:text-gray-500 text-2xl font-light">×</button>
        </div>
        <img src={imgSrc} alt={model.model_name} className="w-full h-48 object-cover rounded-2xl"
          onError={(e) => { e.currentTarget.src = FALLBACK_IMG; }} />
        {loading ? <Spinner /> : detail ? (
          <>
            {detail.description && <p className="text-sm text-gray-500">{detail.description}</p>}
            <div className="flex flex-wrap gap-1.5">
              <span className="px-3 py-1 rounded-full bg-[#D95D39]/10 text-[#D95D39] text-xs font-semibold">{detail.garment_type}</span>
              <span className="px-3 py-1 rounded-full bg-[#F0EDE8] text-gray-600 text-xs font-medium">{detail.cut_type}</span>
            </div>
            {detail.zones?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 mb-2">Morphologies recommandées</p>
                <div className="flex flex-wrap gap-1.5">
                  {detail.zones.map((z) => (
                    <span key={z.zone_id} className="px-2.5 py-1 rounded-full bg-[#D95D39]/10 text-[#D95D39] text-xs font-medium">{z.zone_name}</span>
                  ))}
                </div>
              </div>
            )}
            {detail.fabrics?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 mb-2">Tissus compatibles</p>
                <div className="flex flex-wrap gap-1.5">
                  {detail.fabrics.map((f) => (
                    <span key={f.fabric_id} className="px-2.5 py-1 rounded-full bg-[#FDFBF7] border border-[#E8E4DF] text-gray-600 text-xs">{f.fabric_name}</span>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : null}
        <button onClick={onClose} className="w-full py-3.5 rounded-2xl text-sm font-bold text-white"
          style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}>
          Choisir ce modèle
        </button>
      </div>
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
    <div className="flex items-center justify-center min-h-[30vh]">
      <div className="w-8 h-8 border-4 border-[#F0EDE8] border-t-[#D95D39] rounded-full animate-spin" />
    </div>
  );
}
