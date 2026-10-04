<script setup lang="ts">
import { computed, useId } from "vue";
import type { EditorDetails } from "@/composables/useSoundEditor";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import SeasonPicker from "./SeasonPicker.vue";
import TagEditor from "./TagEditor.vue";
const props = defineProps<{
  modelValue: EditorDetails;
  draft: string;
  dirty: boolean;
  valid: boolean;
  pending: boolean;
  blocked?: boolean;
  error: string | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: EditorDetails];
  "update:draft": [value: string];
  save: [];
}>();
const { t } = useI18n();
const { categories, sounds } = useStudio();
const id = useId();
const suggestions = computed(() => [...new Set(sounds.value.flatMap((s) => s.tags))].sort());
function change(patch: Partial<EditorDetails>) {
  emit("update:modelValue", { ...props.modelValue, ...patch });
}
</script>
<template>
  <form class="panel space-y-4" @submit.prevent="emit('save')">
    <h3 class="font-semibold">{{ t("editor.details") }}</h3>
    <fieldset :disabled="pending" class="min-w-0 space-y-4">
      <div>
        <label :for="`${id}-title`" class="mb-1.5 block text-sm">{{ t("editor.detailTitle") }}</label
        ><input
          :id="`${id}-title`"
          data-test="detail-title"
          type="text"
          :value="modelValue.title"
          class="field"
          required
          @input="change({ title: ($event.target as HTMLInputElement).value })"
        />
      </div>
      <div>
        <label :for="`${id}-category`" class="mb-1.5 block text-sm">{{ t("editor.category") }}</label
        ><select
          :id="`${id}-category`"
          :value="modelValue.category_id"
          class="field"
          @change="change({ category_id: ($event.target as HTMLSelectElement).value })"
        >
          <option v-for="category in categories" :key="category.id" :value="category.id">
            {{ category.name }}
          </option>
        </select>
      </div>
      <SeasonPicker
        :model-value="{ seasons: modelValue.seasons, all_seasons: modelValue.all_seasons }"
        @update:model-value="change($event)"
      />
      <TagEditor
        :model-value="modelValue.tags"
        :draft="draft"
        :suggestions="suggestions"
        @update:model-value="change({ tags: $event })"
        @update:draft="emit('update:draft', $event)"
      />
      <button
        type="button"
        role="switch"
        :aria-checked="modelValue.enabled"
        class="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg border border-line bg-ground px-3 py-2 text-sm"
        @click="change({ enabled: !modelValue.enabled })"
      >
        <span>{{ t("editor.enabled") }}</span>
        <span
          aria-hidden="true"
          class="relative h-6 w-11 shrink-0 rounded-full"
          :class="modelValue.enabled ? 'bg-accent-strong' : 'bg-hover'"
        >
          <span
            class="absolute top-0.5 left-0.5 size-5 rounded-full bg-white transition-transform"
            :class="{ 'translate-x-5': modelValue.enabled }"
          />
        </span>
      </button>
      <div>
        <label :for="`${id}-notes`" class="mb-1.5 block text-sm">{{ t("editor.notes") }}</label
        ><textarea
          :id="`${id}-notes`"
          :value="modelValue.notes"
          class="field min-h-24 resize-y"
          @input="change({ notes: ($event.target as HTMLTextAreaElement).value })"
        />
      </div>
    </fieldset>
    <p v-if="!valid" role="alert" class="text-sm text-warn">{{ t("editor.detailsInvalid") }}</p>
    <p v-if="error" role="alert" class="text-sm break-words text-danger">{{ error }}</p>
    <button
      data-test="save-details"
      type="submit"
      class="btn min-h-11! w-full"
      :disabled="!dirty || !valid || pending || blocked"
      :aria-busy="pending"
    >
      {{ t(pending ? "editor.publishPending" : "editor.saveDetails") }}
    </button>
  </form>
</template>
