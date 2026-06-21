// Singleton background-music manager for the 3D cafe scene.
//
// Browsers block autoplay until the user interacts with the page, so we wait for
// the first pointerdown/keydown before calling play() and retry on later
// interactions if the first attempt was rejected. A subscribe/notify pattern lets
// the TopBar mute button re-render without lifting state or adding a context.
//
// The audio instance survives OfficeScene remounts (navigating scene -> dashboard
// -> scene): unmount pauses, remount resumes if the user had already started it.
//
// Multi-track rotation: HTMLAudioElement.loop only repeats a single track, so we
// set loop=false and advance through PLAYLIST on each `ended` event (m1 -> m2 ->
// m1 ...). Mute/volume/remount-resume all keep working because the element itself
// is reused -- only its `src` changes between tracks.

// Vite `base: '/3d/'` serves public/ files under /3d/ in BOTH dev and prod, so
// the path is identical in either mode (a bare "/sounds/..." would 404 in dev).
const SOUND_BASE = "/3d/sounds";

// Background tracks rotated end-to-end. Append a new entry to add a song; no
// other change is needed.
const PLAYLIST = [`${SOUND_BASE}/m1.mp3`, `${SOUND_BASE}/m2.mp3`];

const DEFAULT_VOLUME = 0.4;

let audio: HTMLAudioElement | null = null;
let started = false;
let muted = false;
let currentIndex = 0;
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
  audio = new Audio(PLAYLIST[currentIndex]);
  audio.loop = false; // rotation handled by the `ended` listener below
  audio.volume = DEFAULT_VOLUME;
  audio.preload = "auto";
  // When the current track finishes, advance to the next one and keep playing.
  audio.addEventListener("ended", () => {
    if (!audio) return;
    currentIndex = (currentIndex + 1) % PLAYLIST.length;
    audio.src = PLAYLIST[currentIndex];
    audio.play().catch(() => {
      // Gesture may have expired (e.g. tab backgrounded). The track is loaded;
      // it resumes on the next play() (unmute / remount).
    });
  });

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
