<script lang="ts">
/** Emitted when "Category default" is chosen (only offered with `allowCategoryDefault`). */
export const CATEGORY_DEFAULT = "__category_default__";
</script>

<script setup lang="ts">
import { computed, useId } from "vue";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import { formatLufs } from "@/lib/format";

// Generic normalization-profile chooser (v-model). Values: a profile id, `null` for "No
// normalization" (needs `allowNone`), CATEGORY_DEFAULT (needs `allowCategoryDefault`), or
// `undefined` while nothing is chosen yet.
const props = defineProps<{ modelValue?: string | null; allowNone?: boolean; allowCategoryDefault?: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: string | null] }>();

const { t } = useI18n();
const { profiles } = useStudio();
const name = useId();

type Option = { key: string; value: string | null; title: string; hint: string };

const options = computed<Option[]>(() => {
  const list: Option[] = [];
  if (props.allowCategoryDefault) {
    list.push({
      key: "category-default",
      value: CATEGORY_DEFAULT,
      title: t("picker.profile.categoryDefault"),
      hint: t("picker.profile.categoryDefaultHint"),
    });
  }
  if (props.allowNone) {
    list.push({ key: "none", value: null, title: t("picker.profile.none"), hint: t("picker.profile.noneHint") });
  }
  for (const profile of profiles.value) {
    list.push({ key: profile.id, value: profile.id, title: profile.name, hint: formatLufs(profile.target_lufs) });
  }
  return list;
});
</script>

<template>
  <div role="radiogroup" :aria-label="t('picker.profile.label')" class="space-y-2">
    <label
      v-for="option in options"
      :key="option.key"
      data-test="option"
      class="group flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-line bg-ground px-3 py-2 transition-colors hover:bg-raised has-checked:border-accent has-checked:bg-accent-soft has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-accent"
    >
      <input
        type="radio"
        class="sr-only"
        :name="name"
        :checked="modelValue === option.value"
        @change="emit('update:modelValue', option.value)"
      />
      <span
        aria-hidden="true"
        class="grid size-5 shrink-0 place-items-center rounded-full border border-muted group-has-checked:border-accent"
      >
        <span class="size-2.5 scale-0 rounded-full bg-accent transition-transform group-has-checked:scale-100" />
      </span>
      <span class="min-w-0 flex-1 truncate text-sm font-medium">{{ option.title }}</span>
      <span class="shrink-0 text-sm text-muted tabular-nums">{{ option.hint }}</span>
    </label>
    <p v-if="!profiles.length" class="px-1 text-sm text-muted">{{ t("picker.profile.empty") }}</p>
  </div>
</template>
