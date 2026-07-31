/**
 * SmartHomeRedirect
 *
 * Reprend l'utilisateur là où il en était dans son parcours,
 * plutôt que de toujours renvoyer vers la même page.
 *
 * Logique :
 * - Pas de sessionId   → Mesures (point de départ)
 * - sessionId, pas fabricId → Catalogue
 * - fabricId, pas adjustmentId → Aisance
 * - adjustmentId, pas verificationId → Compatibilité
 * - verificationId → Rapport (parcours complété)
 */
import { Navigate } from 'react-router-dom';
import { useFlow } from '../../context/FlowContext';

export default function SmartHomeRedirect() {
  const { flow } = useFlow();

  if (!flow.sessionId)      return <Navigate to="/modules/2" replace />;
  if (!flow.fabricId)       return <Navigate to="/modules/3" replace />;
  if (!flow.adjustmentId)   return <Navigate to="/modules/5" replace />;
  if (!flow.verificationId) return <Navigate to="/modules/6" replace />;
  return <Navigate to="/modules/7" replace />;
}
