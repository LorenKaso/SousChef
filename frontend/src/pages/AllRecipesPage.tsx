import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { addFavorite, deleteRecipe, fetchFavorites, fetchRecipes, removeFavorite } from '../api/client';
import AddRecipeModal from '../components/AddRecipeModal';
import RecipeGrid from '../components/RecipeGrid';
import type { Recipe } from '../types/recipe';

export default function AllRecipesPage() {
  const navigate = useNavigate();
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Recipe | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadAll();
  }, []);

  async function loadAll() {
    setLoading(true);
    setError(null);
    try {
      // Fetch both in parallel — favorites failure is non-fatal
      const [recipesData, favoritesData] = await Promise.all([
        fetchRecipes(),
        fetchFavorites().catch(() => [] as Recipe[]),
      ]);
      setRecipes(recipesData);
      setFavoriteIds(new Set(favoritesData.map((r) => r.id)));
    } catch {
      setError('Could not load recipes. Is the backend running?');
    } finally {
      setLoading(false);
    }
  }

  // Prepend the newly imported recipe so it appears first without re-fetching
  function handleRecipeAdded(recipe: Recipe) {
    setRecipes((prev) => [recipe, ...prev]);
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteRecipe(deleteTarget.id);
      setRecipes((prev) => prev.filter((r) => r.id !== deleteTarget.id));
      setFavoriteIds((prev) => {
        const next = new Set(prev);
        next.delete(deleteTarget.id);
        return next;
      });
    } catch {
      // leave list unchanged on error
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  }

  async function handleFavoriteToggle(recipe: Recipe) {
    const isFav = favoriteIds.has(recipe.id);

    // Optimistic update
    setFavoriteIds((prev) => {
      const next = new Set(prev);
      if (isFav) next.delete(recipe.id);
      else next.add(recipe.id);
      return next;
    });

    try {
      if (isFav) {
        await removeFavorite(recipe.id);
      } else {
        await addFavorite(recipe.id);
      }
    } catch {
      // Revert on failure
      setFavoriteIds((prev) => {
        const next = new Set(prev);
        if (isFav) next.add(recipe.id);
        else next.delete(recipe.id);
        return next;
      });
    }
  }

  return (
    <main className="max-w-5xl mx-auto px-6 py-8">
      {/* Page header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-stone-800">All Recipes</h1>
          {!loading && !error && (
            <p className="text-sm text-stone-400 mt-0.5">
              {recipes.length} recipe{recipes.length !== 1 ? 's' : ''}
            </p>
          )}
        </div>

        {/* Add Recipe button */}
        <button
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-amber-500 hover:bg-amber-600 rounded-xl shadow-sm transition-colors"
          aria-label="Add a new recipe"
        >
          <span className="text-lg leading-none font-light">+</span>
          <span>Add Recipe</span>
        </button>
      </div>

      {/* States */}
      {loading && (
        <div className="text-center py-24 text-stone-400">
          Loading recipes…
        </div>
      )}
      {error && (
        <div className="text-center py-24 text-rose-400">{error}</div>
      )}
      {!loading && !error && (
        <RecipeGrid
          recipes={recipes}
          emptyMessage="No recipes yet. Hit + to add your first one."
          favoriteIds={favoriteIds}
          onCardClick={(recipe) => navigate(`/recipes/${recipe.id}`)}
          onFavoriteToggle={handleFavoriteToggle}
          onDeleteRequest={(recipe) => setDeleteTarget(recipe)}
        />
      )}

      <AddRecipeModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onRecipeAdded={handleRecipeAdded}
      />

      {/* Delete confirmation modal */}
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
