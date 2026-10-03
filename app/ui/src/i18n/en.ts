// English catalog. Keys are flat and dotted, grouped by area; later tasks append
// to the matching group. `es.ts` is typed against this object, so a missing
// Spanish string fails `vue-tsc` and the i18n spec.
export const en = {
  // --- app shell -----------------------------------------------------------
  "app.name": "Sound Effects",
  "app.fullName": "Sound Effects Studio",
  "app.skipToContent": "Skip to content",

  // --- navigation ----------------------------------------------------------
  "nav.label": "Main navigation",
  "nav.library": "Library",
  "nav.upload": "Upload",
  "nav.organize": "Organize",
  "nav.system": "System",

  // --- language switch -----------------------------------------------------
  "lang.label": "Language",
  "lang.en": "English",
  "lang.es": "Español",

  // --- common actions ------------------------------------------------------
  "common.save": "Save",
  "common.cancel": "Cancel",
  "common.close": "Close",
  "common.confirm": "Confirm",
  "common.delete": "Delete",
  "common.edit": "Edit",
  "common.retry": "Retry",
  "common.dismiss": "Dismiss",
  "common.loading": "Loading…",
  "common.back": "Back",
  "common.none": "None",
  "common.all": "All",
  "common.search": "Search",
  "common.apply": "Apply",

  // --- confirm dialog (defaults) ------------------------------------------
  "confirm.title": "Are you sure?",
  "confirm.message": "This action can't be undone.",
  "confirm.confirm": "Confirm",
  "confirm.cancel": "Cancel",

  // --- toasts --------------------------------------------------------------
  "toast.dismiss": "Dismiss notification",
  "toast.job.import": "Imported “{title}”",
  "toast.job.publish": "Published “{title}”",
  "toast.jobs.summary": "{n} jobs finished",
  "toast.jobs.summaryFailed": "{n} jobs finished, {failed} failed",
  "toast.job.importFailed": "Couldn't import “{title}”: {reason}",
  "toast.job.publishFailed": "Couldn't publish “{title}”: {reason}",
  "toast.job.previewFailed": "Couldn't render a preview of “{title}”: {reason}",

  // --- errors --------------------------------------------------------------
  "error.title": "Something went wrong",
  "error.network": "Can't reach Sound Effects Studio. Check your connection and try again.",
  "error.http": "Sound Effects Studio returned an error ({status}).",
  "error.unknown": "Unknown error",
  "error.invalidResponse": "Invalid server response",
  "player.error": "This sound couldn't be played.",

  // --- background jobs -----------------------------------------------------
  "jobs.title": "Jobs",
  "jobs.tray.label": "Background jobs",
  "jobs.active": "{n} in progress",
  "jobs.idle": "No jobs running",
  "jobs.empty": "No recent jobs.",
  "jobs.progress": "{title}: {n}% complete",
  "jobs.kind.import": "Import",
  "jobs.kind.publish": "Publish",
  "jobs.kind.preview": "Preview",
  "jobs.status.queued": "Queued",
  "jobs.status.running": "Running",
  "jobs.status.done": "Done",
  "jobs.status.failed": "Failed",

  // --- sound status --------------------------------------------------------
  "status.processing": "Processing",
  "status.ready": "Ready",
  "status.rendering": "Rendering",
  "status.failed": "Failed",

  // --- recipe validation (lib/recipe.ts) -----------------------------------
  "recipe.error.number": "Enter valid numbers.",
  "recipe.error.trimStart": "The start can't be negative.",
  "recipe.error.trimEnd": "The end is past the end of the file.",
  "recipe.error.trimOrder": "The start must come before the end.",
  "recipe.error.fadeNegative": "Fades can't be negative.",
  "recipe.error.fadeLong": "The fades are longer than the trimmed clip.",
  "recipe.error.gainRange": "Gain must be between −24 and +24 dB.",

  // --- views (placeholders until their tasks land) -------------------------
  "library.heading": "Your sounds",
  "library.empty.title": "No sounds yet",
  "library.empty.body": "Upload your first sound or import files you already have to start your library.",
  "library.empty.action": "Upload a sound",
  "upload.heading": "Add new sounds",
  "upload.empty.title": "Nothing to upload yet",
  "upload.empty.body": "Audio files you add will appear here with their progress.",
  "organize.heading": "Categories, seasons and profiles",
  "organize.empty.title": "Organize your library",
  "organize.empty.body": "Group sounds into categories, choose when they play and set how loud they are.",
  "system.heading": "Connection and storage",
  "system.empty.title": "System status",
  "system.empty.body": "Connection details, import tools and storage usage will appear here.",
  "editor.title": "Edit sound",
  "editor.empty.title": "Sound editor",
  "editor.empty.body": "Trim, level and publish this sound.",
} as const;
