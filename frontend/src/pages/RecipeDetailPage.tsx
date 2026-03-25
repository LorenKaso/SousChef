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
import type { Ingredient, Recipe, RecipeSection, Session, Step, Timer } from '../types/recipe';
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

// ── Guided-state helpers ──────────────────────────────────────────────────────

function formatIngredientInstruction(ing: Ingredient): string {
  const amt = formatFraction(ing.amount);
  if (!ing.unit || ing.unit.toLowerCase() === 'unit') return `Add ${amt} ${ing.name}`;
  return `Add ${amt} ${ing.unit} of ${ing.name}`;
}

interface GuidedCurrent {
  sectionIdx: number;
  sectionName: string;
  phase: 'ingredients' | 'steps';
  item: Ingredient | Step;
}

/**
 * Derives the current guided item purely from backend session state + recipe.
 * Returns 'complete' when the whole recipe is done, null when state is mid-transition.
 */
function getCurrentGuidedItem(
  session: Session,
  recipe: Recipe,
): GuidedCurrent | 'complete' | null {
  const sectionIdx = session.current_section_index;
  if (sectionIdx >= recipe.sections.length) return 'complete';

  const section = recipe.sections[sectionIdx];
  const { current_phase, current_item_index } = session;

  if (section.execution_flow !== null) {
    if (current_item_index >= section.execution_flow.length) return 'complete';
    const fi = section.execution_flow[current_item_index];
    const phase: 'ingredients' | 'steps' = fi.type === 'ingredient' ? 'ingredients' : 'steps';
    const item: Ingredient | Step =
      fi.type === 'ingredient' ? section.ingredients[fi.index] : section.steps[fi.index];
    return { sectionIdx, sectionName: section.name, phase, item };
  }

  if (current_phase === 'ingredients') {
    if (current_item_index >= section.ingredients.length) return null;
    return {
      sectionIdx,
      sectionName: section.name,
      phase: 'ingredients',
      item: section.ingredients[current_item_index],
    };
  }

  if (current_item_index >= section.steps.length) return null;
  return {
    sectionIdx,
    sectionName: section.name,
    phase: 'steps',
    item: section.steps[current_item_index],
  };
}

/** First guided item of the section at `sectionIdx`, or null if none. */
function firstItemOfSection(recipe: Recipe, sectionIdx: number): GuidedCurrent | null {
  if (sectionIdx >= recipe.sections.length) return null;
  const section = recipe.sections[sectionIdx];
  if (section.execution_flow !== null && section.execution_flow.length > 0) {
    const fi = section.execution_flow[0];
    const phase: 'ingredients' | 'steps' = fi.type === 'ingredient' ? 'ingredients' : 'steps';
    const item: Ingredient | Step =
      fi.type === 'ingredient' ? section.ingredients[fi.index] : section.steps[fi.index];
    return { sectionIdx, sectionName: section.name, phase, item };
  }
  if (section.ingredients.length > 0)
    return { sectionIdx, sectionName: section.name, phase: 'ingredients', item: section.ingredients[0] };
  if (section.steps.length > 0)
    return { sectionIdx, sectionName: section.name, phase: 'steps', item: section.steps[0] };
  return null;
}

/**
 * Returns the item that comes immediately after the current one, without
 * mutating session state. Returns null when the recipe is on its last item.
 */
function getNextGuidedItem(session: Session, recipe: Recipe): GuidedCurrent | null {
  const sectionIdx = session.current_section_index;
  if (sectionIdx >= recipe.sections.length) return null;
  const section = recipe.sections[sectionIdx];
  const nextIdx = session.current_item_index + 1;

  if (section.execution_flow !== null) {
    if (nextIdx < section.execution_flow.length) {
      const fi = section.execution_flow[nextIdx];
      const phase: 'ingredients' | 'steps' = fi.type === 'ingredient' ? 'ingredients' : 'steps';
      const item: Ingredient | Step =
        fi.type === 'ingredient' ? section.ingredients[fi.index] : section.steps[fi.index];
      return { sectionIdx, sectionName: section.name, phase, item };
    }
    return firstItemOfSection(recipe, sectionIdx + 1);
  }

  const { current_phase } = session;
  if (current_phase === 'ingredients') {
    if (nextIdx < section.ingredients.length)
      return { sectionIdx, sectionName: section.name, phase: 'ingredients', item: section.ingredients[nextIdx] };
    if (section.steps.length > 0)
      return { sectionIdx, sectionName: section.name, phase: 'steps', item: section.steps[0] };
    return firstItemOfSection(recipe, sectionIdx + 1);
  }

  // current_phase === 'steps'
  if (nextIdx < section.steps.length)
    return { sectionIdx, sectionName: section.name, phase: 'steps', item: section.steps[nextIdx] };
  return firstItemOfSection(recipe, sectionIdx + 1);
}

function formatTimerRemaining(timer: Timer): string {
  const elapsed = (Date.now() - new Date(timer.started_at).getTime()) / 1000;
  const remaining = Math.max(0, timer.seconds - elapsed);
  const m = Math.floor(remaining / 60);
  const s = Math.floor(remaining % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
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

  // Tick every second so active-timer countdowns re-render.
  const [, setTimerTick] = useState(0);
  useEffect(() => {
    if (!session || session.active_timers.length === 0) return;
    const id = setInterval(() => setTimerTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [session?.active_timers.length ?? 0]); // eslint-disable-line react-hooks/exhaustive-deps

  // Called by useVoiceSession when the backend returns 404/409 (session gone).
  // Clears all session state so the user can tap "Start Recipe" again.
  function handleSessionInvalid() {
    console.log('[RecipeDetailPage] session invalid — clearing state');
    if (id) clearStoredSession(id);
    setSession(null);
    setVoiceSessionId(null);
    setSessionStatus(null);
  }

  // Voice session — always-listening, wake-word ("Su") activated.
  // Detect Hebrew by scanning title AND a sample of ingredients/steps so that
  // recipes with an English title but Hebrew content still get he-IL SR mode.
  const isHebrew = recipe !== null && (
    /[\u0590-\u05FF]/.test(recipe.title) ||
    recipe.sections.some(s =>
      s.ingredients.some(i => /[\u0590-\u05FF]/.test(i.name)) ||
      s.steps.some(st => /[\u0590-\u05FF]/.test(st.text))
    )
  );
  const { voiceState, debug, isActiveWindow } = useVoiceSession({
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
    onSessionInvalid: handleSessionInvalid,
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
            console.log(
              `[RestoreSession] restoring voiceSessionId=${stored.voiceSessionId} status=${stored.status}`,
            );
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
      console.log(
        `[StartRecipe] voice_session.id=${vSessionId}  recipe_session.id=${recipeSession.id}`,
      );
      setSession(recipeSession);
      setVoiceSessionId(vSessionId);
      setSessionStatus('active');
      saveStoredSession(id, {
        sessionId: recipeSession.id,
        voiceSessionId: vSessionId,
        session: recipeSession,
        status: 'active',
      });
    } catch (err) {
      // Leave the button visible so the user can retry.
      console.error('[StartRecipe] failed to start voice session:', err);
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
        className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-green-700 mb-8 transition-colors"
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
              <h1 className="text-3xl font-extrabold text-stone-800 leading-tight">
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
            <div className="mb-6 rounded-xl bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700 text-center">
              Recipe paused — tap Resume to continue from where you left off.
            </div>
          )}

          {/* ── Current action card ─────────────────────────────────── */}
          {session !== null && sessionStatus !== 'paused' && (() => {
            const guided = getCurrentGuidedItem(session, recipe);
            if (guided === 'complete') {
              return (
                <div className="mb-6 rounded-xl bg-green-600 px-5 py-4 text-center text-white">
                  <p className="text-lg font-bold">All done!</p>
                  <p className="mt-0.5 text-sm text-green-100">Recipe complete.</p>
                </div>
              );
            }
            if (!guided) return null;
            const isStep = guided.phase === 'steps';
            const itemText = isStep
              ? (guided.item as Step).text
              : formatIngredientInstruction(guided.item as Ingredient);
            const next = getNextGuidedItem(session, recipe);
            const nextText = next
              ? (next.phase === 'steps'
                  ? (next.item as Step).text
                  : formatIngredientInstruction(next.item as Ingredient))
              : null;
            return (
              <div className="mb-6 rounded-xl border-2 border-green-400 bg-green-50 px-5 py-4">
                <div className="mb-2 flex items-center gap-2">
                  {recipe.sections.length > 1 && (
                    <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-green-700">
                      {guided.sectionName}
                    </span>
                  )}
                  <span className="text-xs font-medium text-green-600">
                    {isStep ? 'Step' : 'Ingredient'}
                  </span>
                </div>
                <p className="text-base font-semibold leading-snug text-stone-800">{itemText}</p>
                {nextText && (
                  <p className="mt-3 border-t border-green-200 pt-2 text-xs text-stone-500">
                    <span className="font-medium text-stone-400">Up next:</span>{' '}
                    {nextText}
                  </p>
                )}
              </div>
            );
          })()}

          {/* ── Active timers ────────────────────────────────────────── */}
          {session !== null && session.active_timers.length > 0 && (
            <div className="mb-6 space-y-2">
              {session.active_timers.map((timer) => (
                <div
                  key={timer.id}
                  className="flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-4 py-3"
                >
                  <span className="text-sm font-medium text-amber-800">{timer.label}</span>
                  <span className="font-mono text-base font-bold text-amber-700">
                    {formatTimerRemaining(timer)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* ── Last turn log ────────────────────────────────────────── */}
          {session !== null && sessionStatus !== 'paused' && debug.lastVoiceTranscript && (
            <div className="mb-6 rounded-xl border border-stone-100 bg-white px-5 py-4 shadow-sm">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">
                Last turn
              </p>
              <div className="flex gap-2 text-sm">
                <span className="shrink-0 text-stone-400">You:</span>
                <span className="font-medium text-stone-700">{debug.lastVoiceTranscript}</span>
              </div>
              {debug.lastVoiceAnswer && (
                <div className="mt-1 flex gap-2 text-sm">
                  <span className="shrink-0 text-stone-400">Chef:</span>
                  <span className="text-stone-700">{debug.lastVoiceAnswer}</span>
                </div>
              )}
            </div>
          )}

          {/* Sections */}
          <div className="space-y-6">
            {recipe.sections.map((section, sectionIdx) => (
              <div
                key={sectionIdx}
                className={`rounded-2xl border p-6 transition-shadow duration-200 hover:shadow-md ${
                  session !== null && sectionIdx === session.current_section_index
                    ? 'border-green-200 bg-green-50/40 shadow-sm'
                    : 'border-stone-100 bg-white shadow-sm'
                }`}
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
                                ? 'text-green-700 font-semibold'
                                : status === 'done'
                                  ? 'text-stone-300 line-through'
                                  : 'text-stone-700'
                            }`}
                          >
                            <span className={`shrink-0 select-none ${
                              status === 'current' ? 'text-green-500' : 'text-stone-300'
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
                                ? 'bg-green-600 text-white'
                                : status === 'done'
                                  ? 'bg-stone-100 text-stone-300'
                                  : 'bg-green-100 text-green-700'
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
              {voiceState === 'passive'   && (isActiveWindow ? 'Listening — just speak…' : 'Say "Su" to speak…')}
              {voiceState === 'capturing' && 'Listening…'}
              {voiceState === 'sending'   && 'Thinking…'}
              {voiceState === 'speaking'  && 'Speaking…'}
            </p>
          )}

          {/* ── TEMP DEBUG PANEL — remove once voice is confirmed working ── */}
          {session !== null && (
            <div className="mt-4 mx-auto max-w-md rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-xs text-stone-600 space-y-1">
              <p className="font-semibold text-stone-500">Voice debug</p>
              <p>State: <span className="font-mono">{voiceState}</span>{isActiveWindow && <span className="ml-2 text-green-600 font-semibold">(active window)</span>}</p>
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
                className="px-10 py-3 text-base font-semibold text-white bg-green-700 hover:bg-green-800 disabled:opacity-50 rounded-2xl shadow-sm transition-colors"
              >
                {sessionStarting ? 'Starting…' : 'Start Recipe'}
              </button>
            ) : (
              <>
                <button
                  onClick={handlePause}
                  className="px-8 py-3 text-base font-semibold text-green-700 bg-green-50 hover:bg-green-100 border border-green-200 rounded-2xl transition-colors"
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
