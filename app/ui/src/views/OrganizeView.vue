<script setup lang="ts">
import { computed, ref } from "vue";
import { messageOf, ui } from "@/api/client";
import type { Category, Season, Profile } from "@/api/types";
import OrganizeCategories from "@/components/OrganizeCategories.vue";
import OrganizeSeasons from "@/components/OrganizeSeasons.vue";
import OrganizeProfiles from "@/components/OrganizeProfiles.vue";
import Sheet from "@/components/Sheet.vue";
import CategoryForm from "@/components/CategoryForm.vue";
import SeasonForm from "@/components/SeasonForm.vue";
import ProfileForm from "@/components/ProfileForm.vue";
import { useStudio } from "@/composables/useStudio";
import { useConfirm } from "@/composables/useConfirm";
import { useToast } from "@/composables/useToast";
import { useI18n } from "@/i18n";
const { t } = useI18n();
const { categories, seasons, profiles, loaded, loading, refresh, error: loadError } = useStudio();
const tabs = ["categories", "seasons", "profiles"] as const;
type Tab = (typeof tabs)[number];
type Editor =
  | { kind: "categories"; value?: Category }
  | { kind: "seasons"; value?: Season }
  | { kind: "profiles"; value?: Profile };
const tab = ref<Tab>("categories");
const editor = ref<Editor | null>(null);
const formBusy = ref(false);
const pending = ref(false);
const acting = ref<{ kind: Tab; id: string } | null>(null);
const announcement = ref("");
const error = ref<string | null>(null);
const title = computed(() => {
  const kind = editor.value?.kind;
  if (kind === "categories") return t(editor.value?.value ? "organize.editCategory" : "organize.newCategory");
  if (kind === "seasons") return t(editor.value?.value ? "organize.editSeason" : "organize.newSeason");
  return t(editor.value?.value ? "organize.editProfile" : "organize.newProfile");
});
function open(value: Editor): void {
  if (!pending.value) {
    editor.value = value;
    error.value = null;
  }
}
function close(): void {
  if (!formBusy.value) editor.value = null;
}
function tabKey(event: KeyboardEvent): void {
  let index = tabs.indexOf(tab.value);
  if (event.key === "ArrowRight") index = (index + 1) % 3;
  else if (event.key === "ArrowLeft") index = (index + 2) % 3;
  else if (event.key === "Home") index = 0;
  else if (event.key === "End") index = 2;
  else return;
  event.preventDefault();
  tab.value = tabs[index]!;
  (event.currentTarget as HTMLElement).querySelector<HTMLButtonElement>(`#organize-tab-${tab.value}`)?.focus();
}
async function reorder(index: number, delta: number): Promise<void> {
  if (pending.value || index + delta < 0 || index + delta >= categories.value.length) return;
  const moved = categories.value[index]!;
  const ids = categories.value.map((c) => c.id);
  [ids[index], ids[index + delta]] = [ids[index + delta]!, ids[index]!];
  pending.value = true;
  acting.value = { kind: "categories", id: moved.id };
  announcement.value = "";
  error.value = null;
  try {
    await ui.categories.reorder(ids);
    await refresh();
    announcement.value = t("organize.position", { name: moved.name, n: index + delta + 1, total: ids.length });
  } catch (cause) {
    error.value = messageOf(cause);
    useToast().push(error.value, "error");
  } finally {
    pending.value = false;
    acting.value = null;
  }
}
async function remove(kind: Tab, value: Category | Season | Profile): Promise<void> {
  if (pending.value || (kind === "seasons" && value.id === "regular")) return;
  const confirmed = await useConfirm().confirm({
    title: t("organize.delete.title", { name: value.name }),
    message: t(kind === "seasons" ? "organize.delete.message" : "organize.delete.simple"),
    danger: true,
    confirmLabel: t("common.delete"),
  });
  if (!confirmed || pending.value) return;
  pending.value = true;
  acting.value = { kind, id: value.id };
  error.value = null;
  try {
    await ui[kind].remove(value.id);
    await refresh();
    useToast().push(t("organize.deleted"), "success");
  } catch (cause) {
    error.value = messageOf(cause);
    useToast().push(error.value, "error");
  } finally {
    pending.value = false;
    acting.value = null;
  }
}
</script>
<template>
  <section class="min-w-0 space-y-4" aria-labelledby="organize-heading">
    <h2 id="organize-heading" class="text-xl font-semibold">
      {{ t("organize.heading") }}
    </h2>
    <div v-if="!loaded" class="panel">
      <p v-if="loading" role="status">{{ t("common.loading") }}</p>
      <template v-else
        ><p v-if="loadError" role="alert" class="break-words text-danger">
          {{ loadError }}
        </p>
        <button type="button" class="btn-primary mt-3" @click="refresh">
          {{ t("common.retry") }}
        </button></template
      >
    </div>
    <template v-else>
      <div
        role="tablist"
        :aria-label="t('organize.heading')"
        class="grid grid-cols-3 gap-1 rounded-lg border border-line bg-surface p-1 xl:hidden"
        @keydown="tabKey"
      >
        <button
          v-for="key in tabs"
          :id="`organize-tab-${key}`"
          :key="key"
          type="button"
          role="tab"
          :aria-selected="tab === key"
          :aria-controls="`organize-${key}`"
          :tabindex="tab === key ? 0 : -1"
          class="min-h-11 min-w-0 rounded-md px-1 text-sm font-medium"
          :class="tab === key ? 'bg-accent-soft text-ink' : 'text-muted hover:bg-hover'"
          @click="tab = key"
        >
          {{ t(`organize.${key}`) }}
        </button>
      </div>
      <p
        v-if="error"
        role="alert"
        class="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm break-words text-danger"
      >
        {{ error }}
      </p>
      <p class="sr-only" aria-live="polite" aria-atomic="true">{{ announcement }}</p>
      <div class="grid min-w-0 gap-4 xl:grid-cols-3" :aria-busy="pending">
        <section
          id="organize-categories"
          role="tabpanel"
          aria-labelledby="organize-tab-categories"
          class="panel min-w-0 self-start"
          :class="tab === 'categories' ? 'block' : 'hidden xl:block'"
        >
          <OrganizeCategories
            :categories="categories"
            :pending="pending"
            :acting-id="acting?.kind === 'categories' ? acting.id : null"
            @create="open({ kind: 'categories' })"
            @edit="open({ kind: 'categories', value: $event })"
            @remove="remove('categories', $event)"
            @reorder="reorder"
          />
        </section>
        <section
          id="organize-seasons"
          role="tabpanel"
          aria-labelledby="organize-tab-seasons"
          class="panel min-w-0 self-start"
          :class="tab === 'seasons' ? 'block' : 'hidden xl:block'"
        >
          <OrganizeSeasons
            :seasons="seasons"
            :pending="pending"
            :acting-id="acting?.kind === 'seasons' ? acting.id : null"
            @create="open({ kind: 'seasons' })"
            @edit="open({ kind: 'seasons', value: $event })"
            @remove="remove('seasons', $event)"
          />
        </section>
        <section
          id="organize-profiles"
          role="tabpanel"
          aria-labelledby="organize-tab-profiles"
          class="panel min-w-0 self-start"
          :class="tab === 'profiles' ? 'block' : 'hidden xl:block'"
        >
          <OrganizeProfiles
            :profiles="profiles"
            :pending="pending"
            :acting-id="acting?.kind === 'profiles' ? acting.id : null"
            @create="open({ kind: 'profiles' })"
            @edit="open({ kind: 'profiles', value: $event })"
            @remove="remove('profiles', $event)"
          />
        </section>
      </div>
    </template>
    <Sheet :open="editor !== null" :title="title" @close="close">
      <CategoryForm
        v-if="editor?.kind === 'categories'"
        :category="editor.value"
        @saved="editor = null"
        @busy="formBusy = $event"
      />
      <SeasonForm
        v-else-if="editor?.kind === 'seasons'"
        :season="editor.value"
        @saved="editor = null"
        @busy="formBusy = $event"
      />
      <ProfileForm
        v-else-if="editor?.kind === 'profiles'"
        :profile="editor.value"
        @saved="editor = null"
        @busy="formBusy = $event"
      />
    </Sheet>
  </section>
</template>
