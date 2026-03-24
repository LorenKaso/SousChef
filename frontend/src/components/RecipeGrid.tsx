import type { Recipe } from '../types/recipe';
import RecipeCard from './RecipeCard';

interface Props {
  recipes: Recipe[];
  emptyMessage?: string;
  favoriteIds?: Set<string>;
  onCardClick?: (recipe: Recipe) => void;
  onFavoriteToggle?: (recipe: Recipe) => void;
  onDeleteRequest?: (recipe: Recipe) => void;
}

export default function RecipeGrid({
  recipes,
  emptyMessage = 'No recipes here yet.',
  favoriteIds,
  onCardClick,
  onFavoriteToggle,
  onDeleteRequest,
}: Props) {
  if (recipes.length === 0) {
    return (
      <div className="text-center py-24 text-stone-400">
        <p className="text-base">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-4">
      {recipes.map((recipe) => (
        <RecipeCard
          key={recipe.id}
          recipe={recipe}
          isFavorited={favoriteIds?.has(recipe.id)}
          onClick={() => onCardClick?.(recipe)}
          onFavoriteToggle={
            onFavoriteToggle ? () => onFavoriteToggle(recipe) : undefined
          }
          onDeleteRequest={
            onDeleteRequest ? () => onDeleteRequest(recipe) : undefined
          }
        />
      ))}
    </div>
  );
}
