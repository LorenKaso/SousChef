import { useEffect, useRef, useState } from 'react';
import { importRecipeFromText } from '../api/client';
import type { Recipe } from '../types/recipe';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onRecipeAdded: (recipe: Recipe) => void;
}

export default function AddRecipeModal({ isOpen, onClose, onRecipeAdded }: Props) {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Reset state and focus textarea each time the modal opens
  useEffect(() => {
    if (isOpen) {
      setText('');
      setError(null);
      setLoading(false);
      // Small delay so the element is visible before focusing
      const t = setTimeout(() => textareaRef.current?.focus(), 50);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);

    try {
      const result = await importRecipeFromText(trimmed);
      onRecipeAdded(result.recipe);
      onClose();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Something went wrong. Please try again.',
      );
    } finally {
      setLoading(false);
    }
  }

  if (!isOpen) return null;

  return (
    // Backdrop — click outside to close
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-stone-100">
          <h2 className="text-base font-semibold text-stone-800">
            Add New Recipe
          </h2>
          <button
            onClick={onClose}
            className="text-stone-400 hover:text-stone-600 transition-colors text-2xl leading-none"
            aria-label="Close modal"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="px-6 py-5">
          <label
            htmlFor="recipe-text"
            className="block text-sm font-medium text-stone-600 mb-2"
          >
            Paste your recipe text
          </label>
          <textarea
            id="recipe-text"
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste a recipe here — ingredients, steps, title… the more detail the better."
            rows={10}
            disabled={loading}
            className="w-full px-3 py-2.5 text-sm text-stone-800 bg-stone-50 border border-stone-200 rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent placeholder:text-stone-400 disabled:opacity-60"
          />

          {error && (
            <p className="mt-2 text-sm text-rose-500" role="alert">
              {error}
            </p>
          )}

          {/* Footer actions */}
          <div className="mt-4 flex justify-end items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 text-sm font-medium text-stone-600 hover:text-stone-900 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !text.trim()}
              className="px-5 py-2 text-sm font-semibold text-white bg-green-700 hover:bg-green-800 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Adding…' : 'Add Recipe'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
