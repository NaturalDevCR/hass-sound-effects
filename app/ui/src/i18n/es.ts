import type { en } from "./en";

// Español neutro (Costa Rica / Latinoamérica). Typed against the English
// catalog: a missing or extra key is a compile error.
export const es: Record<keyof typeof en, string> = {
  // --- app shell -----------------------------------------------------------
  "app.name": "Sound Effects",
  "app.fullName": "Sound Effects Studio",
  "app.skipToContent": "Saltar al contenido",

  // --- navigation ----------------------------------------------------------
  "nav.label": "Navegación principal",
  "nav.library": "Biblioteca",
  "nav.upload": "Subir",
  "nav.organize": "Organizar",
  "nav.system": "Sistema",

  // --- language switch -----------------------------------------------------
  "lang.label": "Idioma",
  "lang.en": "English",
  "lang.es": "Español",

  // --- common actions ------------------------------------------------------
  "common.save": "Guardar",
  "common.cancel": "Cancelar",
  "common.close": "Cerrar",
  "common.confirm": "Confirmar",
  "common.delete": "Eliminar",
  "common.edit": "Editar",
  "common.retry": "Reintentar",
  "common.dismiss": "Descartar",
  "common.loading": "Cargando…",
  "common.back": "Volver",
  "common.none": "Ninguno",
  "common.all": "Todos",
  "common.search": "Buscar",
  "common.apply": "Aplicar",

  // --- confirm dialog (defaults) ------------------------------------------
  "confirm.title": "¿Estás seguro?",
  "confirm.message": "Esta acción no se puede deshacer.",
  "confirm.confirm": "Confirmar",
  "confirm.cancel": "Cancelar",

  // --- toasts --------------------------------------------------------------
  "toast.dismiss": "Cerrar notificación",
  "toast.job.import": "Se importó «{title}»",
  "toast.job.publish": "Se publicó «{title}»",
  "toast.job.importFailed": "No se pudo importar «{title}»: {reason}",
  "toast.job.publishFailed": "No se pudo publicar «{title}»: {reason}",
  "toast.job.previewFailed": "No se pudo generar la vista previa de «{title}»: {reason}",

  // --- errors --------------------------------------------------------------
  "error.title": "Algo salió mal",
  "error.network": "No se pudo conectar con Sound Effects Studio. Revisa tu conexión e inténtalo de nuevo.",
  "error.http": "Sound Effects Studio respondió con un error ({status}).",
  "error.unknown": "Error desconocido",
  "player.error": "No se pudo reproducir este sonido.",

  // --- background jobs -----------------------------------------------------
  "jobs.title": "Tareas",
  "jobs.tray.label": "Tareas en segundo plano",
  "jobs.active": "{n} en curso",
  "jobs.idle": "Sin tareas en curso",
  "jobs.empty": "No hay tareas recientes.",
  "jobs.progress": "{title}: {n}% completado",
  "jobs.kind.import": "Importación",
  "jobs.kind.publish": "Publicación",
  "jobs.kind.preview": "Vista previa",
  "jobs.status.queued": "En cola",
  "jobs.status.running": "En proceso",
  "jobs.status.done": "Listo",
  "jobs.status.failed": "Falló",

  // --- sound status --------------------------------------------------------
  "status.processing": "Procesando",
  "status.ready": "Listo",
  "status.rendering": "Renderizando",
  "status.failed": "Falló",

  // --- recipe validation (lib/recipe.ts) -----------------------------------
  "recipe.error.number": "Ingresa números válidos.",
  "recipe.error.trimStart": "El inicio no puede ser negativo.",
  "recipe.error.trimEnd": "El final queda después del fin del archivo.",
  "recipe.error.trimOrder": "El inicio debe ir antes del final.",
  "recipe.error.fadeNegative": "Los fundidos no pueden ser negativos.",
  "recipe.error.fadeLong": "Los fundidos son más largos que el fragmento recortado.",
  "recipe.error.gainRange": "La ganancia debe estar entre −24 y +24 dB.",

  // --- views (placeholders until their tasks land) -------------------------
  "library.heading": "Tus sonidos",
  "library.empty.title": "Aún no hay sonidos",
  "library.empty.body": "Sube tu primer sonido o importa archivos que ya tengas para empezar tu biblioteca.",
  "library.empty.action": "Subir un sonido",
  "upload.heading": "Agregar sonidos nuevos",
  "upload.empty.title": "Nada que subir todavía",
  "upload.empty.body": "Los archivos de audio que agregues aparecerán aquí con su progreso.",
  "organize.heading": "Categorías, temporadas y perfiles",
  "organize.empty.title": "Organiza tu biblioteca",
  "organize.empty.body": "Agrupa los sonidos en categorías, elige cuándo suenan y define qué tan fuertes son.",
  "system.heading": "Conexión y almacenamiento",
  "system.empty.title": "Estado del sistema",
  "system.empty.body": "Aquí aparecerán los datos de conexión, las herramientas de importación y el uso de almacenamiento.",
  "editor.title": "Editar sonido",
  "editor.empty.title": "Editor de sonido",
  "editor.empty.body": "Recorta, nivela y publica este sonido.",
};
