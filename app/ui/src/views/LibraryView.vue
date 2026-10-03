<script setup lang="ts">
import { mdiMusicBoxMultiple, mdiUpload } from "@mdi/js";
import EmptyState from "@/components/EmptyState.vue";
import Icon from "@/components/Icon.vue";
import { useI18n } from "@/i18n";

const { t } = useI18n();
</script>

<template>
  <div>
    <section data-test="library" aria-labelledby="library-heading">
      <h2 id="library-heading" class="mb-4 text-lg font-semibold">{{ t("library.heading") }}</h2>
      <EmptyState
        :icon="mdiMusicBoxMultiple"
        :title="t('library.empty.title')"
        :description="t('library.empty.body')"
      >
        <RouterLink :to="{ name: 'upload' }" class="btn-primary">
          <Icon :path="mdiUpload" />
          {{ t("library.empty.action") }}
        </RouterLink>
      </EmptyState>
    </section>
    <!-- Child route: the editor renders in a Sheet above this view, which stays mounted. -->
    <RouterView />
  </div>
</template>
