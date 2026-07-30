import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { login as loginApi } from '../../api/auth';
import { useAuth } from '../../context/AuthContext';
import fashionBg from '../../assets/fashion1.png';

export default function LoginPage() {
  const navigate = useNavigate();
  const auth = useAuth();

  const [email, setEmail] = useState('');
  const [mot_de_passe, setMotDePasse] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const response = await loginApi(email, mot_de_passe);
      const { access_token } = response.data;
      auth.login(null, access_token);
      const { getMyProfile } = await import('../../api/modules');
      const profileRes = await getMyProfile();
      auth.login(profileRes.data, access_token);
      navigate('/');
    } catch (err) {
      const detail = err?.response?.data?.detail;
      // The backend wraps errors in {error, field, message} inside `detail`
      const message =
        (typeof detail === 'object' && detail?.message)
          ? detail.message
          : (typeof detail === 'string' ? detail : null)
          ?? err?.response?.data?.message
          ?? 'Identifiants incorrects. Veuillez réessayer.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="relative min-h-screen flex items-center justify-center overflow-hidden"
      style={{
        backgroundImage: `url(${fashionBg})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }}
    >

      {/* Glassmorphism Card */}
      <div className="relative z-10 w-full max-w-sm mx-4">
        {/* Logo above card */}
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
          <div className="flex justify-center mb-6">
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center shadow-lg"
              style={{
                background: 'linear-gradient(135deg, #EC4899, #9333EA)',
                boxShadow: '0 0 32px rgba(236,72,153,0.5)',
              }}
            >
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
          </div>

          {/* Title */}
          <div className="text-center mb-6">
            <p className="text-white/80 text-sm mb-1">Bienvenue chez</p>
            <h2
              className="text-2xl font-extrabold"
              style={{ background: 'linear-gradient(90deg, #EC4899, #9333EA)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
            >
              LOVA FASHION
            </h2>
            <p className="text-white/60 text-xs mt-1">Connectez-vous pour continuer</p>
          </div>

          {error && (
            <div className="mb-4 rounded-xl bg-red-500/20 border border-red-400/40 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            {/* Email */}
            <div
              className="flex items-center gap-3 rounded-2xl px-4 py-3"
              style={{ background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.2)' }}
            >
              <svg className="w-4 h-4 text-pink-300 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Adresse e-mail"
                className="flex-1 bg-transparent text-sm text-white placeholder-white/50 focus:outline-none"
              />
            </div>

            {/* Password */}
            <div
              className="flex items-center gap-3 rounded-2xl px-4 py-3"
              style={{ background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.2)' }}
            >
              <svg className="w-4 h-4 text-pink-300 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              <input
                type={showPwd ? 'text' : 'password'}
                autoComplete="current-password"
                required
                value={mot_de_passe}
                onChange={(e) => setMotDePasse(e.target.value)}
                placeholder="Mot de passe"
                className="flex-1 bg-transparent text-sm text-white placeholder-white/50 focus:outline-none"
              />
              <button type="button" onClick={() => setShowPwd(!showPwd)} className="text-white/50 hover:text-white/80">
                {showPwd
                  ? <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 4.411m0 0L21 21" /></svg>
                  : <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                }
              </button>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-2xl py-3.5 text-sm font-bold text-white flex items-center justify-center gap-2 transition-opacity disabled:opacity-60"
              style={{ background: 'linear-gradient(90deg, #EC4899, #9333EA)' }}
            >
              {loading ? 'Connexion en cours…' : (
                <>Se connecter <span className="text-lg">→</span></>
              )}
            </button>
          </form>

          {/* Remember + forgot */}
          <div className="flex items-center justify-between mt-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="w-4 h-4 accent-pink-500 rounded"
              />
              <span className="text-xs text-white/70">Se souvenir de moi</span>
            </label>
            <button type="button" className="text-xs text-pink-400 hover:text-pink-300">
              Mot de passe oublié ?
            </button>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.2)' }} />
            <span className="text-xs text-white/40">ou</span>
            <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.2)' }} />
          </div>

          {/* Register */}
          <Link
            to="/register"
            className="flex items-center justify-center gap-2 w-full rounded-2xl py-3 text-sm font-semibold transition"
            style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.25)', color: 'white' }}
          >
            <svg className="w-4 h-4 text-pink-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
            </svg>
            Créer un compte
          </Link>

          {/* Legal */}
          <p className="text-center text-xs text-white/40 mt-4">
            En continuant, vous acceptez nos{' '}
            <span className="text-pink-400 cursor-pointer hover:underline">Conditions d&apos;utilisation</span>
            {' '}et notre{' '}
            <span className="text-pink-400 cursor-pointer hover:underline">Politique de confidentialité</span>
          </p>
        </div>
      </div>
    </div>
  );
}
