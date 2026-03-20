import type { Recipe } from '../types/recipe';

// A small deterministic palette — each recipe gets a consistent accent colour
// based on a simple hash of its id.
const ACCENTS = [
  'bg-amber-400',
  'bg-rose-400',
  'bg-emerald-400',
  'bg-sky-400',
  'bg-violet-400',
] as const;

function accentForId(id: string): string {
  const hash = Array.from(id).reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return ACCENTS[hash % ACCENTS.length];
}

interface Props {
  recipe: Recipe;
  isFavorited?: boolean;
  onClick?: () => void;
  onFavoriteToggle?: () => void;
}

export default function RecipeCard({
  recipe,
  isFavorited,
  onClick,
  onFavoriteToggle,
}: Props) {
  const totalIngredients = recipe.sections.reduce(
    (sum, s) => sum + s.ingredients.length,
    0,
  );
  const totalSteps = recipe.sections.reduce(
    (sum, s) => sum + s.steps.length,
    0,
  );

  // Outer wrapper is a div so that the heart <button> inside is valid HTML.
  // Same visual appearance as before — cursor-pointer + focus ring preserved.
  return (
    <div
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onClick?.();
      }}
      role="button"
      tabIndex={0}
      className="group w-full text-left bg-white rounded-2xl border border-stone-100 shadow-sm overflow-hidden hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 transition-shadow duration-200 cursor-pointer"
    >
      {/* Colour accent strip */}
      <div className={`h-1.5 w-full ${accentForId(recipe.id)}`} />

      <div className="p-4">
        {/* Title row — heart sits beside the title when enabled */}
        <div className="flex items-start justify-between gap-2">
          <p className="font-semibold text-stone-800 text-base leading-snug line-clamp-2 group-hover:text-amber-600 transition-colors duration-150">
            {recipe.title}
          </p>

          {onFavoriteToggle !== undefined && (
            <button
              onClick={(e) => {
                e.stopPropagation(); // don't fire the card's navigation onClick
                onFavoriteToggle();
              }}
              aria-label={isFavorited ? 'Remove from favorites' : 'Add to favorites'}
              className={`shrink-0 text-lg leading-none transition-colors duration-150 ${
                isFavorited
                  ? 'text-rose-500 hover:text-rose-600'
                  : 'text-stone-300 hover:text-rose-400'
              }`}
            >
              {isFavorited ? '♥' : '♡'}
            </button>
          )}
        </div>

        <p className="mt-2 text-xs text-stone-400">
          {recipe.servings} serving{recipe.servings !== 1 ? 's' : ''}&ensp;·&ensp;
          {totalIngredients} ingredient{totalIngredients !== 1 ? 's' : ''}&ensp;·&ensp;
          {totalSteps} step{totalSteps !== 1 ? 's' : ''}
        </p>
      </div>
    </div>
  );
}
