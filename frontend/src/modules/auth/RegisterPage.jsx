import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register as registerApi } from '../../api/auth';
import { useLanguage } from '../../context/LanguageContext';
import fashionBg from '../../assets/fashion1.png';

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
    <div
      className="relative min-h-screen flex items-center justify-center overflow-hidden py-8"
      style={{
        backgroundImage: `url(${fashionBg})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }}
    >
      {/* Floating Language Switcher */}
      <button
        onClick={() => changeLanguage(locale === 'en' ? 'fr' : 'en')}
        className="absolute top-4 right-4 text-xs font-bold px-3 py-1.5 rounded-xl border border-white/30 text-white bg-white/10 hover:bg-white/20 transition z-50 backdrop-blur"
      >
        {locale === 'en' ? 'FR' : 'EN'}
      </button>

      <div className="relative z-10 w-full max-w-sm mx-4">
        <div className="text-center mb-6">
          <h1 className="text-4xl font-extrabold tracking-widest text-white">LOVA</h1>
          <p className="text-pink-400 text-sm font-semibold tracking-[0.4em] uppercase mt-1">Fashion</p>
        </div>

        <div
          className="rounded-3xl p-8 shadow-2xl"
          style={{
            background: 'rgba(255,255,255,0.18)',
            backdropFilter: 'blur(24px)',
            WebkitBackdropFilter: 'blur(24px)',
            border: '1px solid rgba(255,255,255,0.3)',
          }}
        >
          {/* Avatar */}
          <div className="flex justify-center mb-5">
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center shadow-lg"
              style={{ background: 'linear-gradient(135deg, #EC4899, #9333EA)', boxShadow: '0 0 28px rgba(236,72,153,0.5)' }}
            >
              <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
              </svg>
            </div>
          </div>

          <div className="text-center mb-5">
            <h2
              className="text-xl font-extrabold"
              style={{ background: 'linear-gradient(90deg, #EC4899, #9333EA)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
            >
              {t('auth.joinTitle')}
            </h2>
            <p className="text-white/60 text-xs mt-1">{t('auth.joinSubtitle')}</p>
          </div>

          {error && (
            <div className="mb-4 rounded-xl bg-red-500/20 border border-red-400/40 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-3">
            {[
              { name: 'nom',   placeholder: t('auth.fullName'),    type: 'text'  },
              { name: 'email', placeholder: t('auth.email'),       type: 'email' },
            ].map(({ name, placeholder, type }) => (
              <div
                key={name}
                className="flex items-center gap-3 rounded-2xl px-4 py-3"
                style={{ background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.2)' }}
              >
                <input
                  name={name}
                  type={type}
                  required
                  value={form[name]}
                  onChange={handleChange}
                  placeholder={placeholder}
                  className="flex-1 bg-transparent text-sm text-white placeholder-white/50 focus:outline-none"
                />
              </div>
            ))}

            {/* Password */}
            <div
              className="flex items-center gap-3 rounded-2xl px-4 py-3"
              style={{ background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.2)' }}
            >
              <input
                name="mot_de_passe"
                type={showPwd ? 'text' : 'password'}
                autoComplete="new-password"
                required
                value={form.mot_de_passe}
                onChange={handleChange}
                placeholder={t('auth.password')}
                className="flex-1 bg-transparent text-sm text-white placeholder-white/50 focus:outline-none"
              />
              <button type="button" onClick={() => setShowPwd(!showPwd)} className="text-white/50 hover:text-white/80">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              </button>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-2xl py-3.5 text-sm font-bold text-white flex items-center justify-center gap-2 transition-opacity disabled:opacity-60 mt-1"
              style={{ background: 'linear-gradient(90deg, #EC4899, #9333EA)' }}
            >
              {loading ? t('auth.registering') : <>{t('auth.registerBtn')} <span className="text-lg">→</span></>}
            </button>
          </form>

          <div className="flex items-center gap-3 my-4">
            <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.2)' }} />
            <span className="text-xs text-white/40">{t('common.or')}</span>
            <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.2)' }} />
          </div>

          <Link
            to="/login"
            className="flex items-center justify-center gap-2 w-full rounded-2xl py-3 text-sm font-semibold transition"
            style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.25)', color: 'white' }}
          >
            {t('auth.alreadyHaveAccount')}
          </Link>
        </div>
      </div>
    </div>
  );
}
