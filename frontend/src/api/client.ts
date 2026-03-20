// All requests go through the /api prefix which Vite proxies to
// http://localhost:8000 (stripping /api) during development.
// Change BASE if the proxy config or deployment target changes.

import type {
  FavoriteEntry,
  ImportRecipeTextResponse,
  Recipe,
} from '../types/recipe';

const BASE = '/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      // ignore JSON parse errors
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// ── Recipes ──────────────────────────────────────────────────────────────────

export async function fetchRecipes(): Promise<Recipe[]> {
  const res = await fetch(`${BASE}/recipes`);
  return handleResponse<Recipe[]>(res);
}

export async function fetchRecipe(recipeId: string): Promise<Recipe> {
  const res = await fetch(`${BASE}/recipes/${recipeId}`);
  return handleResponse<Recipe>(res);
}

export async function importRecipeFromText(
  rawText: string,
): Promise<ImportRecipeTextResponse> {
  const res = await fetch(`${BASE}/recipes/import/text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ raw_text: rawText }),
  });
  return handleResponse<ImportRecipeTextResponse>(res);
}

// ── Favorites ─────────────────────────────────────────────────────────────────

export async function fetchFavorites(): Promise<Recipe[]> {
  const res = await fetch(`${BASE}/favorites`);
  return handleResponse<Recipe[]>(res);
}

export async function addFavorite(recipeId: string): Promise<FavoriteEntry> {
  const res = await fetch(`${BASE}/recipes/${recipeId}/favorite`, {
    method: 'POST',
  });
  return handleResponse<FavoriteEntry>(res);
}

export async function removeFavorite(recipeId: string): Promise<void> {
  const res = await fetch(`${BASE}/recipes/${recipeId}/favorite`, {
    method: 'DELETE',
  });
  await handleResponse<unknown>(res);
}
