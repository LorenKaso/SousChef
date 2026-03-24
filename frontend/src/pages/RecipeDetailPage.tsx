import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  addFavorite,
  fetchFavorites,
  fetchRecipe,
  removeFavorite,
  startVoiceSession,
  stopVoiceSession,
} from '../api/client';
import type { Recipe, RecipeSection, Session } from '../types/recipe';
import { useVoiceSession } from '../hooks/useVoiceSession';

// ── Fraction formatting ───────────────────────────────────────────────────────

const COOKING_FRACS: [number, string][] = [
  [1 / 8, '1/8'],
  [1 / 4, '1/4'],
  [1 / 3, '1/3'],
  [3 / 8, '3/8'],
  [1 / 2, '1/2'],
  [5 / 8, '5/8'],
  [2 / 3, '2/3'],
  [3 / 4, '3/4'],
  [7 / 8, '7/8'],
];

function formatFraction(value: number): string {
  if (value <= 0) return String(value);
  const whole = Math.floor(value);
  const frac = value - whole;
  if (frac < 0.005) return String(whole);

  let bestLabel = '';
  let minDiff = Infinity;
  for (const [f, label] of COOKING_FRACS) {
    const diff = Math.abs(frac - f);
    if (diff < minDiff) {
      minDiff = diff;
      bestLabel = label;
    }
  }

  if (minDiff > 0.02) return String(value);
  return whole > 0 ? `${whole} ${bestLabel}` : bestLabel;
}

// ── localStorage helpers ──────────────────────────────────────────────────────

interface StoredSession {
  sessionId: string;
  voiceSessionId: string;
  session: Session;
  status: 'active' | 'paused';
}

function storageKey(recipeId: string) {
  return `souschef_session_${recipeId}`;
}

function loadStoredSession(recipeId: string): StoredSession | null {
  try {
    const raw = localStorage.getItem(storageKey(recipeId));
    return raw ? (JSON.parse(raw) as StoredSession) : null;
  } catch {
    return null;
  }
}

function saveStoredSession(recipeId: string, value: StoredSession) {
  localStorage.setItem(storageKey(recipeId), JSON.stringify(value));
}

function clearStoredSession(recipeId: string) {
  localStorage.removeItem(storageKey(recipeId));
}

// ── Step/ingredient status ────────────────────────────────────────────────────

type ItemStatus = 'none' | 'done' | 'current' | 'pending';

function ingredientStatus(
  session: Session | null,
  sectionIdx: number,
  ingIdx: number,
  section: RecipeSection,
): ItemStatus {
  if (session === null) return 'none';

  const cur = session.current_section_index;
  if (sectionIdx < cur) return 'done';
  if (sectionIdx > cur) return 'pending';

  const { current_phase, current_item_index } = session;

  if (section.execution_flow !== null) {
    const flowIdx = section.execution_flow.findIndex(
      (fi) => fi.type === 'ingredient' && fi.index === ingIdx,
    );
    if (flowIdx === -1) return 'none';
    if (flowIdx < current_item_index) return 'done';
    if (flowIdx === current_item_index) return 'current';
    return 'pending';
  }

  // Classic mode
  if (current_phase === 'steps') return 'done';
  if (ingIdx < current_item_index) return 'done';
  if (ingIdx === current_item_index) return 'current';
  return 'pending';
}

function stepStatus(
  session: Session | null,
  sectionIdx: number,
  stepIdx: number,
  section: RecipeSection,
): ItemStatus {
  if (session === null) return 'none';

  const cur = session.current_section_index;
  if (sectionIdx < cur) return 'done';
  if (sectionIdx > cur) return 'pending';

  const { current_phase, current_item_index } = session;

  if (section.execution_flow !== null) {
    const flowIdx = section.execution_flow.findIndex(
      (fi) => fi.type === 'step' && fi.index === stepIdx,
    );
    if (flowIdx === -1) return 'none';
    if (flowIdx < current_item_index) return 'done';
    if (flowIdx === current_item_index) return 'current';
    return 'pending';
  }

  // Classic mode
  if (current_phase === 'ingredients') return 'pending';
  if (stepIdx < current_item_index) return 'done';
  if (stepIdx === current_item_index) return 'current';
  return 'pending';
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function RecipeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFavorited, setIsFavorited] = useState<boolean | null>(null);

  // Cooking session state
  const [session, setSession] = useState<Session | null>(null);
  const [voiceSessionId, setVoiceSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<'active' | 'paused' | null>(null);
  const [sessionStarting, setSessionStarting] = useState(false);

  // Voice session — always-listening, wake-word ("Su") activated.
  const isHebrew = recipe !== null && /[\u0590-\u05FF]/.test(recipe.title);
  const { voiceState, debug } = useVoiceSession({
    voiceSessionId,
    active: sessionStatus === 'active',
    isHebrew,
    onSessionUpdate: (updatedSession) => {
      setSession(updatedSession);
      if (id && voiceSessionId) {
        saveStoredSession(id, {
          sessionId: updatedSession.id,
          voiceSessionId,
          session: updatedSession,
          status: 'active',
        });
      }
    },
  });

  // Load recipe + favorites, then restore any paused session from localStorage.
  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [data, favorites] = await Promise.all([
          fetchRecipe(id!),
          fetchFavorites().catch(() => [] as Recipe[]),
        ]);
        if (!cancelled) {
          setRecipe(data);
          setIsFavorited(favorites.some((f) => f.id === id));

          // Restore paused session if one exists for this recipe.
          const stored = loadStoredSession(id!);
          if (stored) {
            setSession(stored.session);
            setVoiceSessionId(stored.voiceSessionId);
            setSessionStatus(stored.status);
          }
        }
      } catch {
        if (!cancelled) setError('Recipe not found.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [id]);

  async function handleFavoriteToggle() {
    if (!id || isFavorited === null) return;
    const next = !isFavorited;
    setIsFavorited(next);
    try {
      if (next) await addFavorite(id);
      else await removeFavorite(id);
    } catch {
      setIsFavorited(!next);
    }
  }

  async function handleStartRecipe() {
    if (!id || sessionStarting) return;
    setSessionStarting(true);
    try {
      const response = await startVoiceSession(id);
      const recipeSession = response.recipe_session;
      const vSessionId = response.voice_session.id;
      setSession(recipeSession);
      setVoiceSessionId(vSessionId);
      setSessionStatus('active');
      saveStoredSession(id, {
        sessionId: recipeSession.id,
        voiceSessionId: vSessionId,
        session: recipeSession,
        status: 'active',
      });
    } catch {
      // Leave the button visible so the user can retry.
    } finally {
      setSessionStarting(false);
    }
  }

  function handlePause() {
    if (!id || !session || !voiceSessionId) return;
    const next = sessionStatus === 'paused' ? 'active' : 'paused';
    setSessionStatus(next);
    saveStoredSession(id, { sessionId: session.id, voiceSessionId, session, status: next });
  }

  async function handleEndRecipe() {
    if (!id) return;
    if (voiceSessionId) {
      try {
        await stopVoiceSession(voiceSessionId);
      } catch {
        // best-effort: clear local state even if the server call fails
      }
    }
    clearStoredSession(id);
    setSession(null);
    setVoiceSessionId(null);
    setSessionStatus(null);
  }

  return (
    <main className="max-w-3xl mx-auto px-6 py-8">
      {/* Back navigation */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1 text-sm text-stone-500 hover:text-stone-800 mb-8 transition-colors"
      >
        ← Back
      </button>

      {loading && (
        <div className="text-center py-24 text-stone-400">Loading recipe…</div>
      )}

      {error && (
        <div className="text-center py-24 text-rose-400">{error}</div>
      )}

      {!loading && !error && recipe && (
        <>
          {/* Header — title + favorite toggle */}
          <div className="mb-8 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-stone-800 leading-tight">
                {recipe.title}
              </h1>
              <p className="text-sm text-stone-400 mt-1.5">
                {recipe.servings} serving{recipe.servings !== 1 ? 's' : ''}
              </p>
            </div>

            {isFavorited !== null && (
              <button
                onClick={handleFavoriteToggle}
                aria-label={isFavorited ? 'Remove from favorites' : 'Add to favorites'}
                className={`mt-1 text-3xl leading-none transition-colors duration-150 ${
                  isFavorited
                    ? 'text-rose-500 hover:text-rose-600'
                    : 'text-stone-300 hover:text-rose-400'
                }`}
              >
                {isFavorited ? '♥' : '♡'}
              </button>
            )}
          </div>

          {/* Paused banner */}
          {sessionStatus === 'paused' && (
            <div className="mb-6 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-700 text-center">
              Recipe paused — tap Resume to continue from where you left off.
            </div>
          )}

          {/* Sections */}
          <div className="space-y-6">
            {recipe.sections.map((section, sectionIdx) => (
              <div
                key={sectionIdx}
                className="bg-white rounded-2xl border border-stone-100 shadow-sm p-6"
              >
                {recipe.sections.length > 1 && (
                  <h2 className="text-base font-semibold text-stone-700 mb-5">
                    {section.name}
                  </h2>
                )}

                {/* Ingredients */}
                {section.ingredients.length > 0 && (
                  <div className="mb-6">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-stone-400 mb-3">
                      Ingredients
                    </h3>
                    <ul className="space-y-2">
                      {section.ingredients.map((ing, ingIdx) => {
                        const status = ingredientStatus(session, sectionIdx, ingIdx, section);
                        return (
                          <li
                            key={ingIdx}
                            className={`flex items-baseline gap-2 text-sm transition-colors ${
                              status === 'current'
                                ? 'text-amber-700 font-semibold'
                                : status === 'done'
                                  ? 'text-stone-300 line-through'
                                  : 'text-stone-700'
                            }`}
                          >
                            <span className={`shrink-0 select-none ${
                              status === 'current' ? 'text-amber-400' : 'text-stone-300'
                            }`}>
                              {status === 'current' ? '▶' : '·'}
                            </span>
                            <span>
                              <span className="font-medium">
                                {formatFraction(ing.amount)} {ing.unit}
                              </span>{' '}
                              {ing.name}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}

                {/* Steps */}
                {section.steps.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-stone-400 mb-3">
                      Steps
                    </h3>
                    <ol className="space-y-4">
                      {section.steps.map((step, stepIdx) => {
                        const status = stepStatus(session, sectionIdx, stepIdx, section);
                        return (
                          <li key={stepIdx} className="flex gap-3">
                            <span className={`shrink-0 w-5 h-5 rounded-full text-xs font-bold flex items-center justify-center mt-0.5 ${
                              status === 'current'
                                ? 'bg-amber-500 text-white'
                                : status === 'done'
                                  ? 'bg-stone-100 text-stone-300'
                                  : 'bg-amber-100 text-amber-600'
                            }`}>
                              {stepIdx + 1}
                            </span>
                            <p className={`text-sm leading-relaxed ${
                              status === 'current'
                                ? 'text-stone-900 font-medium'
                                : status === 'done'
                                  ? 'text-stone-300'
                                  : 'text-stone-700'
                            }`}>
                              {step.text}
                            </p>
                          </li>
                        );
                      })}
                    </ol>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Voice state indicator */}
          {session !== null && voiceState !== 'off' && (
            <p className="mt-8 text-center text-xs text-stone-400 tracking-wide">
              {voiceState === 'passive'   && 'Say "Su" to speak…'}
              {voiceState === 'capturing' && 'Listening…'}
              {voiceState === 'sending'   && 'Thinking…'}
              {voiceState === 'speaking'  && 'Speaking…'}
            </p>
          )}

          {/* ── TEMP DEBUG PANEL — remove once voice is confirmed working ── */}
          {session !== null && (
            <div className="mt-4 mx-auto max-w-md rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-stone-600 space-y-1">
              <p className="font-semibold text-amber-700">Voice debug</p>
              <p>State: <span className="font-mono">{voiceState}</span></p>
              <p>SR supported:{' '}
                <span className={debug.srSupported === false ? 'text-rose-600 font-bold' : ''}>
                  {debug.srSupported === null ? '(checking)' : String(debug.srSupported)}
                </span>
              </p>
              <p>Last transcript: <span className="font-mono">{debug.lastTranscript || '—'}</span></p>
              <p>Wake word matched: <span className="font-mono">{String(debug.wakeMatched)}</span></p>
              {debug.lastError && (
                <p className="text-rose-600 font-semibold">Error: {debug.lastError}</p>
              )}
            </div>
          )}
          {/* ── END TEMP DEBUG PANEL ── */}

          {/* Session controls */}
          <div className="mt-4 flex justify-center gap-4">
            {session === null ? (
              <button
                onClick={handleStartRecipe}
                disabled={sessionStarting}
                className="px-10 py-3 text-base font-semibold text-white bg-amber-500 hover:bg-amber-600 disabled:opacity-50 rounded-2xl shadow-sm transition-colors"
              >
                {sessionStarting ? 'Starting…' : 'Start Recipe'}
              </button>
            ) : (
              <>
                <button
                  onClick={handlePause}
                  className="px-8 py-3 text-base font-semibold text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-2xl transition-colors"
                >
                  {sessionStatus === 'paused' ? 'Resume' : 'Pause'}
                </button>
                <button
                  onClick={handleEndRecipe}
                  className="px-8 py-3 text-base font-semibold text-stone-600 bg-stone-100 hover:bg-stone-200 rounded-2xl transition-colors"
                >
                  End Recipe
                </button>
              </>
            )}
          </div>
        </>
      )}
    </main>
  );
}
