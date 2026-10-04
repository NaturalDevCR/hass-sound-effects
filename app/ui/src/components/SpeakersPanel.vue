<script setup lang="ts">
import AuditionTargets from "./AuditionTargets.vue";
import { useStudio } from "@/composables/useStudio";
import { useSettingsSave } from "@/composables/useSettingsSave";
import { useI18n } from "@/i18n";
const { state } = useStudio();
const { pending, error, save } = useSettingsSave();
const { t } = useI18n();
</script>
<template>
  <section class="panel min-w-0 space-y-4" aria-labelledby="speakers-heading">
    <h3 id="speakers-heading" class="font-semibold">{{ t("system.speakers") }}</h3>
    <AuditionTargets
      :targets="state?.settings.audition_targets ?? []"
      :pending="pending"
      :error="error"
      @save="save({ audition_targets: $event })"
    />
  </section>
</template>
