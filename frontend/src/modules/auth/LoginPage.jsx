import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { login as loginApi } from '../../api/auth';
import { useAuth } from '../../context/AuthContext';

export default function LoginPage() {
  const navigate = useNavigate();
  const auth = useAuth();

  const [email, setEmail] = useState('');
  const [mot_de_passe, setMotDePasse] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await loginApi(email, mot_de_passe);
      const { access_token } = response.data;
      // Store token first so the profile request can authenticate
      auth.login(null, access_token);
      // Fetch full user profile
      const { getMyProfile } = await import('../../api/modules');
      const profileRes = await getMyProfile();
      auth.login(profileRes.data, access_token);
      navigate('/');
    } catch (err) {
      const message =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        'Identifiants incorrects. Veuillez réessayer.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center px-4">
      {/* Brand */}
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-extrabold tracking-widest text-gray-900 uppercase">
          LOVA FASHION
        </h1>
        <p className="mt-1 text-sm text-gray-500">Plateforme de confection sur mesure</p>
      </div>

      {/* Card */}
      <div className="w-full max-w-md bg-white rounded-2xl shadow-md p-8">
        <h2 className="text-2xl font-bold text-gray-800 mb-6">Connexion</h2>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {/* Email */}
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Adresse e-mail
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="vous@exemple.com"
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm text-gray-900
                         placeholder-gray-400 focus:border-gray-800 focus:outline-none focus:ring-1
                         focus:ring-gray-800 transition"
            />
          </div>

          {/* Password */}
          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Mot de passe
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={mot_de_passe}
              onChange={(e) => setMotDePasse(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm text-gray-900
                         placeholder-gray-400 focus:border-gray-800 focus:outline-none focus:ring-1
                         focus:ring-gray-800 transition"
            />
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-semibold text-white
                       hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-800
                       focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {loading ? 'Connexion en cours…' : 'Se connecter'}
          </button>
        </form>

        {/* Footer link */}
        <p className="mt-6 text-center text-sm text-gray-500">
          Pas encore de compte ?{' '}
          <Link
            to="/register"
            className="font-medium text-gray-900 underline underline-offset-2 hover:text-gray-600"
          >
            S&apos;inscrire
          </Link>
        </p>
      </div>
    </div>
  );
}
