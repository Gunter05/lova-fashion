/**
 * FlowContext — parcours utilisateur global
 *
 * Persiste les IDs clés entre les modules pour éviter à l'utilisateur
 * de resélectionner tissu / session / patron à chaque étape.
 *
 * Stockage : localStorage (survit aux rechargements de page)
 */
import { createContext, useContext, useState, useCallback } from 'react';

const STORAGE_KEY = 'lova_flow';

const DEFAULT_FLOW = {
  sessionId:    null, // session de mesures (Module 2)
  fabricId:     null, // tissu choisi (Module 3)
  fabricName:   null, // pour affichage
  modelId:      null, // patron choisi (Module 4)
  modelName:    null, // pour affichage
  adjustmentId: null, // ajustement d'aisance (Module 5)
  verificationId: null, // résultat compatibilité (Module 6)
};

const readStorage = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULT_FLOW, ...JSON.parse(raw) } : { ...DEFAULT_FLOW };
  } catch {
    return { ...DEFAULT_FLOW };
  }
};

const FlowContext = createContext(null);

export function FlowProvider({ children }) {
  const [flow, setFlowState] = useState(readStorage);

  const setFlow = useCallback((patch) => {
    setFlowState((prev) => {
      const next = { ...prev, ...patch };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const resetFlow = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setFlowState({ ...DEFAULT_FLOW });
  }, []);

  return (
    <FlowContext.Provider value={{ flow, setFlow, resetFlow }}>
      {children}
    </FlowContext.Provider>
  );
}

export const useFlow = () => {
  const ctx = useContext(FlowContext);
  if (!ctx) throw new Error('useFlow must be used inside <FlowProvider>');
  return ctx;
};

export default FlowContext;
