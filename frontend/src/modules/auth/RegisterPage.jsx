import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register as registerApi } from '../../api/auth';
import { useLanguage } from '../../context/LanguageContext';

export default function RegisterPage() {
  const navigate = useNavigate();
  const { t, locale, changeLanguage } = useLanguage();

  const [form, setForm] = useState({
    nom: '',
    email: '',
    mot_de_passe: '',
  });
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await registerApi(form);
      navigate('/login', {
        state: { message: t('auth.regSuccess') },
      });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const backendMessage = err?.response?.data?.message;
      const message =
        Array.isArray(detail)
          ? detail.map((d) => d.msg).join(', ')
          : typeof detail === 'string'
          ? detail
          : detail?.message ||
            backendMessage ||
            t('auth.defaultError');
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen flex items-center justify-center px-4 py-8" style={{ background: '#FAF8F5' }}>
      <button
        onClick={() => changeLanguage(locale === 'en' ? 'fr' : 'en')}
        className="absolute top-4 right-4 text-xs font-bold px-2 py-1 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-100 transition"
      >
        {locale === 'en' ? 'FR' : 'EN'}
      </button>

      <div className="w-full max-w-sm">
        <div className="text-center mb-6">
          <span className="text-3xl font-extrabold tracking-widest text-gray-900">LOVA</span>
          <p className="text-xs font-semibold tracking-[0.35em] text-terracotta uppercase mt-1">Fashion</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-[#F0EDE8] p-6">
          <div className="flex justify-center mb-5">
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #D95D39, #B54A2E)' }}
            >
              <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
              </svg>
            </div>
          </div>

          <div className="text-center mb-5">
            <h2 className="text-xl font-bold text-gray-900">{t('auth.joinTitle')}</h2>
            <p className="text-xs text-gray-400 mt-1">{t('auth.joinSubtitle')}</p>
          </div>

          {error && (
            <div className="mb-4 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">{t('auth.fullName')}</label>
              <input
                name="nom"
                type="text"
                required
                value={form.nom}
                onChange={handleChange}
                className="w-full rounded-xl border border-[#E8E4DF] px-4 py-2.5 text-sm focus:outline-none focus:border-terracotta bg-white"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">{t('auth.email')}</label>
              <input
                name="email"
                type="email"
                required
                value={form.email}
                onChange={handleChange}
                className="w-full rounded-xl border border-[#E8E4DF] px-4 py-2.5 text-sm focus:outline-none focus:border-terracotta bg-white"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">{t('auth.password')}</label>
              <div className="relative">
                <input
                  name="mot_de_passe"
                  type={showPwd ? 'text' : 'password'}
                  autoComplete="new-password"
                  required
                  value={form.mot_de_passe}
                  onChange={handleChange}
                  className="w-full rounded-xl border border-[#E8E4DF] px-4 py-2.5 pr-10 text-sm focus:outline-none focus:border-terracotta bg-white"
                />
                <button
                  type="button"
                  onClick={() => setShowPwd(!showPwd)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  {showPwd ? (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 4.411m0 0L21 21" /></svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-2xl py-3.5 text-sm font-bold text-white disabled:opacity-50 mt-1"
              style={{ background: 'linear-gradient(90deg, #D95D39, #B54A2E)' }}
            >
              {loading ? t('auth.registering') : t('auth.registerBtn')}
            </button>
          </form>

          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px bg-[#F0EDE8]" />
            <span className="text-xs text-gray-400">{t('common.or')}</span>
            <div className="flex-1 h-px bg-[#F0EDE8]" />
          </div>

          <Link
            to="/login"
            className="flex items-center justify-center w-full rounded-2xl py-3 text-sm font-semibold text-gray-700 border border-[#E8E4DF] hover:bg-gray-50 transition"
          >
            {t('auth.alreadyHaveAccount')}
          </Link>
        </div>
      </div>
    </div>
  );
}