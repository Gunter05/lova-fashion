# Implementation Plan: Frontend Global Architecture

## Overview

Implements the global frontend architecture for LOVA FASHION: Vite + React + Tailwind CSS scaffold, HTTP client with JWT interceptor, AuthContext, authentication pages, shared layout with sidebar navigation, protected routing, and integration of Module 7.

## Tasks

- [x] 1. Scaffold Vite+React project & setup Tailwind CSS
  - Run `npm create vite@latest . -- --template react` inside `frontend/`
  - Install and configure Tailwind CSS v3
  - Install Axios and React Router DOM
  - Requirements: NFR (React, Vite, Tailwind CSS, Axios)

- [x] 2. Setup HTTP client & AuthContext
  - Depends on: 1
  - Create `src/api/client.js` — Axios instance with base URL from env + JWT Bearer interceptor
  - Create `src/api/auth.js` — login and register endpoint functions
  - Create `src/context/AuthContext.jsx` — React context with user state, login/logout, token persistence in localStorage
  - Requirements: NFR (Axios, Context API, JWT)

- [x] 3. Authentication views
  - Depends on: 2
  - Create `src/modules/auth/LoginPage.jsx` — Tailwind form, calls `authApi.login`, stores token via AuthContext
  - Create `src/modules/auth/RegisterPage.jsx` — Tailwind form, calls `authApi.register`
  - Requirements: User Story 1

- [x] 4. Layout & global navigation
  - Depends on: 2
  - Create `src/components/layout/Sidebar.jsx` — links for Modules 1–7
  - Create `src/components/layout/Navbar.jsx` — profile name + logout button
  - Create `src/components/layout/AppLayout.jsx` — wraps Sidebar + Navbar + Outlet
  - Create `src/components/common/ProtectedRoute.jsx` — redirects unauthenticated users to /login
  - Create `src/components/common/ModulePlaceholder.jsx` — generic "coming soon" component for modules not yet integrated
  - Requirements: User Stories 2, 3

- [x] 5. App.jsx routing & Module 7 integration
  - Depends on: 3, 4
  - Configure `src/App.jsx` with React Router: public routes (/login, /register) and protected routes under AppLayout
  - Create stub `src/modules/module_7_report/ReportPage.jsx` wired to `/modules/7`
  - Mount ModulePlaceholder on routes for Modules 1–6
  - Requirements: User Stories 2, 3; NFR (React Router)

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"] },
    { "wave": 2, "tasks": ["2"] },
    { "wave": 3, "tasks": ["3", "4"] },
    { "wave": 4, "tasks": ["5"] }
  ]
}
```

## Notes

- The Vite dev server proxies `/api` requests to the backend (configurable via `vite.config.js`).
- JWT token is stored in `localStorage` under the key `lova_token`.
- ModulePlaceholder accepts a `moduleNumber` and `moduleName` prop for display.
- The frontend lives in `frontend/` — all paths above are relative to `frontend/`.
