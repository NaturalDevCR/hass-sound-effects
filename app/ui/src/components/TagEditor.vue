<script setup lang="ts">
import { computed, useId } from "vue";
import { mdiClose, mdiPlus } from "@mdi/js";
import Icon from "@/components/Icon.vue";
import { useI18n } from "@/i18n";
import { addTag, slugifyTag } from "@/lib/tags";

// Generic tag list editor (v-model = the tags). Whatever is typed becomes a lowercase slug, the
// same normalization the backend applies, so what you see is what gets stored. `suggestions` are
// existing tags to pick from; the parent decides which ones to offer. `v-model:draft` (optional)
// exposes the text typed but not yet turned into a chip, so a parent that submits right away can
// include it instead of silently dropping it.
const props = defineProps<{ modelValue: string[]; suggestions?: string[]; label?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string[]] }>();
const draft = defineModel<string>("draft", { default: "" });

const { t } = useI18n();
const inputId = useId();
const hintId = useId();

const MAX_SUGGESTIONS = 12;

const pending = computed(() => slugifyTag(draft.value));
// What Enter would add: shown while typing so the stored (slugified) form is no surprise.
const preview = computed(() => (pending.value && !props.modelValue.includes(pending.value) ? pending.value : ""));
const offered = computed(() =>
  (props.suggestions ?? [])
    .filter((tag) => !props.modelValue.includes(tag) && (!pending.value || tag.includes(pending.value)))
    .slice(0, MAX_SUGGESTIONS),
);

function commit(tags: string[]): void {
  if (tags.length !== props.modelValue.length) emit("update:modelValue", tags);
}

function commitDraft(): void {
  commit(addTag(props.modelValue, draft.value));
  draft.value = "";
}

// Typing or pasting a comma ends a tag: everything before the last comma is committed, what
// follows stays in the field. Handled on `input` (not keydown) because mobile keyboards report
// their comma key as "Unidentified".
function onInput(event: Event): void {
  const el = event.target as HTMLInputElement;
  const parts = el.value.split(",");
  const rest = parts.pop() ?? "";
  if (parts.length) commit(parts.reduce<string[]>(addTag, [...props.modelValue]));
  draft.value = rest;
  el.value = rest; // the ref may not change (""), so write the DOM value ourselves
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== "Enter" || event.isComposing) return;
  event.preventDefault(); // never submit an enclosing form
  commitDraft();
}

function remove(tag: string): void {
  emit(
    "update:modelValue",
    props.modelValue.filter((existing) => existing !== tag),
  );
}

function pick(tag: string): void {
  commit(addTag(props.modelValue, tag));
  draft.value = ""; // the partial text was only a search for this suggestion
}
</script>

<template>
  <!-- Every button here swallows mousedown: that keeps focus in the field, so the blur that would
       commit a half-typed tag never fires before a click on a suggestion, Add or a remove cross. -->
  <div>
    <label :for="inputId" class="mb-1.5 block text-sm font-medium">{{ label ?? t("picker.tags.label") }}</label>
    <div class="flex gap-2">
      <input
        :id="inputId"
        :value="draft"
        type="text"
        class="field min-w-0 flex-1"
        :placeholder="t('picker.tags.placeholder')"
        :aria-describedby="preview ? hintId : undefined"
        enterkeyhint="done"
        autocapitalize="none"
        autocomplete="off"
        autocorrect="off"
        spellcheck="false"
        @input="onInput"
        @keydown="onKeydown"
        @blur="commitDraft"
      />
      <button
        data-test="add"
        type="button"
        class="btn shrink-0 px-3"
        :disabled="!pending"
        :aria-label="t('picker.tags.add')"
        @mousedown.prevent
        @click="commitDraft"
      >
        <Icon :path="mdiPlus" />
      </button>
    </div>

    <p v-if="preview" :id="hintId" data-test="pending" class="mt-1.5 text-xs break-words text-muted">
      {{ t("picker.tags.pending", { tag: preview }) }}
    </p>

    <ul v-if="modelValue.length" class="mt-2 flex flex-wrap gap-2">
      <li
        v-for="tag in modelValue"
        :key="tag"
        data-test="tag"
        class="inline-flex h-9 max-w-full items-center rounded-full border border-line bg-raised pl-3 text-sm"
      >
        <span class="min-w-0 truncate">{{ tag }}</span>
        <!-- The pill stays compact; the button reaches 44 px so a thumb can hit it. -->
        <button
          type="button"
          class="-my-1 -mr-1.5 grid size-11 shrink-0 place-items-center rounded-full text-muted hover:text-ink"
          :aria-label="t('picker.tags.remove', { tag })"
          @mousedown.prevent
          @click="remove(tag)"
        >
          <Icon :path="mdiClose" :size="16" />
        </button>
      </li>
    </ul>

    <div v-if="offered.length" data-test="suggestions" class="mt-3">
      <p class="mb-1.5 text-xs text-muted">{{ t("picker.tags.suggestions") }}</p>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="tag in offered"
          :key="tag"
          data-test="suggestion"
          type="button"
          class="chip max-w-full"
          @mousedown.prevent
          @click="pick(tag)"
        >
          <Icon :path="mdiPlus" :size="16" />
          <span class="min-w-0 truncate">{{ tag }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
