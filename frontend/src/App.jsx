import { Navigate, Route, Routes } from 'react-router-dom';

import AppLayout        from './components/layout/AppLayout';
import ProtectedRoute   from './components/common/ProtectedRoute';

import LoginPage        from './modules/auth/LoginPage';
import RegisterPage     from './modules/auth/RegisterPage';

import ProfilePage      from './modules/module_1_profile/ProfilePage';
import MeasurementsPage from './modules/module_2_measurements/MeasurementsPage';
import FabricCatalogPage  from './modules/module_3_fabric/FabricCatalogPage';
import PatternCatalogPage from './modules/module_4_pattern/PatternCatalogPage';
import EaseMarginsPage  from './modules/module_5_ease/EaseMarginsPage';
import CompatibilityPage  from './modules/module_6_compatibility/CompatibilityPage';
import ReportPage       from './modules/module_7_report/ReportPage';

export default function App() {
  return (
    <Routes>
      <Route path="/login"    element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/modules/7" replace />} />
          <Route path="modules/1" element={<ProfilePage />} />
          <Route path="modules/2" element={<MeasurementsPage />} />
          <Route path="modules/3" element={<FabricCatalogPage />} />
          <Route path="modules/4" element={<PatternCatalogPage />} />
          <Route path="modules/5" element={<EaseMarginsPage />} />
          <Route path="modules/6" element={<CompatibilityPage />} />
          <Route path="modules/7" element={<ReportPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
