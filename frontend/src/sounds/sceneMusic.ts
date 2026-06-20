// Singleton background-music manager for the 3D cafe scene.
//
// Browsers block autoplay until the user interacts with the page, so we wait for
// the first pointerdown/keydown before calling play() and retry on later
// interactions if the first attempt was rejected. A subscribe/notify pattern lets
// the TopBar mute button re-render without lifting state or adding a context.
//
// The audio instance survives OfficeScene remounts (navigating scene -> dashboard
// -> scene): unmount pauses, remount resumes if the user had already started it.

const MUSIC_URL = (import.meta as unknown as { env: { DEV?: boolean } }).env?.DEV
  ? "/sounds/m1.mp3"
  : "/3d/sounds/m1.mp3";

const DEFAULT_VOLUME = 0.4;

let audio: HTMLAudioElement | null = null;
let started = false;
let muted = false;
const listeners = new Set<(muted: boolean) => void>();

function notify(): void {
  for (const fn of listeners) fn(muted);
}

export function initSceneMusic(): void {
  if (audio) {
    // Remount (e.g. back to /scene): resume if the user had already started it.
    if (started && audio.paused) {
      audio.play().catch(() => {});
    }
    return;
  }
  audio = new Audio(MUSIC_URL);
  audio.loop = true;
  audio.volume = DEFAULT_VOLUME;
  audio.preload = "auto";

  let bound = true;
  const start = () => {
    if (!audio || started) return;
    audio
      .play()
      .then(() => {
        started = true;
        if (bound) {
          window.removeEventListener("pointerdown", start);
          window.removeEventListener("keydown", start);
          bound = false;
        }
      })
      .catch(() => {
        // Autoplay still blocked (e.g. the gesture wasn't "activating" enough) or
        // the file isn't ready yet — leave started=false so the next interaction retries.
      });
  };
  window.addEventListener("pointerdown", start);
  window.addEventListener("keydown", start);
}

export function stopSceneMusic(): void {
  if (audio) audio.pause();
}

export function toggleMute(): boolean {
  if (!audio) return muted;
  muted = !muted;
  audio.muted = muted;
  notify();
  return muted;
}

export function subscribeMute(fn: (muted: boolean) => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function isMuted(): boolean {
  return muted;
}
