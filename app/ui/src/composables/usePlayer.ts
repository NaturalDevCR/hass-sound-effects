import { ref } from "vue";
import { translate } from "@/i18n";
import { useToast } from "./useToast";

const currentId = ref<string | null>(null);
const playing = ref(false);
let audio: HTMLAudioElement | null = null;

function reset(): void {
  currentId.value = null;
  playing.value = false;
}

/** One shared element: starting a sound always silences the previous one. */
function element(): HTMLAudioElement {
  if (!audio) {
    audio = new Audio();
    audio.preload = "none";
    audio.addEventListener("ended", reset);
    // External pauses (media keys, an incoming call). Ignore the late event our own
    // pause() queues when we switch sounds: by then play() has made `paused` false again.
    audio.addEventListener("pause", () => {
      if (audio?.paused) playing.value = false;
    });
    audio.addEventListener("error", () => {
      if (!currentId.value) return;
      reset();
      useToast().push(translate("player.error"), "error");
    });
  }
  return audio;
}

function stop(): void {
  if (audio) {
    audio.pause();
    audio.currentTime = 0;
  }
  reset();
}

/** Plays `url` for sound `id`; calling it again for the sound that is playing stops it. */
function toggle(id: string, url: string): void {
  if (currentId.value === id && playing.value) {
    stop();
    return;
  }
  const el = element();
  el.pause();
  el.src = url;
  el.currentTime = 0;
  currentId.value = id;
  playing.value = true;
  el.play().catch(() => {
    if (currentId.value !== id) return; // superseded by another sound meanwhile
    reset();
    useToast().push(translate("player.error"), "error");
  });
}

export function usePlayer() {
  return { currentId, playing, toggle, stop };
}
