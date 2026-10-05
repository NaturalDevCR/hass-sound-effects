<script setup lang="ts">
import { ref, watch, useId } from "vue";
import { mdiSpeaker } from "@mdi/js";
import type { AuditionTarget } from "@/api/types";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/i18n";
import EmptyState from "./EmptyState.vue";
const props = defineProps<{ targets: AuditionTarget[]; pending?: boolean; error?: string | null }>();
const emit = defineEmits<{ save: [targets: AuditionTarget[]] }>();
const { t } = useI18n();
const id = useId();
const list = ref<AuditionTarget[]>(props.targets.map((target) => ({ ...target })));
const validation = ref<string | null>(null);
watch(
  () => props.targets,
  (targets, previous) => {
    // Refreshing another panel must not erase speaker drafts when the saved list is unchanged.
    if (JSON.stringify(targets) !== JSON.stringify(previous))
      list.value = targets.map((target) => ({ ...target }));
  },
);
function add() {
  list.value.push({
    id: `target-${crypto.getRandomValues(new Uint32Array(2)).join("-")}`,
    label: "",
    kind: "media_player",
    entity_id: "",
    volume: null,
  });
  validation.value = null;
}
async function remove(target: AuditionTarget) {
  if (
    props.targets.some((item) => item.id === target.id) &&
    !(await useConfirm().confirm({
      title: t("system.removeTarget", { label: target.label }),
      message: t("organize.delete.simple"),
      danger: true,
      confirmLabel: t("common.delete"),
    }))
  )
    return;
  list.value = list.value.filter((item) => item.id !== target.id);
  validation.value = null;
}
// Home Assistant's entity-id rule, plus the selected domain below.
const entityId = /^(?!.+__)(?!_)[\da-z_]+(?<!_)\.(?!_)[\da-z_]+(?<!_)$/;
function submit() {
  if (props.pending) return;
  validation.value = null;
  const ids = new Set<string>();
  for (const target of list.value) {
    const targetId = target.id.trim();
    if (!targetId || ids.has(targetId)) {
      validation.value = t("system.targetIdInvalid");
      return;
    }
    ids.add(targetId);
    if (!target.label.trim()) {
      validation.value = t("system.targetLabelInvalid");
      return;
    }
    const entity = target.entity_id.trim();
    if (
      !entityId.test(entity) ||
      (target.kind !== "media_player" && target.kind !== "script") ||
      entity.split(".")[0] !== target.kind
    ) {
      validation.value = t("system.targetInvalid", { kind: target.kind });
      return;
    }
    if (
      target.volume !== null &&
      (typeof target.volume !== "number" ||
        !Number.isFinite(target.volume) ||
        target.volume < 0 ||
        target.volume > 1)
    ) {
      validation.value = t("system.volumeInvalid");
      return;
    }
  }
  emit(
    "save",
    list.value.map((target) => ({
      ...target,
      id: target.id.trim(),
      label: target.label.trim(),
      entity_id: target.entity_id.trim(),
    })),
  );
}
</script>
<template>
  <form class="min-w-0 space-y-4" :aria-busy="pending" novalidate @submit.prevent="submit">
    <p class="text-sm text-muted">{{ t("system.speakersHint") }}</p>
    <fieldset :disabled="pending" class="min-w-0 space-y-3">
      <EmptyState
        v-if="!list.length"
        :icon="mdiSpeaker"
        :title="t('system.noSpeakers')"
        :description="t('system.noSpeakersHint')"
      >
        <button type="button" data-test="add-target" class="btn-primary min-h-11!" @click="add">
          {{ t("system.addTarget") }}
        </button>
      </EmptyState>
      <div
        v-for="target in list"
        :key="target.id"
        class="min-w-0 space-y-3 rounded-lg border border-line bg-ground p-3"
      >
        <div>
          <label :for="`${id}-${target.id}-label`" class="mb-1 block text-sm">{{
            t("system.targetLabel")
          }}</label>
          <input
            :id="`${id}-${target.id}-label`"
            v-model="target.label"
            data-test="target-label"
            class="field"
            required
          />
        </div>
        <div>
          <label :for="`${id}-${target.id}-kind`" class="mb-1 block text-sm">{{
            t("system.targetKind")
          }}</label>
          <select :id="`${id}-${target.id}-kind`" v-model="target.kind" data-test="target-kind" class="field">
            <option value="media_player">{{ t("editor.mediaPlayer") }}</option>
            <option value="script">{{ t("editor.script") }}</option>
          </select>
        </div>
        <div>
          <label :for="`${id}-${target.id}-entity`" class="mb-1 block text-sm">{{
            t("system.entity")
          }}</label>
          <input
            :id="`${id}-${target.id}-entity`"
            v-model="target.entity_id"
            data-test="target-entity"
            class="field"
            required
            :aria-describedby="`${id}-${target.id}-hint`"
            spellcheck="false"
          />
          <p :id="`${id}-${target.id}-hint`" class="mt-1 text-xs text-muted">
            {{ t("system.entityHint", { kind: target.kind }) }}
          </p>
        </div>
        <label class="flex min-h-11 cursor-pointer items-center gap-3 text-sm"
          ><input
            type="checkbox"
            class="size-5 accent-accent"
            :checked="target.volume !== null"
            @change="target.volume = target.volume === null ? 0.5 : null"
          />{{ t("system.setVolume") }}</label
        >
        <div v-if="target.volume !== null" class="space-y-2">
          <label :for="`${id}-${target.id}-volume`" class="block text-sm">{{ t("system.volume") }}</label>
          <input
            v-model.number="target.volume"
            type="range"
            min="0"
            max="1"
            step="0.01"
            class="min-h-11 w-full accent-accent"
            :aria-label="t('system.volume')"
            :aria-valuetext="Number(target.volume).toFixed(2)"
          />
          <input
            :id="`${id}-${target.id}-volume`"
            v-model.number="target.volume"
            data-test="target-volume"
            type="number"
            min="0"
            max="1"
            step="0.01"
            class="field"
          />
        </div>
        <button
          type="button"
          data-test="remove-target"
          class="btn-ghost min-h-11! max-w-full break-words text-danger!"
          @click="remove(target)"
        >
          {{ t("system.removeTarget", { label: target.label || t("system.speakers") }) }}
        </button>
      </div>
      <button v-if="list.length" data-test="add-target" type="button" class="btn min-h-11!" @click="add">
        {{ t("system.addTarget") }}
      </button>
    </fieldset>
    <p v-if="validation || error" role="alert" class="text-sm break-words text-danger">
      {{ validation || error }}
    </p>
    <button class="btn-primary min-h-11!" :disabled="pending">
      {{ pending ? t("editor.publishPending") : t("common.save") }}
    </button>
  </form>
</template>
