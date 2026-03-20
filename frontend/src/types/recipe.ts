// Types mirror the backend Pydantic models exactly.
// Update here if the backend models change.

export interface Ingredient {
  name: string;
  amount: number;
  unit: string;
}

export interface Step {
  index: number;
  text: string;
  default_timer_seconds: number | null;
}

export interface RecipeSection {
  name: string;
  ingredients: Ingredient[];
  steps: Step[];
}

export interface Recipe {
  id: string;
  title: string;
  servings: number;
  sections: RecipeSection[];
}

export interface ImportRecipeTextRequest {
  raw_text: string;
  title?: string;
  language_hint?: 'en' | 'he';
}

export interface ImportRecipeTextResponse {
  recipe: Recipe;
  confidence: string;
  warnings: string[];
}

export interface FavoriteEntry {
  recipe_id: string;
  favorited_at: string;
}
