import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useLanguage } from '../../context/LanguageContext';
import { getMyProfile, updateMyProfile, uploadProfilePhoto, getPhotoHistory } from '../../api/modules';

export default function ProfilePage() {
  const { login, token } = useAuth();
  const { t, locale } = useLanguage();
  const fileRef = useRef(null);

  const [profile,   setProfile]   = useState(null);
  const [photos,    setPhotos]    = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [saving,    setSaving]    = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error,     setError]     = useState('');
  const [success,   setSuccess]   = useState('');
  const [form,      setForm]      = useState({ nom: '', email: '' });

  const getRoleLabel = (role) => {
    if (!role) return '';
    return t(`profile.roles.${role}`) || role;
  };

  useEffect(() => {
    (async () => {
      try {
        const [pRes, phRes] = await Promise.all([getMyProfile(), getPhotoHistory()]);
        setProfile(pRes.data);
        setPhotos(phRes.data || []);
        setForm({ nom: pRes.data.nom, email: pRes.data.email });
      } catch {
        setError(t('profile.unableLoad'));
      } finally {
        setLoading(false);
      }
    })();
  }, [t]);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const res = await updateMyProfile(form);
      setProfile(res.data);
      login(res.data, token);
      setSuccess(t('profile.updated'));
    } catch (err) {
      setError(err?.response?.data?.detail?.message || 'Error updating.');
    } finally {
      setSaving(false);
    }
  };

  const handlePhotoChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      const res = await uploadProfilePhoto(file);
      setPhotos((prev) => [res.data, ...prev]);
      setSuccess(t('profile.photoUpdated'));
    } catch (err) {
      setError(err?.response?.data?.detail?.message || t('profile.uploadFailed'));
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  if (loading) return <Spinner />;

  const latestPhoto = photos[0]?.url_photo;
  const initials    = (profile?.nom || 'U').split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();

  return (
    <div className="space-y-4 max-w-lg mx-auto">
      {error   && <Toast type="error"   message={error}   onClose={() => setError('')} />}
      {success && <Toast type="success" message={success} onClose={() => setSuccess('')} />}

      {/* Avatar card */}
      <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5 flex items-center gap-4">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="relative shrink-0 group"
          title={t('profile.changePhoto')}
        >
          <div
            className="w-20 h-20 rounded-full overflow-hidden ring-4 ring-[#F0EDE8]"
            style={{ background: 'linear-gradient(135deg, #D95D39, #B54A2E)' }}
          >
            {latestPhoto
              ? <img src={latestPhoto} alt="avatar" className="w-full h-full object-cover" />
              : <span className="w-full h-full flex items-center justify-center text-2xl font-extrabold text-white">{initials}</span>}
          </div>
          <span className="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition flex items-center justify-center text-white text-xs font-medium">
            {uploading ? '…' : t('profile.edit')}
          </span>
        </button>
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handlePhotoChange} />

        <div>
          <p className="text-base font-bold text-gray-900">{profile?.nom}</p>
          <p className="text-xs text-gray-400 mt-0.5">{profile?.email}</p>
          <span className="inline-block mt-1.5 px-2.5 py-0.5 text-xs font-semibold rounded-full bg-[#D95D39]/10 text-[#D95D39]">
            {getRoleLabel(profile?.role)}
          </span>
        </div>
      </div>

      {/* Edit form */}
      <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">{t('profile.personalInfo')}</h2>
        <form onSubmit={handleSave} className="space-y-3">
          {[
            { label: t('profile.role'),               value: getRoleLabel(profile?.role) },
            {
              label: t('profile.regDate'),
              value: profile?.date_inscription
                ? new Date(profile.date_inscription).toLocaleDateString(locale === 'en' ? 'en-US' : 'fr-FR', { dateStyle: 'long' })
                : '',
            },
          ].map(({ label, value }) => (
            <div key={label}>
              <label className="block text-xs font-medium text-gray-400 mb-1">{label}</label>
              <div className="w-full rounded-xl border border-[#F0EDE8] bg-[#FAF8F5] px-4 py-2.5 text-sm text-gray-500">
                {value}
              </div>
            </div>
          ))}

          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">{t('profile.fullName')}</label>
            <input
              name="nom"
              type="text"
              value={form.nom}
              onChange={(e) => setForm((p) => ({ ...p, nom: e.target.value }))}
              className="w-full rounded-xl border border-[#E8E4DF] px-4 py-2.5 text-sm focus:outline-none focus:border-[#D95D39] bg-white"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">{t('profile.email')}</label>
            <input
              name="email"
              type="email"
              value={form.email}
              onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
              className="w-full rounded-xl border border-[#E8E4DF] px-4 py-2.5 text-sm focus:outline-none focus:border-[#D95D39] bg-white"
            />
          </div>

          <button
            type="submit"
            disabled={saving}
            className="w-full rounded-2xl py-3.5 text-sm font-bold text-white disabled:opacity-50 mt-1"
            style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
          >
            {saving ? t('profile.savingBtn') : t('profile.saveBtn')}
          </button>
        </form>
      </div>

      {/* Photo history */}
      {photos.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">{t('profile.photoHistory')}</h2>
          <div className="grid grid-cols-4 gap-2">
            {photos.map((p) => (
              <div key={p.id_photo} className="aspect-square rounded-xl overflow-hidden border border-[#F0EDE8]">
                <img src={p.url_photo} alt="photo" className="w-full h-full object-cover" />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Toast({ type, message, onClose }) {
  const s = {
    error:   'bg-red-50 border-red-100 text-red-700',
    success: 'bg-[#4E6E58]/5 border-[#4E6E58]/20 text-[#3A5242]',
  };
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
