<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import type { Category } from "@/api/types";
import Icon from "@/components/Icon.vue";
import { useI18n } from "@/i18n";
import { resolveIcon } from "@/lib/icons";

// `counts` maps category id -> sounds to show for it (the parent decides which filters apply),
// `total` is the count behind "All". `null` is the "All" selection.
const props = defineProps<{
  categories: Category[];
  modelValue: string | null;
  counts: Record<string, number>;
  total: number;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string | null] }>();

const { t } = useI18n();
const group = ref<HTMLElement | null>(null);

// A category restored from the URL (or picked elsewhere) may sit off screen in the scroller:
// bring the active chip into view on mount and whenever the selection changes.
function reveal(): void {
  group.value?.querySelector<HTMLElement>('[aria-pressed="true"]')?.scrollIntoView?.({ block: "nearest", inline: "center" });
}

onMounted(reveal);
watch(() => props.modelValue, reveal, { flush: "post" });
</script>

<template>
  <!-- Bleeds to the screen edges on phones and scrolls sideways with snapping; wraps from md up. -->
  <div
    ref="group"
    role="group"
    :aria-label="t('library.categories')"
    class="no-scrollbar -mx-4 flex snap-x snap-proximity scroll-px-4 gap-2 overflow-x-auto px-4 py-1 md:mx-0 md:flex-wrap md:overflow-visible md:px-0"
  >
    <button
      type="button"
      class="snap-start"
      :class="modelValue === null ? 'chip-active' : 'chip'"
      :aria-pressed="modelValue === null"
      @click="emit('update:modelValue', null)"
    >
      {{ t("common.all") }}
      <span class="text-xs text-muted tabular-nums">{{ total }}</span>
    </button>
    <button
      v-for="category in categories"
      :key="category.id"
      type="button"
      class="snap-start"
      :class="modelValue === category.id ? 'chip-active' : 'chip'"
      :aria-pressed="modelValue === category.id"
      @click="emit('update:modelValue', category.id)"
    >
      <span
        data-test="dot"
        aria-hidden="true"
        class="size-2.5 shrink-0 rounded-full"
        :style="{ backgroundColor: category.color }"
      />
      <Icon :path="resolveIcon(category.icon)" :size="18" />
      <span>{{ category.name }}</span> <span class="text-xs text-muted tabular-nums">{{ counts[category.id] ?? 0 }}</span>
    </button>
  </div>
</template>
