import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register as registerApi } from '../../api/auth';

const ROLES = [
  { value: 'Client', label: 'Client' },
  { value: 'Tailor', label: 'Tailleur' },
  { value: 'Admin', label: 'Administrateur' },
];
export default function RegisterPage() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    cni: '',
    nom: '',
    email: '',
    mot_de_passe: '',
    role: 'Client',
  });
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
        state: { message: 'Compte créé avec succès. Vous pouvez maintenant vous connecter.' },
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
            "L'inscription a échoué. Veuillez réessayer.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center px-4 py-12">
      {/* Brand */}
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-extrabold tracking-widest text-gray-900 uppercase">
          LOVA FASHION
        </h1>
        <p className="mt-1 text-sm text-gray-500">Plateforme de confection sur mesure</p>
      </div>

      {/* Card */}
      <div className="w-full max-w-md bg-white rounded-2xl shadow-md p-8">
        <h2 className="text-2xl font-bold text-gray-800 mb-6">Créer un compte</h2>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {/* CNI */}
          <div>
            <label
              htmlFor="cni"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Numéro CNI
            </label>
            <input
              id="cni"
              name="cni"
              type="text"
              autoComplete="off"
              required
              value={form.cni}
              onChange={handleChange}
              placeholder="ABC123456"
              maxLength={9}
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm text-gray-900
                         placeholder-gray-400 focus:border-gray-800 focus:outline-none focus:ring-1
                         focus:ring-gray-800 transition"
            />
          </div>

          {/* Full name */}
          <div>
            <label
              htmlFor="nom"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Nom complet
            </label>
            <input
              id="nom"
              name="nom"
              type="text"
              autoComplete="name"
              required
              value={form.nom}
              onChange={handleChange}
              placeholder="Jean Dupont"
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm text-gray-900
                         placeholder-gray-400 focus:border-gray-800 focus:outline-none focus:ring-1
                         focus:ring-gray-800 transition"
            />
          </div>

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
              name="email"
              type="email"
              autoComplete="email"
              required
              value={form.email}
              onChange={handleChange}
              placeholder="vous@exemple.com"
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm text-gray-900
                         placeholder-gray-400 focus:border-gray-800 focus:outline-none focus:ring-1
                         focus:ring-gray-800 transition"
            />
          </div>

          {/* Password */}
          <div>
            <label
              htmlFor="mot_de_passe"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Mot de passe
            </label>
            <input
              id="mot_de_passe"
              name="mot_de_passe"
              type="password"
              autoComplete="new-password"
              required
              value={form.mot_de_passe}
              onChange={handleChange}
              placeholder="••••••••"
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm text-gray-900
                         placeholder-gray-400 focus:border-gray-800 focus:outline-none focus:ring-1
                         focus:ring-gray-800 transition"
            />
          </div>

          {/* Role */}
          <div>
            <label
              htmlFor="role"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Rôle
            </label>
            <select
              id="role"
              name="role"
              required
              value={form.role}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm text-gray-900
                         focus:border-gray-800 focus:outline-none focus:ring-1 focus:ring-gray-800
                         bg-white transition"
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-semibold text-white
                       hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-800
                       focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {loading ? 'Création en cours…' : "Créer mon compte"}
          </button>
        </form>

        {/* Footer link */}
        <p className="mt-6 text-center text-sm text-gray-500">
          Déjà un compte ?{' '}
          <Link
            to="/login"
            className="font-medium text-gray-900 underline underline-offset-2 hover:text-gray-600"
          >
            Se connecter
          </Link>
        </p>
      </div>
    </div>
  );
}
