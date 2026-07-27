import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { getMyProfile, updateMyProfile, uploadProfilePhoto, getPhotoHistory } from '../../api/modules';

const ROLE_LABELS = { Client: 'Client', Tailor: 'Tailleur', Admin: 'Administrateur' };

export default function ProfilePage() {
  const { user, login, token } = useAuth();
  const fileRef = useRef(null);

  const [profile, setProfile] = useState(null);
  const [photos,  setPhotos]  = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving,  setSaving]  = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error,   setError]   = useState('');
  const [success, setSuccess] = useState('');
  const [form, setForm]       = useState({ nom: '', email: '' });

  // ── Load profile ───────────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const [pRes, phRes] = await Promise.all([getMyProfile(), getPhotoHistory()]);
        setProfile(pRes.data);
        setPhotos(phRes.data || []);
        setForm({ nom: pRes.data.nom, email: pRes.data.email });
      } catch {
        setError('Impossible de charger le profil.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // ── Update profile ─────────────────────────────────────────────────────────
  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const res = await updateMyProfile(form);
      setProfile(res.data);
      login(res.data, token);           // refresh stored user
      setSuccess('Profil mis à jour avec succès.');
    } catch (err) {
      setError(err?.response?.data?.detail?.message || 'Erreur lors de la mise à jour.');
    } finally {
      setSaving(false);
    }
  };

  // ── Upload photo ───────────────────────────────────────────────────────────
  const handlePhotoChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      const res = await uploadProfilePhoto(file);
      setPhotos((prev) => [res.data, ...prev]);
      setSuccess('Photo de profil mise à jour.');
    } catch (err) {
      setError(err?.response?.data?.detail?.message || "Échec du téléversement de la photo.");
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  if (loading) return <LoadingSpinner />;

  const latestPhoto = photos[0]?.url_photo;
  const initials    = (profile?.nom || 'U').split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Mon Profil</h1>
        <p className="text-sm text-gray-500 mt-0.5">Gérez vos informations personnelles et votre photo de profil.</p>
      </div>

      {/* Alerts */}
      {error   && <Alert type="error"   message={error}   onClose={() => setError('')} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess('')} />}

      {/* Avatar + basic info */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 flex items-center gap-6">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="relative shrink-0 group"
          title="Changer la photo"
        >
          <div className="w-20 h-20 rounded-full bg-rose-100 flex items-center justify-center overflow-hidden ring-2 ring-rose-200">
            {latestPhoto
              ? <img src={latestPhoto} alt="avatar" className="w-full h-full object-cover" />
              : <span className="text-2xl font-bold text-rose-500">{initials}</span>}
          </div>
          <span className="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition flex items-center justify-center text-white text-xs font-medium">
            {uploading ? '…' : 'Modifier'}
          </span>
        </button>
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handlePhotoChange} />

        <div>
          <p className="text-lg font-semibold text-gray-900">{profile?.nom}</p>
          <p className="text-sm text-gray-500">{profile?.email}</p>
          <span className="inline-block mt-1 px-2.5 py-0.5 text-xs font-medium rounded-full bg-rose-50 text-rose-600 border border-rose-200">
            {ROLE_LABELS[profile?.role] ?? profile?.role}
          </span>
        </div>
      </div>

      {/* Edit form */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-base font-semibold text-gray-800 mb-4">Informations personnelles</h2>
        <form onSubmit={handleSave} className="space-y-4">
          <Field label="CNI" value={profile?.cni || ''} readOnly />
          <Field label="Rôle" value={ROLE_LABELS[profile?.role] ?? profile?.role} readOnly />
          <Field
            label="Nom complet"
            name="nom"
            value={form.nom}
            onChange={(e) => setForm((p) => ({ ...p, nom: e.target.value }))}
          />
          <Field
            label="Adresse e-mail"
            name="email"
            type="email"
            value={form.email}
            onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
          />
          <Field
            label="Date d'inscription"
            value={profile?.date_inscription ? new Date(profile.date_inscription).toLocaleDateString('fr-FR', { dateStyle: 'long' }) : ''}
            readOnly
          />
          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 rounded-lg bg-gray-900 text-white text-sm font-semibold hover:bg-gray-700 disabled:opacity-50 transition"
            >
              {saving ? 'Enregistrement…' : 'Enregistrer'}
            </button>
          </div>
        </form>
      </div>

      {/* Photo history */}
      {photos.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-base font-semibold text-gray-800 mb-4">Historique des photos</h2>
          <div className="grid grid-cols-4 gap-3">
            {photos.map((p) => (
              <div key={p.id_photo} className="aspect-square rounded-xl overflow-hidden border border-gray-100">
                <img src={p.url_photo} alt="photo" className="w-full h-full object-cover" />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, name, value, type = 'text', onChange, readOnly }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <input
        name={name}
        type={type}
        value={value}
        onChange={onChange}
        readOnly={readOnly}
        className={[
          'w-full rounded-lg border px-4 py-2.5 text-sm text-gray-900 focus:outline-none transition',
          readOnly
            ? 'border-gray-200 bg-gray-50 text-gray-500 cursor-default'
            : 'border-gray-300 focus:border-gray-800 focus:ring-1 focus:ring-gray-800',
        ].join(' ')}
      />
    </div>
  );
}

function Alert({ type, message, onClose }) {
  const styles = {
    error:   'bg-red-50 border-red-200 text-red-700',
    success: 'bg-green-50 border-green-200 text-green-700',
  };
  return (
    <div className={`flex items-center justify-between rounded-lg border px-4 py-3 text-sm ${styles[type]}`}>
      <span>{message}</span>
      <button onClick={onClose} className="ml-4 font-bold">×</button>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 border-4 border-gray-200 border-t-rose-500 rounded-full animate-spin" />
    </div>
  );
}
