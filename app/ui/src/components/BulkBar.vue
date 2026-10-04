<script setup lang="ts">
import { computed } from "vue";
import {
  mdiAlertCircleOutline,
  mdiCalendarMonth,
  mdiClose,
  mdiDelete,
  mdiFolderMove,
  mdiTagMultiple,
  mdiTune,
  mdiVolumeHigh,
  mdiVolumeOff,
} from "@mdi/js";
import Icon from "@/components/Icon.vue";
import { useI18n, type MessageKey } from "@/i18n";

export type BulkAction = "category" | "seasons" | "tags" | "normalize" | "enable" | "disable" | "delete";

// Fixed bar shown while selecting. `count` is how many sounds are selected, `total` how many the
// current filters list ("Select all (filtered)"). The parent runs the actions.
const props = defineProps<{ count: number; total: number; busy?: boolean; error?: string | null }>();
const emit = defineEmits<{ action: [name: BulkAction]; "select-all": []; done: [] }>();

const { t, tp } = useI18n();

const actions: { name: BulkAction; label: MessageKey; icon: string; danger?: boolean }[] = [
  { name: "category", label: "library.bulk.category", icon: mdiFolderMove },
  { name: "seasons", label: "library.bulk.seasons", icon: mdiCalendarMonth },
  { name: "tags", label: "library.bulk.tags", icon: mdiTagMultiple },
  { name: "normalize", label: "library.bulk.normalize", icon: mdiTune },
  { name: "enable", label: "library.bulk.enable", icon: mdiVolumeHigh },
  { name: "disable", label: "library.bulk.disable", icon: mdiVolumeOff },
  { name: "delete", label: "library.bulk.delete", icon: mdiDelete, danger: true },
];

const locked = computed(() => props.count === 0 || props.busy === true);
const allSelected = computed(() => props.total === 0 || props.count >= props.total);

function run(name: BulkAction): void {
  if (!locked.value) emit("action", name);
}
</script>

<template>
  <!-- Sits right above the phone tab bar; from md up the sidebar (w-60) owns the left edge. -->
  <div
    role="toolbar"
    :aria-label="t('library.bulk.label')"
    :aria-busy="busy ? 'true' : undefined"
    class="fixed inset-x-0 bottom-[var(--tabbar-h)] z-40 border-t border-line bg-raised/95 shadow-[0_-8px_24px_rgb(0_0_0/0.35)] backdrop-blur-md md:left-60"
  >
    <div class="mx-auto max-w-6xl px-3 pt-2 pb-2 md:px-6">
      <div class="flex items-center gap-2">
        <p data-test="count" aria-live="polite" class="min-w-0 flex-1 truncate text-sm font-semibold">
          {{ tp("library.bulk.count", count) }}
        </p>
        <button
          data-test="select-all"
          type="button"
          class="btn"
          :disabled="allSelected"
          @click="emit('select-all')"
        >
          {{ t("library.bulk.selectAll", { n: total }) }}
        </button>
        <button
          data-test="done"
          type="button"
          class="btn-ghost size-11 shrink-0 p-0!"
          :aria-label="t('library.bulk.done')"
          @click="emit('done')"
        >
          <Icon :path="mdiClose" :size="22" />
        </button>
      </div>

      <p
        v-if="error"
        role="alert"
        class="mt-2 flex items-start gap-2 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm break-words"
      >
        <Icon :path="mdiAlertCircleOutline" :size="18" class="mt-0.5 text-danger" />
        <span class="min-w-0 flex-1">{{ error }}</span>
      </p>

      <!-- Seven actions do not fit a 360 px screen: the strip scrolls (the next button peeks out as a
           hint), the page never does. Icon over label on phones, side by side from md up. -->
      <div class="no-scrollbar -mx-3 mt-2 flex gap-2 overflow-x-auto px-3 md:mx-0 md:flex-wrap md:overflow-visible md:px-0">
        <button
          v-for="action in actions"
          :key="action.name"
          :data-test="`action-${action.name}`"
          type="button"
          class="btn min-h-14 min-w-[4.5rem] shrink-0 flex-col gap-0.5 px-2 text-xs md:min-h-10 md:min-w-0 md:flex-row md:gap-2 md:px-4 md:text-sm"
          :class="{ 'text-danger!': action.danger }"
          :disabled="locked"
          @click="run(action.name)"
        >
          <Icon :path="action.icon" :size="18" />
          {{ t(action.label) }}
        </button>
      </div>
    </div>
  </div>
</template>
