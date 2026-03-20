import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { addFavorite, fetchFavorites, fetchRecipes, removeFavorite } from '../api/client';
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
        />
      )}

      <AddRecipeModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onRecipeAdded={handleRecipeAdded}
      />
    </main>
  );
}
