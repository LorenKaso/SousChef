import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { deleteRecipe, fetchFavorites, removeFavorite } from '../api/client';
import RecipeGrid from '../components/RecipeGrid';
import type { Recipe } from '../types/recipe';

export default function FavoritesPage() {
  const navigate = useNavigate();
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Recipe | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadFavorites();
  }, []);

  async function loadFavorites() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFavorites();
      setRecipes(data);
    } catch {
      setError('Could not load favorites. Is the backend running?');
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteRecipe(deleteTarget.id);
      setRecipes((prev) => prev.filter((r) => r.id !== deleteTarget.id));
    } catch {
      // leave list unchanged on error
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  }

  // Every recipe on this page IS a favorite, so toggling always means removing.
  // Optimistically remove from the list; revert if the API call fails.
  async function handleFavoriteRemove(recipe: Recipe) {
    setRecipes((prev) => prev.filter((r) => r.id !== recipe.id));
    try {
      await removeFavorite(recipe.id);
    } catch {
      // Revert: put the recipe back at the front
      setRecipes((prev) => [recipe, ...prev]);
    }
  }

  // All recipes shown here are favorited — pass a Set of all their ids
  const allFavoriteIds = new Set(recipes.map((r) => r.id));

  return (
    <main className="max-w-5xl mx-auto px-6 py-8">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-extrabold text-stone-800">Favorites</h1>
        {!loading && !error && (
          <p className="text-sm text-stone-400 mt-0.5">
            {recipes.length} saved recipe{recipes.length !== 1 ? 's' : ''}
          </p>
        )}
      </div>

      {/* States */}
      {loading && (
        <div className="text-center py-24 text-stone-400">
          Loading favorites…
        </div>
      )}
      {error && (
        <div className="text-center py-24 text-rose-400">{error}</div>
      )}
      {!loading && !error && (
        <RecipeGrid
          recipes={recipes}
          emptyMessage="No favorites yet. Tap the ♡ on any recipe to save it here."
          favoriteIds={allFavoriteIds}
          onCardClick={(recipe) => navigate(`/recipes/${recipe.id}`)}
          onFavoriteToggle={handleFavoriteRemove}
          onDeleteRequest={(recipe) => setDeleteTarget(recipe)}
        />
      )}

      {deleteTarget !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => !deleting && setDeleteTarget(null)}
        >
          <div
            className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold text-stone-800 mb-1">
              Delete recipe?
            </h2>
            <p className="text-sm text-stone-500 mb-5">
              <span className="font-medium text-stone-700">{deleteTarget.title}</span>
              {' '}will be permanently removed. This cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                className="px-4 py-2 text-sm font-medium text-stone-600 bg-stone-100 hover:bg-stone-200 rounded-xl transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteConfirm}
                disabled={deleting}
                className="px-4 py-2 text-sm font-medium text-white bg-rose-500 hover:bg-rose-600 rounded-xl transition-colors disabled:opacity-50"
              >
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
