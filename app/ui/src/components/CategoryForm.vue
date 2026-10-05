<script setup lang="ts">
import { ref, useId, watch } from "vue";
import { ui } from "@/api/client";
import type { Category } from "@/api/types";
import { useI18n } from "@/i18n";
import { useFormMutation } from "@/composables/useFormMutation";
import ColorPicker from "./ColorPicker.vue";
import IconPicker from "./IconPicker.vue";
import ProfilePicker from "./ProfilePicker.vue";
const props = defineProps<{ category?: Category }>();
const emit = defineEmits<{
  saved: [category: Category];
  busy: [pending: boolean];
}>();
const { t } = useI18n();
const id = useId();
const name = ref(props.category?.name ?? "");
const description = ref(props.category?.description ?? "");
const color = ref(props.category?.color ?? "#8b5cf6");
const colorValid = ref(true);
const icon = ref(props.category?.icon ?? "mdi:music-note");
const profile = ref<string | null>(props.category?.default_profile_id ?? null);
const { pending, error, save } = useFormMutation();
watch(pending, (value) => emit("busy", value), { flush: "sync" });
async function submit(): Promise<void> {
  if (pending.value) return;
  if (!name.value.trim()) {
    error.value = t("form.nameRequired");
    return;
  }
  if (!colorValid.value) {
    error.value = t("form.colorInvalid");
    return;
  }
  const body = {
    name: name.value.trim(),
    description: description.value.trim(),
    color: color.value,
    icon: icon.value,
    default_profile_id: profile.value,
  };
  await save(
    () => (props.category ? ui.categories.update(props.category.id, body) : ui.categories.create(body)),
    (category) => emit("saved", category),
  );
}
</script>
<template>
  <form class="space-y-5" novalidate :aria-busy="pending" @submit.prevent="submit">
    <fieldset :disabled="pending" class="min-w-0 space-y-5">
      <div>
        <label :for="`${id}-name`" class="mb-1.5 block text-sm font-medium">{{ t("form.name") }}</label
        ><input :id="`${id}-name`" v-model="name" data-test="name" class="field" required maxlength="120" />
      </div>
      <div>
        <label :for="`${id}-description`" class="mb-1.5 block text-sm font-medium">{{ t("form.description") }}</label
        ><textarea :id="`${id}-description`" v-model="description" class="field min-h-24" rows="3" />
      </div>
      <ColorPicker v-model="color" @valid="colorValid = $event" />
      <IconPicker v-model="icon" />
      <ProfilePicker v-model="profile" allow-none />
    </fieldset>
    <p v-if="error" role="alert" class="text-sm break-words text-danger">
      {{ error }}
    </p>
    <button type="submit" class="btn-primary w-full" :disabled="pending">
      {{ pending ? t("common.loading") : t("common.save") }}
    </button>
  </form>
</template>
