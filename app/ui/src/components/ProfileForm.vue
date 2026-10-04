<script setup lang="ts">
import { ref, useId, watch } from "vue";
import { messageOf, ui } from "@/api/client";
import type { Profile, ProfileUpdateResult } from "@/api/types";
import { useI18n } from "@/i18n";
import { useStudio } from "@/composables/useStudio";
import { useJobs } from "@/composables/useJobs";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
const props = defineProps<{ profile?: Profile }>();
const emit = defineEmits<{
  saved: [profile: Profile];
  busy: [pending: boolean];
}>();
const { t, tp } = useI18n();
const id = useId();
const name = ref(props.profile?.name ?? "");
const values = ref({
  target_lufs: props.profile?.target_lufs ?? -16,
  true_peak: props.profile?.true_peak ?? -1.5,
  lra: props.profile?.lra ?? 11,
});
const controls = [
  { key: "target_lufs", label: "targetLufs", min: -30, max: -5, step: 0.5 },
  { key: "true_peak", label: "truePeak", min: -9, max: 0, step: 0.1 },
  { key: "lra", label: "lra", min: 1, max: 20, step: 0.5 },
] as const;
const pending = ref(false);
const error = ref<string | null>(null);
// A failed apply retries the saved change without PATCHing the same profile again.
const saved = ref<ProfileUpdateResult | null>(null);
watch(pending, (value) => emit("busy", value), { flush: "sync" });
async function submit(): Promise<void> {
  if (pending.value) return;
  if (!name.value.trim()) {
    error.value = t("form.nameRequired");
    return;
  }
  if (
    controls.some(
      (c) =>
        typeof values.value[c.key] !== "number" ||
        !Number.isFinite(values.value[c.key]) ||
        values.value[c.key] < c.min ||
        values.value[c.key] > c.max,
    )
  ) {
    error.value = t("profile.invalid");
    return;
  }
  pending.value = true;
  error.value = null;
  try {
    if (!saved.value) {
      const body = { name: name.value.trim(), ...values.value };
      saved.value = props.profile
        ? await ui.profiles.update(props.profile.id, body)
        : { profile: await ui.profiles.create(body), affected_sound_ids: [] };
      await useStudio().refresh();
      useToast().push(t("organize.saved"), "success");
    }
    const { profile, affected_sound_ids } = saved.value;
    if (
      affected_sound_ids.length &&
      (await useConfirm().confirm({
        title: tp("profile.rerender", affected_sound_ids.length),
        message: t("profile.rerender.message"),
        confirmLabel: t("common.apply"),
      }))
    ) {
      const { queued } = await ui.profiles.apply(profile.id, {
        sound_ids: affected_sound_ids,
      });
      await Promise.all([useStudio().refresh(), useJobs().refresh()]);
      useToast().push(tp("profile.queued", queued), "success");
    }
    emit("saved", profile);
  } catch (cause) {
    error.value = messageOf(cause);
  } finally {
    pending.value = false;
  }
}
</script>
<template>
  <form class="space-y-5" novalidate :aria-busy="pending" @submit.prevent="submit">
    <fieldset :disabled="pending || saved !== null" class="min-w-0 space-y-5">
      <div>
        <label :for="`${id}-name`" class="mb-1.5 block text-sm font-medium">{{ t("form.name") }}</label
        ><input :id="`${id}-name`" v-model="name" data-test="name" class="field" required maxlength="120" />
      </div>
      <div v-for="control in controls" :key="control.key" class="rounded-lg border border-line bg-ground p-3">
        <label :for="`${id}-${control.key}-number`" class="block text-sm font-medium">{{
          t(`profile.${control.label}`)
        }}</label>
        <div class="mt-2 flex min-w-0 items-center gap-3">
          <input
            v-model.number="values[control.key]"
            type="range"
            class="min-h-11 min-w-0 flex-1 accent-accent"
            :min="control.min"
            :max="control.max"
            :step="control.step"
            :aria-label="t(`profile.${control.label}`)"
            :aria-describedby="`${id}-${control.key}-help`"
          />
          <input
            :id="`${id}-${control.key}-number`"
            v-model.number="values[control.key]"
            :data-test="control.key"
            type="number"
            class="field w-24! shrink-0 tabular-nums"
            :min="control.min"
            :max="control.max"
            :step="control.step"
            :aria-describedby="`${id}-${control.key}-help`"
          />
        </div>
        <p :id="`${id}-${control.key}-help`" class="mt-2 text-sm text-muted">
          {{ t(`profile.${control.label}.hint`) }}
        </p>
      </div>
    </fieldset>
    <p v-if="error" role="alert" class="text-sm break-words text-danger">
      {{ error }}
    </p>
    <button type="submit" class="btn-primary w-full" :disabled="pending">
      {{ pending ? t("common.loading") : error && saved ? t("common.retry") : t("common.save") }}
    </button>
  </form>
</template>
