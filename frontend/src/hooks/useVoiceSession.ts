/**
 * useVoiceSession
 *
 * Always-listening, wake-word-activated voice loop for the cooking mode.
 *
 * Runtime loop:
 *   passive (idle)          → hear "Su" → speak "כן/Yes" → passive (active window)
 *   passive (active window) → SR final result → sending
 *   sending                 → (backend ok) → speaking
 *   sending                 → (422/503)    → speaking (retry prompt)
 *   speaking                → (audio ended) → passive (active window)
 *   [30 s inactivity]       → passive (idle, wake word required again)
 *
 * All commands travel as SR transcript text — no audio capture or Whisper
 * inference.  The backend handles routing, RAG, and TTS generation.
 */

import { useEffect, useRef, useState } from 'react';
import { sendVoiceTurn } from '../api/client';
import type { Session } from '../types/recipe';

// ── Public types ──────────────────────────────────────────────────────────────

export type VoiceState = 'off' | 'passive' | 'capturing' | 'sending' | 'speaking';

/** Debug surface — remove the debug panel in RecipeDetailPage when no longer needed. */
export interface VoiceDebugInfo {
  srSupported: boolean | null; // null = not yet checked
  lastTranscript: string;       // wake-word SpeechRecognition transcript
  wakeMatched: boolean;
  lastVoiceTranscript: string;  // Whisper transcript from last turn
  lastVoiceAnswer: string;      // backend answer from last turn
  lastError: string | null;
}

interface Options {
  voiceSessionId: string | null;
  active: boolean;
  isHebrew: boolean;
  onSessionUpdate: (session: Session) => void;
  /** Called when the backend returns 404 or 409 — the session no longer exists. */
  onSessionInvalid?: () => void;
}

// ── Constants ─────────────────────────────────────────────────────────────────

// Wake-word / assistant-name detection.
// Matches the short forms ("Su", "So") and the full assistant name ("SousChef",
// "Sous Chef", "Sous-Chef") so all natural invocation styles trigger capture.
// The backend independently strips the same prefixes from the Whisper transcript
// before routing, so neither the detection word nor any variant ever reaches
// the question-routing logic.
const WAKE_WORD_RE = /^(sous[\s\-]?chef|su|sue|so|סו|שו)\b/i;

/** After wake-word activation, any speech triggers a turn for this long. */
const ACTIVE_WINDOW_MS = 30_000;

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useVoiceSession({
  voiceSessionId,
  active,
  isHebrew,
  onSessionUpdate,
  onSessionInvalid,
}: Options): { voiceState: VoiceState; debug: VoiceDebugInfo; isActiveWindow: boolean } {
  const [voiceState, setVoiceState] = useState<VoiceState>('off');
  const [isActiveWindow, setIsActiveWindow] = useState(false);
  const [debug, setDebug] = useState<VoiceDebugInfo>({
    srSupported: null,
    lastTranscript: '',
    wakeMatched: false,
    lastVoiceTranscript: '',
    lastVoiceAnswer: '',
    lastError: null,
  });

  const onSessionUpdateRef = useRef(onSessionUpdate);
  onSessionUpdateRef.current = onSessionUpdate;

  const onSessionInvalidRef = useRef(onSessionInvalid);
  onSessionInvalidRef.current = onSessionInvalid;

  const isHebrewRef = useRef(isHebrew);
  isHebrewRef.current = isHebrew;

  // setDebug is stable across renders — safe to capture in effect closure.
  const setDebugRef = useRef(setDebug);
  setDebugRef.current = setDebug;

  useEffect(() => {
    if (!voiceSessionId || !active) {
      setVoiceState('off');
      setIsActiveWindow(false);
      return;
    }

    const vsId = voiceSessionId;
    console.log(`[voice] session active — voiceSessionId=${vsId}`);

    // ── Mutable runtime state ───────────────────────────────────────────────
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let recognition: any = null;
    let blobUrl: string | null = null;
    let stateValue: VoiceState = 'passive';
    let destroyed = false;

    // ── Active-window state ─────────────────────────────────────────────────
    // True when the user has recently used the wake word and any speech should
    // trigger capture without requiring the wake word again.
    let inActiveWindow = false;
    let activeWindowTimer: ReturnType<typeof setTimeout> | null = null;

    function updateActiveWindow(val: boolean) {
      inActiveWindow = val;
      setIsActiveWindow(val);
    }

    function clearActiveWindowTimer() {
      if (activeWindowTimer !== null) {
        clearTimeout(activeWindowTimer);
        activeWindowTimer = null;
      }
    }

    function scheduleActiveWindowTimeout() {
      clearActiveWindowTimer();
      activeWindowTimer = setTimeout(() => {
        activeWindowTimer = null;
        if (!destroyed) {
          console.log('[voice] active window timed out — reverting to idle (wake word required)');
          updateActiveWindow(false);
          teardownRecognition();
          startPassive();
        }
      }, ACTIVE_WINDOW_MS);
    }

    function setState(s: VoiceState) {
      if (destroyed) return;
      stateValue = s;
      setVoiceState(s);
    }

    function patchDebug(patch: Partial<VoiceDebugInfo>) {
      if (destroyed) return;
      setDebugRef.current(prev => ({ ...prev, ...patch }));
    }

    // ── Resource teardown ───────────────────────────────────────────────────

    function revokeBlobUrl() {
      if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
    }

    function teardownRecognition() {
      if (!recognition) return;
      recognition.onresult = null;
      recognition.onerror  = null;
      recognition.onend    = null;
      try { recognition.stop(); } catch { /* already stopped */ }
      recognition = null;
    }

    function fullCleanup() {
      destroyed = true;
      clearActiveWindowTimer();
      teardownRecognition();
      revokeBlobUrl();
      window.speechSynthesis?.cancel();
    }

    // ── Wake-word confirmation ───────────────────────────────────────────────
    // Plays a short "כן"/"Yes" via browser TTS so the user knows the wake word
    // was heard, then re-enters passive mode in active-window mode.  This
    // replaces the old startCapture() call so that the first post-wake-word
    // command also goes through the SR-text path instead of Whisper.

    function speakWakeConfirmation() {
      if (destroyed) return;
      setState('speaking');
      if (!('speechSynthesis' in window)) { startPassive(); return; }
      window.speechSynthesis.cancel();
      const msg = isHebrewRef.current ? 'כן' : 'Yes';
      const utt = new SpeechSynthesisUtterance(msg);
      utt.lang   = isHebrewRef.current ? 'he-IL' : 'en-US';
      utt.volume = 0.8;
      utt.rate   = 1.5;
      utt.onend   = () => { if (!destroyed) startPassive(); };
      utt.onerror = () => { if (!destroyed) startPassive(); };
      window.speechSynthesis.speak(utt);
    }

    // ── Retry prompt ────────────────────────────────────────────────────────

    function speakRetry() {
      if (destroyed) return;
      setState('speaking');
      if (!('speechSynthesis' in window)) { startPassive(); return; }
      window.speechSynthesis.cancel();
      const msg = isHebrewRef.current
        ? 'לא הבנתי, תוכלי לחזור שוב?'
        : "I didn't understand, can you say that again?";
      const utt = new SpeechSynthesisUtterance(msg);
      utt.lang    = isHebrewRef.current ? 'he-IL' : 'en-US';
      utt.onend   = () => startPassive();
      utt.onerror = () => startPassive();
      window.speechSynthesis.speak(utt);
    }

    // ── Play backend TTS response ───────────────────────────────────────────

    function playResponse(base64: string, contentType: string) {
      if (destroyed) return;
      revokeBlobUrl();
      setState('speaking');
      try {
        const bytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
        const blob  = new Blob([bytes], { type: contentType });
        blobUrl     = URL.createObjectURL(blob);
        const audio = new Audio(blobUrl);
        audio.onended = () => { revokeBlobUrl(); startPassive(); };
        audio.onerror = () => { revokeBlobUrl(); startPassive(); };
        audio.play().catch(() => { revokeBlobUrl(); startPassive(); });
      } catch {
        startPassive();
      }
    }

    // ── Send SR text directly (active-window turns) ──────────────────────────
    // In active-window mode the browser's SR already has the full transcript.
    // Sending it as transcript_text bypasses Whisper (which hallucinated on the
    // short, partially-captured audio that previously reached it).

    async function sendTranscriptAsTurn(text: string) {
      if (destroyed) return;
      clearActiveWindowTimer(); // suspend timeout while turn is in flight
      setState('sending');

      try {
        const res = await sendVoiceTurn(vsId, {
          transcript_text: text,
          language_hint: isHebrewRef.current ? 'he' : 'en',
        });
        if (destroyed) return;
        patchDebug({
          lastError: null,
          lastVoiceTranscript: res.transcript,
          lastVoiceAnswer: res.answer,
        });
        onSessionUpdateRef.current(res.recipe_session);
        playResponse(res.audio_base64, res.audio_content_type);
      } catch (err: unknown) {
        if (destroyed) return;
        const msg = err instanceof Error ? err.message : String(err);
        patchDebug({ lastError: `sendVoiceTurn failed: ${msg}` });
        if (msg.includes('422') || msg.includes('503')) {
          speakRetry();
        } else if (msg.includes('404') || msg.includes('409')) {
          console.log(`[voice] FATAL: session invalid (${msg}) — stopping hook`);
          setState('off');
          onSessionInvalidRef.current?.();
        } else {
          startPassive();
        }
      }
    }

    // ── Passive listening ───────────────────────────────────────────────────

    function startPassive() {
      if (destroyed) return;
      setState('passive');

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
      if (!SR) {
        patchDebug({
          srSupported: false,
          lastError: 'SpeechRecognition not available in this browser',
        });
        // If SR is unavailable while in the active window, drop back to idle
        // so we don't schedule a timeout that can never be cleared.
        if (inActiveWindow) updateActiveWindow(false);
        return;
      }
      patchDebug({ srSupported: true, lastError: null });

      teardownRecognition();

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const rec: any = new SR();
      rec.continuous     = true;
      rec.interimResults = true;
      // Active window + Hebrew: use he-IL so the browser recognises Hebrew speech.
      // Idle (wake-word) mode: always en-US so Chrome reliably hears "Su/SousChef".
      // The command audio captured by MediaRecorder goes to backend Whisper regardless.
      rec.lang = (inActiveWindow && isHebrewRef.current) ? 'he-IL' : 'en-US';

      // Reset the inactivity clock each time we re-enter passive while active.
      if (inActiveWindow) scheduleActiveWindowTimeout();

      let explicitlyStopped = false;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      rec.onresult = (event: any) => {
        if (destroyed || stateValue !== 'passive') return;
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript.trim();

          if (inActiveWindow) {
            // Active window: wait for SR's FINAL result so we have the full
            // utterance, then send it as text directly.  Using interim results
            // (previous behaviour) caused MediaRecorder to start after most of
            // the speech was already over, leaving Whisper with near-silence
            // which it hallucinated as "Thank you very much."
            if (event.results[i].isFinal && transcript.length >= 1) {
              patchDebug({ lastTranscript: transcript, wakeMatched: true });
              console.log(`[voice] active window final: "${transcript}" — sending as text`);
              explicitlyStopped = true;
              rec.stop();
              sendTranscriptAsTurn(transcript);
              return;
            }
            // Show interim transcript in debug without triggering a turn.
            if (transcript.length >= 1) {
              patchDebug({ lastTranscript: transcript });
            }
          } else {
            // Idle: require the wake word before capturing.
            const matched = WAKE_WORD_RE.test(transcript);
            patchDebug({ lastTranscript: transcript, wakeMatched: matched });
            if (matched) {
              console.log(`[voice] wake word matched ("${transcript}") — entering active window`);
              updateActiveWindow(true);
              explicitlyStopped = true;
              rec.stop();
              // Play a short confirmation then re-enter passive in active-window
              // mode.  This ensures the first post-wake-word command also goes
              // through the SR-text path (same as subsequent turns) instead of
              // the old startCapture() → Whisper path that caused hallucinations.
              speakWakeConfirmation();
              return;
            }
          }
        }
      };

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      rec.onerror = (event: any) => {
        const err = event?.error ?? 'unknown SR error';
        if (err === 'not-allowed') {
          patchDebug({ srSupported: false, lastError: 'Microphone permission denied' });
          setState('off');
          return;
        }
        patchDebug({ lastError: `SR error: ${err}` });
        if (!destroyed && stateValue === 'passive' && !explicitlyStopped) {
          setTimeout(() => {
            if (!destroyed && stateValue === 'passive') startPassive();
          }, 500);
        }
      };

      rec.onend = () => {
        if (!destroyed && stateValue === 'passive' && !explicitlyStopped) {
          setTimeout(() => {
            if (!destroyed && stateValue === 'passive') startPassive();
          }, 200);
        }
      };

      recognition = rec;
      try {
        rec.start();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        patchDebug({ lastError: `rec.start() threw: ${msg}` });
      }
    }

    // ── Startup ──────────────────────────────────────────────────────────────
    // SpeechRecognition manages its own mic permission — just enter passive.

    startPassive();
    return fullCleanup;
  }, [voiceSessionId, active]); // eslint-disable-line react-hooks/exhaustive-deps

  return { voiceState, debug, isActiveWindow };
}
