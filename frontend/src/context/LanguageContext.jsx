/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useCallback } from 'react';
import { translations } from './translations';

const LANGUAGE_KEY = 'lova_lang';

const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [locale, setLocale] = useState(() => {
    return localStorage.getItem(LANGUAGE_KEY) || 'en';
  });

  const changeLanguage = useCallback((lang) => {
    localStorage.setItem(LANGUAGE_KEY, lang);
    setLocale(lang);
  }, []);

  const t = useCallback((key, replacements = {}) => {
    const parts = key.split('.');
    let value = translations[locale];

    for (const part of parts) {
      if (value && typeof value === 'object') {
        value = value[part];
      } else {
        value = undefined;
        break;
      }
    }

    if (value === undefined) {
      // Fallback to English
      let fallbackValue = translations['en'];
      for (const part of parts) {
        if (fallbackValue && typeof fallbackValue === 'object') {
          fallbackValue = fallbackValue[part];
        } else {
          fallbackValue = undefined;
          break;
        }
      }
      value = fallbackValue !== undefined ? fallbackValue : key;
    }

    if (typeof value === 'string') {
      let result = value;
      Object.keys(replacements).forEach((k) => {
        result = result.replaceAll(`{${k}}`, replacements[k]);
      });
      return result;
    }

    return value;
  }, [locale]);

  return (
    <LanguageContext.Provider value={{ locale, changeLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export const useLanguage = () => {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error('useLanguage must be used inside a <LanguageProvider>');
  }
  return ctx;
};
