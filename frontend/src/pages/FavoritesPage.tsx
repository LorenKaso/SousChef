import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchFavorites, removeFavorite } from '../api/client';
import RecipeGrid from '../components/RecipeGrid';
import type { Recipe } from '../types/recipe';

export default function FavoritesPage() {
  const navigate = useNavigate();
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        <h1 className="text-2xl font-bold text-stone-800">Favorites</h1>
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
        />
      )}
    </main>
  );
}
