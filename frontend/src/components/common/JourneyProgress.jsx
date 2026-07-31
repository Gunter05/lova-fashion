/**
 * JourneyProgress — barre de progression du parcours client
 *
 * Affiche les 5 étapes clés (Mesures → Catalogue → Aisance → Compatibilité → Rapport)
 * avec indication visuelle de l'étape active et des étapes complétées.
 * Les étapes complétées sont cliquables pour revenir en arrière.
 */
import { useNavigate, useLocation } from 'react-router-dom';
import { useFlow } from '../../context/FlowContext';

const STEPS = [
  { label: 'Mesures',   short: '1', path: '/modules/2' },
  { label: 'Catalogue', short: '2', path: '/modules/3' },
  { label: 'Aisance',   short: '3', path: '/modules/5' },
  { label: 'Compat.',   short: '4', path: '/modules/6' },
  { label: 'Rapport',   short: '5', path: '/modules/7' },
];

function activeIndex(pathname) {
  if (pathname.includes('/modules/2')) return 0;
  if (pathname.includes('/modules/3') || pathname.includes('/modules/4')) return 1;
  if (pathname.includes('/modules/5')) return 2;
  if (pathname.includes('/modules/6')) return 3;
  if (pathname.includes('/modules/7')) return 4;
  return -1;
}

function completedSteps(flow) {
  const done = new Set();
  if (flow.sessionId)      done.add(0);
  if (flow.fabricId)       done.add(1);
  if (flow.adjustmentId)   done.add(2);
  if (flow.verificationId) done.add(3);
  return done;
}

export default function JourneyProgress() {
  const navigate     = useNavigate();
  const { pathname } = useLocation();
  const { flow }     = useFlow();

  const current   = activeIndex(pathname);
  const completed = completedSteps(flow);

  // Masqué sur les pages non-modulaires (profil, etc.)
  if (current === -1) return null;

  return (
    <div className="mb-3">
      {/* Étapes + connecteurs */}
      <div className="flex items-start">
        {STEPS.map((step, i) => {
          const isDone      = completed.has(i);
          const isActive    = i === current;
          const isLast      = i === STEPS.length - 1;
          const isReachable = i === 0 || completed.has(i - 1) || isDone || isActive;

          return (
            <div key={step.path} className="flex items-start flex-1 min-w-0">
              {/* Nœud + label */}
              <div className="flex flex-col items-center shrink-0" style={{ width: 28 }}>
                <button
                  onClick={() => isReachable && navigate(step.path)}
                  disabled={!isReachable}
                  title={step.label}
                  aria-label={`Étape ${i + 1} : ${step.label}${isDone ? ' (complétée)' : isActive ? ' (en cours)' : ''}`}
                  className={[
                    'w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold transition-all',
                    isActive
                      ? 'bg-[#D95D39] text-white shadow ring-2 ring-[#D95D39]/25'
                      : isDone
                      ? 'bg-[#4E6E58] text-white'
                      : isReachable
                      ? 'bg-[#F0EDE8] text-gray-500 hover:bg-[#E8E4DF]'
                      : 'bg-[#F0EDE8] text-gray-300 cursor-not-allowed',
                  ].join(' ')}
                >
                  {isDone && !isActive ? (
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    step.short
                  )}
                </button>
                <span
                  className={[
                    'text-[9px] mt-1 text-center leading-tight font-medium',
                    isActive ? 'text-[#D95D39]' : isDone ? 'text-[#4E6E58]' : 'text-gray-300',
                  ].join(' ')}
                  style={{ maxWidth: 40 }}
                >
                  {step.label}
                </span>
              </div>

              {/* Ligne de connexion */}
              {!isLast && (
                <div className="flex-1 mx-1 mt-3.5">
                  <div
                    className="h-[2px] w-full rounded-full transition-all"
                    style={{
                      background: isDone
                        ? '#4E6E58'
                        : isActive
                        ? 'linear-gradient(90deg, #D95D39 40%, #F0EDE8 40%)'
                        : '#F0EDE8',
                    }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
