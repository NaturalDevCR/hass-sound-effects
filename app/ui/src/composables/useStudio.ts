import { computed, ref } from "vue";
import { messageOf, ui } from "@/api/client";
import type { Category, Profile, Season, Settings, Sound, State } from "@/api/types";

// Module-level singleton: every component sees the same lists, and a refresh
// from any view updates all of them.
const state = ref<State | null>(null);
const categories = ref<Category[]>([]);
const seasons = ref<Season[]>([]);
const profiles = ref<Profile[]>([]);
const sounds = ref<Sound[]>([]);
// `loading` starts true: until the first refresh settles the lists are empty only because
// nothing has arrived yet, and views must not flash their empty state. `loaded` flips once,
// after the first successful refresh, and stays true (later refreshes keep the old data).
const loading = ref(true);
const loaded = ref(false);
const error = ref<string | null>(null);

const categoryIndex = computed(() => new Map(categories.value.map((c) => [c.id, c])));
const seasonIndex = computed(() => new Map(seasons.value.map((s) => [s.id, s])));
const profileIndex = computed(() => new Map(profiles.value.map((p) => [p.id, p])));

let inflight: Promise<void> | null = null;
let trailing: Promise<void> | null = null;
let settingsVersion = 0;

/** Apply the canonical PUT response before any pending refresh or queued save can use it. */
function applySettings(settings: Settings): void {
  settingsVersion += 1;
  if (state.value) state.value = { ...state.value, settings };
}

async function load(): Promise<void> {
  const version = settingsVersion;
  try {
    const [nextState, nextCategories, nextSeasons, nextProfiles, nextSounds] = await Promise.all([
      ui.state(),
      ui.categories.list(),
      ui.seasons.list(),
      ui.profiles.list(),
      ui.sounds.list(),
    ]);
    // Keep other refreshed fields (e.g. the rotated token), but a pre-PUT fetch must
    // never replace the successful PUT's settings, even if the follow-up fetch fails.
    state.value =
      version !== settingsVersion && state.value
        ? { ...nextState, settings: state.value.settings }
        : nextState;
    categories.value = nextCategories;
    seasons.value = nextSeasons;
    profiles.value = nextProfiles;
    sounds.value = nextSounds;
    loaded.value = true;
  } catch (cause) {
    error.value = messageOf(cause);
  }
}

function fetchStudio(): Promise<void> {
  loading.value = true;
  error.value = null;
  const run = load().finally(() => {
    loading.value = false;
    inflight = null;
  });
  inflight = run;
  return run;
}

/**
 * Reload everything in parallel. Normal callers share the current request; forced
 * callers wait for it and share one fresh request started after their mutation.
 * Never throws: failures land in `error`.
 */
function refresh(options: { force?: boolean } = {}): Promise<void> {
  const current = inflight;
  if (!current) return fetchStudio();
  if (!options.force) return current;
  trailing ??= current.then(() => {
    trailing = null;
    return inflight ?? fetchStudio();
  });
  return trailing;
}

let inflightSounds: Promise<void> | null = null;
let trailingSounds: Promise<void> | null = null;

async function loadSounds(): Promise<void> {
  try {
    sounds.value = await ui.sounds.list();
    // Before the first full load `error` belongs to that failed load (its Retry banner): a
    // lightweight success, e.g. a job-completion poll, must not wipe it.
    if (loaded.value) error.value = null;
  } catch (cause) {
    error.value = messageOf(cause);
  }
}

function fetchSounds(): Promise<void> {
  const run = loadSounds().finally(() => {
    inflightSounds = null;
  });
  inflightSounds = run;
  return run;
}

/**
 * Lightweight reload used after jobs finish and after edits. A request already in flight may
 * have been sent before the caller's change landed, so a call made meanwhile waits for it and
 * then fetches once more; every caller that arrives in the meantime shares that single trailing
 * request. A success clears `error` once the studio has loaded.
 */
function refreshSounds(): Promise<void> {
  const current = inflightSounds;
  if (!current) return fetchSounds();
  trailingSounds ??= current.then(() => {
    trailingSounds = null;
    // Another caller may already have started a (fresh enough) request in the gap.
    return inflightSounds ?? fetchSounds();
  });
  return trailingSounds;
}

type Id = string | null | undefined;

export function useStudio() {
  return {
    state,
    categories,
    seasons,
    profiles,
    sounds,
    loading,
    loaded,
    error,
    refresh,
    applySettings,
    refreshSounds,
    categoryById: (id: Id): Category | undefined => (id ? categoryIndex.value.get(id) : undefined),
    seasonById: (id: Id): Season | undefined => (id ? seasonIndex.value.get(id) : undefined),
    profileById: (id: Id): Profile | undefined => (id ? profileIndex.value.get(id) : undefined),
  };
}
