/**
 * useVoiceSession
 *
 * Always-listening, wake-word-activated voice loop for the cooking mode.
 *
 * Runtime loop:
 *   passive  → (hear "Su")  → capturing
 *   capturing→ (silence/timeout) → sending
 *   sending  → (backend ok) → speaking
 *   sending  → (422/503)    → speaking  (retry prompt via speechSynthesis)
 *   speaking → (audio ended) → passive
 *
 * All STT, flow/RAG/LLM routing, and TTS happen in the backend.
 * This hook only: listens for the wake word, captures audio, ships it,
 * plays the WAV response, and loops.
 *
 * The microphone stream is opened ONCE when the session becomes active and
 * kept open for the whole session.  This eliminates the async getUserMedia
 * latency that previously cut off the start of commands spoken immediately
 * after the wake word.
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
}

// ── Constants ─────────────────────────────────────────────────────────────────

// "Su" is an English wake word — use en-US for reliable recognition.
// Variants: "su", "sue" (common mishear), and the Hebrew samech/shin forms
// in case the user switches recognition language later.
const WAKE_WORD_RE = /^(su|sue|so|סו|שו)\b/i;

const SILENCE_THRESHOLD_RMS = 8;
const SILENCE_DURATION_MS   = 700;  // was 1500 — reduces dead-wait on every turn
const MIN_VOICE_MS          = 300;
const MAX_CAPTURE_MS        = 6000;
const MIN_BLOB_BYTES        = 500;

// ── MIME type ─────────────────────────────────────────────────────────────────

function pickMimeType(): string {
  if (typeof MediaRecorder === 'undefined') return '';
  for (const t of [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/ogg',
  ]) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return '';
}

const RECORDER_MIME = pickMimeType();

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useVoiceSession({
  voiceSessionId,
  active,
  isHebrew,
  onSessionUpdate,
}: Options): { voiceState: VoiceState; debug: VoiceDebugInfo } {
  const [voiceState, setVoiceState] = useState<VoiceState>('off');
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

  const isHebrewRef = useRef(isHebrew);
  isHebrewRef.current = isHebrew;

  // setDebug is stable across renders — safe to capture in effect closure.
  const setDebugRef = useRef(setDebug);
  setDebugRef.current = setDebug;

  useEffect(() => {
    if (!voiceSessionId || !active) {
      setVoiceState('off');
      return;
    }

    const vsId = voiceSessionId;

    // ── Mutable runtime state ───────────────────────────────────────────────
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let recognition: any = null;
    let recorder: MediaRecorder | null = null;
    // Single mic stream opened once for the whole session lifetime.
    let micStream: MediaStream | null = null;
    let audioCtx: AudioContext | null = null;
    let vadTimer: ReturnType<typeof setTimeout> | null = null;
    let captureHardTimeout: ReturnType<typeof setTimeout> | null = null;
    let blobUrl: string | null = null;
    let stateValue: VoiceState = 'passive';
    let destroyed = false;

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

    function stopMic() {
      micStream?.getTracks().forEach(t => t.stop());
      micStream = null;
    }

    function stopVAD() {
      if (vadTimer !== null)           { clearTimeout(vadTimer);           vadTimer = null; }
      if (captureHardTimeout !== null) { clearTimeout(captureHardTimeout); captureHardTimeout = null; }
      if (audioCtx)                    { audioCtx.close();                 audioCtx = null; }
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
      teardownRecognition();
      stopVAD();
      if (recorder && recorder.state !== 'inactive') {
        try { recorder.stop(); } catch { /* ignored */ }
      }
      recorder = null;
      stopMic();
      revokeBlobUrl();
      window.speechSynthesis?.cancel();
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

    // ── Send captured audio ─────────────────────────────────────────────────

    async function sendTurn(blob: Blob, mimeType: string) {
      if (destroyed || stateValue !== 'capturing') return;

      const t0 = Date.now();
      console.log(`[voice] capture stopped — blob ${blob.size}B, mime ${mimeType}`);

      if (blob.size < MIN_BLOB_BYTES) {
        patchDebug({ lastError: `Blob too small (${blob.size} bytes) — discarded` });
        startPassive();
        return;
      }

      setState('sending');

      let audio_base64: string;
      try {
        audio_base64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload  = () => resolve((reader.result as string).split(',')[1]);
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });
      } catch {
        patchDebug({ lastError: 'FileReader failed encoding audio' });
        startPassive();
        return;
      }

      const t1 = Date.now();
      console.log(`[voice] encoded in ${t1 - t0}ms — sending request`);

      try {
        const res = await sendVoiceTurn(vsId, { audio_base64, mime_type: mimeType });
        const t2 = Date.now();
        console.log(`[voice] response received in ${t2 - t1}ms (total from stop: ${t2 - t0}ms)`);
        if (destroyed) return;
        patchDebug({
          lastError: null,
          lastVoiceTranscript: res.transcript,
          lastVoiceAnswer: res.answer,
        });
        onSessionUpdateRef.current(res.recipe_session);
        playResponse(res.audio_base64, res.audio_content_type);
        console.log(`[voice] playback started at +${Date.now() - t0}ms`);
      } catch (err: unknown) {
        if (destroyed) return;
        const msg = err instanceof Error ? err.message : String(err);
        console.log(`[voice] request failed at +${Date.now() - t0}ms: ${msg}`);
        patchDebug({ lastError: `sendVoiceTurn failed: ${msg}` });
        if (msg.includes('422') || msg.includes('503')) {
          speakRetry();
        } else {
          startPassive();
        }
      }
    }

    // ── Capture phase ───────────────────────────────────────────────────────
    // micStream is already open — no async getUserMedia needed here.

    function startCapture() {
      if (destroyed) return;
      setState('capturing');
      teardownRecognition();

      if (!micStream) {
        patchDebug({ lastError: 'Mic stream not available' });
        startPassive();
        return;
      }

      const chunks: Blob[] = [];
      const mimeType = RECORDER_MIME;
      recorder = new MediaRecorder(micStream, mimeType ? { mimeType } : undefined);

      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };

      recorder.onstop = () => {
        stopVAD();
        // Keep micStream open — it is shared for the whole session lifetime.
        if (!destroyed && stateValue === 'capturing') {
          const finalBlob = new Blob(chunks, { type: mimeType || 'audio/webm' });
          sendTurn(finalBlob, mimeType || 'audio/webm');
        }
      };

      audioCtx = new AudioContext();
      const source   = audioCtx.createMediaStreamSource(micStream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);

      let hadVoice    = false;
      let voiceStart  = 0;
      let silenceStart = Date.now();

      function checkVAD() {
        if (destroyed || stateValue !== 'capturing') return;
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (const v of data) { const n = (v - 128) / 128; sum += n * n; }
        const rms = Math.sqrt(sum / data.length) * 100;

        if (rms > SILENCE_THRESHOLD_RMS) {
          if (!hadVoice) { hadVoice = true; voiceStart = Date.now(); }
          silenceStart = Date.now();
        } else if (hadVoice && (Date.now() - voiceStart) > MIN_VOICE_MS) {
          if ((Date.now() - silenceStart) > SILENCE_DURATION_MS) {
            if (recorder && recorder.state === 'recording') recorder.stop();
            return;
          }
        }
        vadTimer = setTimeout(checkVAD, 100);
      }

      captureHardTimeout = setTimeout(() => {
        if (recorder && recorder.state === 'recording') recorder.stop();
      }, MAX_CAPTURE_MS);

      recorder.start(100);
      checkVAD();
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
        return;
      }
      patchDebug({ srSupported: true, lastError: null });

      teardownRecognition();

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const rec: any = new SR();
      rec.continuous     = true;
      rec.interimResults = true;
      // FIX: use en-US so Chrome reliably transcribes the English wake word "Su".
      // The actual command audio is captured separately and sent to backend Whisper
      // which auto-detects Hebrew / English.
      rec.lang = 'en-US';

      let explicitlyStopped = false;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      rec.onresult = (event: any) => {
        if (destroyed || stateValue !== 'passive') return;
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript.trim();
          const matched = WAKE_WORD_RE.test(transcript);
          // Always surface the transcript in the debug panel.
          patchDebug({ lastTranscript: transcript, wakeMatched: matched });
          if (matched) {
            explicitlyStopped = true;
            rec.stop();
            startCapture();
            return;
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

    // ── Startup: open mic once, then enter passive mode ─────────────────────

    async function init() {
      try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'getUserMedia failed';
        patchDebug({
          srSupported: false,
          lastError: `Mic access denied: ${msg}`,
        });
        setState('off');
        return;
      }
      if (!destroyed) startPassive();
    }

    init();
    return fullCleanup;
  }, [voiceSessionId, active]); // eslint-disable-line react-hooks/exhaustive-deps

  return { voiceState, debug };
}
