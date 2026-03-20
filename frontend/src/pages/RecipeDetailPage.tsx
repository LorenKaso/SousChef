import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { addFavorite, fetchFavorites, fetchRecipe, removeFavorite } from '../api/client';
import type { Recipe } from '../types/recipe';

export default function RecipeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // null = not yet loaded; true/false = known state
  const [isFavorited, setIsFavorited] = useState<boolean | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        // Fetch recipe and favorites in parallel
        const [data, favorites] = await Promise.all([
          fetchRecipe(id!),
          fetchFavorites().catch(() => [] as Recipe[]),
        ]);
        if (!cancelled) {
          setRecipe(data);
          setIsFavorited(favorites.some((f) => f.id === id));
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
    setIsFavorited(next); // optimistic
    try {
      if (next) {
        await addFavorite(id);
      } else {
        await removeFavorite(id);
      }
    } catch {
      setIsFavorited(!next); // revert
    }
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

            {/* Heart toggle — shown once we know the favorited state */}
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

          {/* Sections */}
          <div className="space-y-6">
            {recipe.sections.map((section, sectionIdx) => (
              <div
                key={sectionIdx}
                className="bg-white rounded-2xl border border-stone-100 shadow-sm p-6"
              >
                {/* Section name — only shown when there are multiple sections */}
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
                      {section.ingredients.map((ing, ingIdx) => (
                        <li
                          key={ingIdx}
                          className="flex items-baseline gap-2 text-sm text-stone-700"
                        >
                          <span className="shrink-0 text-stone-300 select-none">
                            ·
                          </span>
                          <span>
                            <span className="font-medium">
                              {ing.amount} {ing.unit}
                            </span>{' '}
                            {ing.name}
                          </span>
                        </li>
                      ))}
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
                      {section.steps.map((step, stepIdx) => (
                        <li key={stepIdx} className="flex gap-3">
                          <span className="shrink-0 w-5 h-5 rounded-full bg-amber-100 text-amber-600 text-xs font-bold flex items-center justify-center mt-0.5">
                            {stepIdx + 1}
                          </span>
                          <p className="text-sm text-stone-700 leading-relaxed">
                            {step.text}
                          </p>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Start Recipe CTA — wired in Phase 3 */}
          <div className="mt-10 flex justify-center">
            <button
              className="px-10 py-3 text-base font-semibold text-white bg-amber-500 hover:bg-amber-600 rounded-2xl shadow-sm transition-colors"
              onClick={() => {
                // Phase 3: navigate to cooking/voice session for this recipe
              }}
            >
              Start Recipe
            </button>
          </div>
        </>
      )}
    </main>
  );
}
