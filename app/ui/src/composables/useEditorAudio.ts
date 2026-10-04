import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch, type Ref } from "vue";
import { audioUrl, messageOf } from "@/api/client";
import type { Recipe } from "@/api/types";
import { audioEngine as engine } from "@/lib/audioEngine";
import { computePeaks } from "@/lib/peaks";
import { usePlayer } from "./usePlayer";

export function useEditorAudio(
  id: Readonly<Ref<string>>,
  recipe: Ref<Recipe>,
  valid: Readonly<Ref<boolean>>,
  available: Readonly<Ref<boolean>> = ref(true),
) {
  const buffer = shallowRef<AudioBuffer>();
  const peaks = shallowRef<number[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const activated = ref(navigator.userActivation?.hasBeenActive ?? false);
  const playing = ref(false);
  const position = ref(0);
  const loop = ref(false);
  const bypass = ref(false);
  const duration = computed(() => buffer.value?.duration ?? 0);
  let generation = 0;
  let frame = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;
  function stop() {
    clearTimeout(timer);
    engine.stop();
    playing.value = false;
    cancelAnimationFrame(frame);
  }
  async function decode() {
    if (loading.value || disposed || !available.value) return;
    activated.value = true;
    loading.value = true;
    error.value = null;
    const ticket = ++generation;
    try {
      const decoded = await engine.load(audioUrl(id.value, "original"));
      if (ticket !== generation || disposed) return;
      buffer.value = decoded;
      peaks.value = computePeaks(
        Array.from({ length: decoded.numberOfChannels }, (_, i) => decoded.getChannelData(i)),
        Math.min(1800, decoded.length || 1800),
      );
    } catch (cause) {
      if (ticket === generation && !disposed) error.value = messageOf(cause);
    } finally {
      if (ticket === generation) loading.value = false;
    }
  }
  function animate() {
    position.value = engine.position;
    playing.value = engine.playing;
    if (playing.value) frame = requestAnimationFrame(animate);
  }
  function play(from?: number) {
    if (!buffer.value || (!bypass.value && !valid.value)) return;
    clearTimeout(timer);
    usePlayer().stop();
    const r = recipe.value;
    try {
      engine.play(
        buffer.value,
        {
          trimStart: r.trim_start,
          trimEnd: r.trim_end ?? duration.value,
          gainDb: r.gain_db,
          fadeIn: r.fade_in,
          fadeOut: r.fade_out,
          bypass: bypass.value,
        },
        { loop: loop.value, from },
      );
      error.value = null;
      cancelAnimationFrame(frame);
      animate();
    } catch (cause) {
      stop();
      error.value = messageOf(cause);
    }
  }
  function toggle() {
    if (playing.value) {
      position.value = engine.position;
      stop();
    } else {
      const start = bypass.value ? 0 : recipe.value.trim_start;
      const end = bypass.value ? duration.value : (recipe.value.trim_end ?? duration.value);
      play(position.value >= start && position.value < end ? position.value : start);
    }
  }
  function seek(time: number) {
    const start = bypass.value ? 0 : recipe.value.trim_start;
    const end = bypass.value ? duration.value : (recipe.value.trim_end ?? duration.value);
    position.value = Math.max(start, Math.min(time, end));
    if (playing.value) play(position.value);
  }
  watch(
    () => [
      recipe.value.trim_start,
      recipe.value.trim_end,
      recipe.value.gain_db,
      recipe.value.fade_in,
      recipe.value.fade_out,
      bypass.value,
      loop.value,
    ],
    () => {
      if (!playing.value) return;
      clearTimeout(timer);
      if (!valid.value && !bypass.value) {
        stop();
        return;
      }
      timer = setTimeout(() => {
        const end = bypass.value ? duration.value : (recipe.value.trim_end ?? duration.value);
        const current = engine.position;
        play(current < end ? current : undefined);
      }, 80);
    },
  );
  watch(id, () => {
    generation++;
    stop();
    usePlayer().stop();
    buffer.value = undefined;
    peaks.value = [];
    position.value = 0;
    loading.value = false;
    if (activated.value) void decode();
  });
  watch(available, (next) => {
    if (next && activated.value && !buffer.value && !loading.value) void decode();
  });
  function activate(event: Event) {
    if (event instanceof KeyboardEvent && (event.metaKey || event.ctrlKey || event.altKey)) return;
    if (!activated.value) void decode();
  }
  onMounted(() => {
    engine.onEnded = () => {
      position.value = engine.position;
      playing.value = false;
      cancelAnimationFrame(frame);
    };
    engine.onError = (cause) => {
      stop();
      error.value = messageOf(cause);
    };
    document.addEventListener("pointerdown", activate);
    document.addEventListener("keydown", activate);
    if (activated.value) void decode();
  });
  onBeforeUnmount(() => {
    disposed = true;
    generation++;
    stop();
    usePlayer().stop();
    engine.onEnded = undefined;
    engine.onError = undefined;
    document.removeEventListener("pointerdown", activate);
    document.removeEventListener("keydown", activate);
  });
  return {
    buffer,
    peaks,
    loading,
    error,
    activated,
    playing,
    position,
    loop,
    bypass,
    duration,
    decode,
    play,
    toggle,
    seek,
    stop,
  };
}
