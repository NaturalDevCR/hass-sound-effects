<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { mdiFolderOutline } from "@mdi/js";
import { ui, messageOf } from "@/api/client";
import type { BrowseResult } from "@/api/types";
import { formatBytes } from "@/lib/format";
import { useI18n } from "@/i18n";
import EmptyState from "./EmptyState.vue";
import Icon from "./Icon.vue";
const props = withDefaults(defineProps<{ pending?: boolean; canImport?: boolean }>(), { canImport: true });
const emit = defineEmits<{ import: [paths: string[]] }>();
const { t, tp } = useI18n();
const result = ref<BrowseResult>({ path: "", parent: null, roots: [], entries: [] });
const selected = ref(new Set<string>());
const loading = ref(false);
const error = ref<string | null>(null);
const requestedPath = ref("");
let ticket = 0;
const entries = computed(() =>
  [...result.value.entries]
    .filter((entry) => result.value.path || !result.value.roots.includes(entry.path))
    .sort((a, b) => Number(b.kind === "dir") - Number(a.kind === "dir") || a.name.localeCompare(b.name)),
);
const supported = computed(() => entries.value.filter((entry) => entry.kind === "file" && entry.supported));
const breadcrumbs = computed(() => {
  const root = result.value.roots.find(
    (root) => result.value.path === root || result.value.path.startsWith(`${root}/`),
  );
  if (!root) return [];
  const crumbs = [{ name: root, path: root }];
  const parts = result.value.path.slice(root.length).split("/").filter(Boolean);
  for (const name of parts) crumbs.push({ name, path: `${crumbs.at(-1)!.path}/${name}` });
  return crumbs;
});
async function browse(path: string) {
  const current = ++ticket;
  requestedPath.value = path;
  loading.value = true;
  error.value = null;
  try {
    const next = await ui.importer.browse(path);
    if (current === ticket) result.value = next;
  } catch (cause) {
    if (current === ticket) error.value = messageOf(cause);
  } finally {
    if (current === ticket) loading.value = false;
  }
}
function toggle(path: string) {
  const next = new Set(selected.value);
  if (!next.delete(path)) next.add(path);
  selected.value = next;
}
function selectSupported() {
  selected.value = new Set([...selected.value, ...supported.value.map((entry) => entry.path)]);
}
function clearSelection() {
  selected.value = new Set();
}
defineExpose({ clearSelection });
onMounted(() => browse(""));
onBeforeUnmount(() => {
  ticket++;
});
</script>
<template>
  <div class="min-w-0 space-y-4" :aria-busy="loading || pending">
    <nav :aria-label="t('system.roots')" class="flex flex-wrap gap-2">
      <button class="btn-ghost min-h-11!" :disabled="loading || pending" @click="browse('')">
        {{ t("system.roots") }}
      </button>
      <button
        v-for="root in result.roots"
        :key="root"
        :data-path="root"
        class="btn min-h-11! break-all"
        :aria-current="result.path === root ? 'location' : undefined"
        :disabled="loading || pending"
        @click="browse(root)"
      >
        {{ root }}
      </button>
    </nav>
    <nav
      v-if="breadcrumbs.length"
      :aria-label="t('system.parent')"
      class="flex flex-wrap items-center gap-1 text-sm"
    >
      <template v-for="crumb in breadcrumbs" :key="crumb.path">
        <span aria-hidden="true" class="text-muted">/</span>
        <button
          class="btn-ghost min-h-11! max-w-full break-all"
          :disabled="loading || pending"
          :aria-current="crumb.path === result.path ? 'location' : undefined"
          @click="browse(crumb.path)"
        >
          {{ crumb.name }}
        </button>
      </template>
    </nav>
    <button
      v-if="result.parent !== null"
      data-test="parent"
      class="btn min-h-11!"
      :disabled="loading || pending"
      @click="browse(result.parent)"
    >
      {{ t("system.parent") }}
    </button>
    <p v-if="loading" role="status" class="text-sm text-muted">{{ t("common.loading") }}</p>
    <div v-else-if="error" class="space-y-2">
      <p role="alert" class="text-sm break-words text-danger">{{ error }}</p>
      <button data-test="browse-retry" class="btn min-h-11!" @click="browse(requestedPath)">
        {{ t("common.retry") }}
      </button>
    </div>
    <template v-else>
      <button
        v-if="supported.length"
        data-test="select-supported"
        class="btn min-h-11!"
        :disabled="pending"
        @click="selectSupported"
      >
        {{ t("system.selectSupported") }}
      </button>
      <ul
        v-if="entries.length"
        class="max-h-80 space-y-1 overflow-y-auto overscroll-contain rounded-lg border border-line p-2"
      >
        <li v-for="entry in entries" :key="entry.path" data-test="entry" class="min-w-0">
          <button
            v-if="entry.kind === 'dir'"
            :data-path="entry.path"
            class="btn-ghost min-h-11! w-full justify-start! text-left"
            :disabled="pending"
            @click="browse(entry.path)"
          >
            <Icon :path="mdiFolderOutline" class="shrink-0" /><span class="min-w-0 break-all">{{
              entry.name
            }}</span>
          </button>
          <label
            v-else
            class="flex min-h-11 items-center gap-3 rounded-lg px-3 py-2 has-focus-visible:outline-2 has-focus-visible:outline-accent"
            :class="entry.supported ? 'cursor-pointer hover:bg-raised' : 'text-muted'"
          >
            <input
              v-if="entry.supported"
              type="checkbox"
              class="size-5 shrink-0 accent-accent"
              :checked="selected.has(entry.path)"
              :disabled="pending"
              @change="toggle(entry.path)"
            />
            <span class="min-w-0 flex-1"
              ><span class="block break-all text-sm">{{ entry.name }}</span
              ><span class="block text-xs text-muted">{{ formatBytes(entry.size) }}</span></span
            >
            <span
              v-if="entry.supported"
              class="shrink-0 rounded-full border border-ok/30 px-2 py-1 text-xs text-ok"
              >{{ t("system.supported") }}</span
            >
          </label>
        </li>
      </ul>
      <EmptyState
        v-else-if="result.path"
        :icon="mdiFolderOutline"
        :title="t('system.folderEmpty')"
        :description="t('system.folderEmptyHint')"
      >
        <button class="btn min-h-11!" :disabled="pending" @click="browse(result.parent ?? '')">
          {{ t("system.parent") }}
        </button>
      </EmptyState>
    </template>
    <slot />
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p data-test="selection-count" role="status" class="text-sm text-muted">
        {{ tp("system.selected", selected.size) }}
      </p>
      <button v-if="selected.size" class="btn-ghost min-h-11!" :disabled="pending" @click="clearSelection">
        {{ t("system.clearSelection") }}
      </button>
    </div>
    <button
      data-test="import-selected"
      class="btn-primary min-h-11! w-full"
      :disabled="pending || !canImport || !selected.size"
      @click="emit('import', [...selected])"
    >
      {{ pending ? t("system.importing") : tp("system.importFiles", selected.size) }}
    </button>
  </div>
</template>
