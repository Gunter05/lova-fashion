# Design: Frontend Global Architecture

## Architecture des dossiers (`/frontend/src/`)

```text
src/
├── api/
│   ├── client.js              # Instance Axios + Intercepteurs JWT
│   └── auth.js                # Endpoints Login / Register
├── components/
│   ├── layout/
│   │   ├── AppLayout.jsx      # Wrapper Sidebar + Navbar
│   │   ├── Sidebar.jsx        # Navigation principale (Modules 1 à 7)
│   │   └── Navbar.jsx         # Barre supérieure (Profil + Logout)
│   └── common/
│       ├── ProtectedRoute.jsx # HOC de protection des routes
│       └── ModulePlaceholder.jsx # Composant générique d'attente
├── context/
│   └── AuthContext.jsx        # État global utilisateur & session JWT
├── modules/
│   ├── auth/                  # Pages LoginPage.jsx & RegisterPage.jsx
│   └── module_7_report/      # Composants et pages du Module 7
├── App.jsx                    # Configuration des routes (React Router)
└── main.jsx