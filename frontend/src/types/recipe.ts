// Types mirror the backend Pydantic models exactly.
// Update here if the backend models change.

// ── Recipe ───────────────────────────────────────────────────────────────────

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

export interface FlowItem {
  type: 'ingredient' | 'step';
  index: number;
}

export interface RecipeSection {
  name: string;
  ingredients: Ingredient[];
  steps: Step[];
  execution_flow: FlowItem[] | null;
}

export interface Recipe {
  id: string;
  title: string;
  servings: number;
  sections: RecipeSection[];
}

// ── Import ────────────────────────────────────────────────────────────────────

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

// ── Favorites ─────────────────────────────────────────────────────────────────

export interface FavoriteEntry {
  recipe_id: string;
  favorited_at: string;
}

// ── Cooking session ───────────────────────────────────────────────────────────

export interface Timer {
  id: string;
  seconds: number;
  label: string;
  step_index: number;
  started_at: string;
}

export interface Session {
  id: string;
  recipe_id: string;
  current_section_index: number;
  current_phase: 'ingredients' | 'steps' | 'flow';
  current_item_index: number;
  active_timers: Timer[];
  pending_timer: { seconds: number; label: string | null } | null;
  created_at: string;
  updated_at: string;
}

export type ActionType =
  | 'START_TIMER'
  | 'TIMER_FINISHED'
  | 'NEXT_STEP'
  | 'PREV_STEP'
  | 'HIGHLIGHT_INGREDIENT';

export interface Action {
  type: ActionType;
  payload: Record<string, unknown>;
}

export interface AskResponse {
  answer: string;
  actions: Action[];
  session: Session;
}

// ── Voice session ─────────────────────────────────────────────────────────────

export type VoiceSessionState =
  | 'idle'
  | 'listening'
  | 'processing'
  | 'speaking'
  | 'stopped';

export interface VoiceSession {
  id: string;
  recipe_session_id: string;
  state: VoiceSessionState;
  last_transcript: string | null;
  last_answer: string | null;
  stt_model: string | null;
  tts_model: string | null;
  created_at: string;
  updated_at: string;
}

export interface VoiceSessionStartResponse {
  voice_session: VoiceSession;
  recipe_session: Session;
}

export interface VoiceSessionTurnResponse {
  transcript: string;
  answer: string;
  actions: Action[];
  voice_session: VoiceSession;
  recipe_session: Session;
  audio_base64: string;
  audio_content_type: string;
  audio_encoding: string;
}
