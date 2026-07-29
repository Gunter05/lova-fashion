/**
 * PatternCatalogPage — redirects to the combined Catalogue page (Module 3)
 * which handles both models (MODÈLES tab) and fabrics (TISSUS tab).
 */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function PatternCatalogPage() {
  const navigate = useNavigate();
  useEffect(() => { navigate('/modules/3', { replace: true }); }, [navigate]);
  return null;
}
