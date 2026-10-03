<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { mdiWaveform } from "@mdi/js";
import EmptyState from "@/components/EmptyState.vue";
import Sheet from "@/components/Sheet.vue";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";

const props = defineProps<{ id: string }>();

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const { sounds } = useStudio();

const sound = computed(() => sounds.value.find((s) => s.id === props.id));

// Back when there is somewhere to go back to (opened from the list), otherwise
// (deep link) replace with Library so the sheet never traps the user.
function close(): void {
  if (router.options.history.state.back) router.back();
  else void router.replace({ name: "library", query: route.query });
}
</script>

<template>
  <Sheet :open="true" :title="sound?.title ?? t('editor.title')" @close="close">
    <EmptyState :icon="mdiWaveform" :title="t('editor.empty.title')" :description="t('editor.empty.body')" />
  </Sheet>
</template>
