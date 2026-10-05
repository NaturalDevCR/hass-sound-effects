<script setup lang="ts">
import { ref } from "vue";
import type { Category } from "@/api/types";
import { mdiPencilOutline, mdiTrashCanOutline, mdiFolderMusicOutline, mdiChevronUp, mdiChevronDown } from "@mdi/js";
import Icon from "./Icon.vue";
import EmptyState from "./EmptyState.vue";
import { useI18n } from "@/i18n";
import { resolveIcon } from "@/lib/icons";
defineProps<{ categories: Category[]; pending: boolean; actingId?: string | null }>();
const emit = defineEmits<{
  create: [];
  edit: [value: Category];
  remove: [value: Category];
  reorder: [index: number, delta: number];
}>();
const { t } = useI18n();
const list = ref<HTMLElement | null>(null);
function focusReorder(id: string, delta: number): void {
  const buttons = Array.from(list.value?.querySelectorAll<HTMLButtonElement>("button[data-direction]") ?? [])
    .filter((button) => button.dataset.categoryId === id);
  const same = buttons.find((button) => button.dataset.direction === String(delta));
  const target = same && !same.disabled ? same : buttons.find((button) => !button.disabled);
  target?.focus();
}
defineExpose({ focusReorder });
</script>
<template>
  <header class="mb-4 flex flex-wrap items-center justify-between gap-2">
    <h3 class="font-semibold">{{ t("organize.categories") }}</h3>
    <button type="button" class="btn-primary" :disabled="pending" @click="emit('create')">
      {{ t("organize.newCategory") }}
    </button>
  </header>
  <EmptyState
    v-if="!categories.length"
    :icon="mdiFolderMusicOutline"
    :title="t('organize.categories')"
    :description="t('organize.categories.empty')"
    ><button type="button" class="btn-primary" @click="emit('create')">
      {{ t("organize.newCategory") }}
    </button></EmptyState
  >
  <ul v-else ref="list" class="space-y-3">
    <li v-for="(category, index) in categories" :key="category.id" class="rounded-lg border border-line bg-ground p-3">
      <div class="flex min-w-0 items-center gap-3">
        <span class="grid size-11 shrink-0 place-items-center rounded-lg bg-raised" :style="{ color: category.color }"
          ><Icon :path="resolveIcon(category.icon)" :size="24"
        /></span>
        <div class="min-w-0 flex-1">
          <h4 class="break-words font-medium">{{ category.name }}</h4>
          <p v-if="category.description" class="mt-1 text-sm break-words text-muted">
            {{ category.description }}
          </p>
        </div>
      </div>
      <div class="mt-2 flex flex-wrap justify-end gap-1">
        <span class="mr-auto grid size-11 place-items-center">
          <span v-if="actingId === category.id" role="status" :aria-label="t('common.loading')" class="size-4 animate-spin rounded-full border-2 border-muted border-t-transparent" />
        </span>
        <button
          type="button"
          class="btn-ghost size-11 p-0!"
          :data-category-id="category.id"
          data-direction="-1"
          :disabled="pending || index === 0"
          :aria-label="t('organize.up', { name: category.name })"
          @click="emit('reorder', index, -1)"
        >
          <Icon :path="mdiChevronUp" />
        </button>
        <button
          type="button"
          class="btn-ghost size-11 p-0!"
          :data-category-id="category.id"
          data-direction="1"
          :disabled="pending || index === categories.length - 1"
          :aria-label="t('organize.down', { name: category.name })"
          @click="emit('reorder', index, 1)"
        >
          <Icon :path="mdiChevronDown" />
        </button>
        <button
          type="button"
          class="btn-ghost size-11 p-0!"
          :disabled="pending"
          :aria-label="t('organize.edit', { name: category.name })"
          @click="emit('edit', category)"
        >
          <Icon :path="mdiPencilOutline" />
        </button>
        <button
          type="button"
          class="btn-ghost size-11 p-0! text-danger!"
          :disabled="pending"
          :aria-label="t('organize.delete', { name: category.name })"
          @click="emit('remove', category)"
        >
          <Icon :path="mdiTrashCanOutline" />
        </button>
      </div>
    </li>
  </ul>
</template>
