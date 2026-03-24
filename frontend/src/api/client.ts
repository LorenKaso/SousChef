// All requests go through the /api prefix which Vite proxies to
// http://localhost:8000 (stripping /api) during development.
// Change BASE if the proxy config or deployment target changes.

import type {
  AskResponse,
  FavoriteEntry,
  ImportRecipeTextResponse,
  Recipe,
  Session,
  VoiceSessionStartResponse,
  VoiceSessionTurnResponse,
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

export async function deleteRecipe(recipeId: string): Promise<void> {
  const res = await fetch(`${BASE}/recipes/${recipeId}`, {
    method: 'DELETE',
  });
  await handleResponse<unknown>(res);
}

// ── Cooking session ───────────────────────────────────────────────────────────

export async function startSession(recipeId: string): Promise<Session> {
  const res = await fetch(`${BASE}/session/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recipe_id: recipeId }),
  });
  return handleResponse<Session>(res);
}

export async function askQuestion(
  sessionId: string,
  text: string,
): Promise<AskResponse> {
  const res = await fetch(`${BASE}/session/${sessionId}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  return handleResponse<AskResponse>(res);
}

// ── Voice session ─────────────────────────────────────────────────────────────

export async function startVoiceSession(
  recipeId: string,
): Promise<VoiceSessionStartResponse> {
  const res = await fetch(`${BASE}/voice/session/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recipe_id: recipeId }),
  });
  return handleResponse<VoiceSessionStartResponse>(res);
}

export async function sendVoiceTurn(
  voiceSessionId: string,
  payload: {
    transcript_text?: string;
    audio_base64?: string;
    mime_type?: string;
    language_hint?: 'en' | 'he';
  },
): Promise<VoiceSessionTurnResponse> {
  const res = await fetch(`${BASE}/voice/session/${voiceSessionId}/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<VoiceSessionTurnResponse>(res);
}

export async function stopVoiceSession(
  voiceSessionId: string,
): Promise<void> {
  const res = await fetch(`${BASE}/voice/session/${voiceSessionId}/stop`, {
    method: 'POST',
  });
  await handleResponse<unknown>(res);
}
