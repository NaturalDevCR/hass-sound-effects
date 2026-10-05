# Usage

Sound Effects Studio prepares and publishes audio. The `sound_effects` integration chooses an item from its cached catalog; your Home Assistant automation decides how and where to play it.

## Concepts

### Categories, seasons and tags

Categories group related sounds, such as `intro` or `announcement`. Each sound belongs to one category and has a stable `key`, which defaults to its original filename and can help preserve existing automation references.

Seasons have immutable IDs and display names. **Regular** is built in, has no date range, cannot be deleted, and is the fallback. Other seasons use inclusive yearly `MM-DD` ranges, including ranges that cross New Year. When ranges overlap, the higher priority season wins; ties are resolved by season ID. Sounds can belong to selected seasons or be marked **all seasons**.

Tags are lowercase labels used as required filters. For example, request `es` to limit a selection to sounds tagged for Spanish. A sound must match every requested tag; season fallback never relaxes tag requirements.

### Normalization profiles and loudness

Normalization profiles set a target integrated loudness in LUFS and true-peak ceiling in dBTP, with an LRA target. They make clips with different source volumes more consistent when played together. Choose a category default for new uploads/imports or assign a profile per sound. Gain is applied after normalization as a deliberate offset; a limiter protects the true-peak ceiling when normalization is active or positive gain is used. The original upload is preserved.

### Shuffle-bag selection

Selection is random without replacement within a round. Once all eligible sounds have been played, a new round begins and avoids immediately repeating the previous sound when another choice exists. Bags are separated by category, effective season and sorted requested tags, and persist across restarts. A single eligible sound can repeat. `dry_run` previews a pick without changing history.

## Studio views

The Studio is a Home Assistant sidebar panel. Its UI is described here as the Studio views; available controls are backed by the App's editing, organization and import features.

### Library

Browse by category, season and tag; search and preview published audio. The loudness strip shows the category's LUFS spread and can apply a profile to its sounds. Select multiple sounds for bulk category, season, tag and enabled-state changes or deletion.

### Editor

Open a sound to inspect its waveform and set trim points, gain, fades and normalization profile. Preview the rendered result, review published loudness and true peak, edit title/category/seasons/tags/enabled state/notes, then save and publish. **Test on speaker** sends an audition to a configured target; auditions do not change selection history.

### Upload

Upload one or more supported audio files. Set batch defaults for category, seasons, tags and normalization profile; uploads are transferred in chunks and show per-file progress and errors. The category's default profile is the initial profile choice where applicable.

### Organize

Create and edit categories, seasons and normalization profiles. Configure category default profiles; use yearly season date ranges and priority to define calendar selection. The season timeline and date probe show which season the calendar resolves for a date. Profile changes can offer to re-render affected sounds.

### System

Check connection details, discovery status, token, whether `/config/www` can serve files, and storage/jobs. This view also configures audition speakers, the media base URL, upload/duration limits, and imports files from the allowed Home Assistant configuration, media and share folders.

## Integration entities

The integration provides these default English entity IDs (Home Assistant may add a suffix for conflicts, and names can be customized):

- `sensor.sound_effects_studio_active_season`: current season ID, with `name`, `source`, and `color` attributes. Source is `override`, `entity`, `calendar`, or `default`. An explicit action season affects only that selection.
- `select.sound_effects_studio_season_override`: choose **Auto** or a season name. The choice persists across Home Assistant restarts. In Auto mode, resolution checks an optional configured season entity, then the calendar, then Regular.
- `sensor.sound_effects_studio_<category_name_slug>`: last selected title for that category, with sound ID, key, URL, duration, season, timestamp and current eligible count attributes.
- `binary_sensor.sound_effects_studio_connected`: diagnostic connectivity status, with catalog revision, last sync and App version attributes.

Category sensor IDs are derived from category names, without a `_last` suffix. The optional season entity is configured in integration options. Its state may match a season ID or name, case-insensitively. An explicit `season` passed to `sound_effects.select` has highest priority, followed by the override selector.

## Tips

- Keep legacy filenames as sound keys when migrating automations that use them for logs or comparisons.
- Use concise category IDs and consistent lowercase tags.
- Use the Studio's speaker audition to check media reachability; if speakers cannot reach Home Assistant's default URL, configure **System → Media base URL** in Studio for auditions. The integration’s **Public base URL** option separately controls URLs returned to automations.
- If `/config/www` was created after Home Assistant started, restart Home Assistant once so `/local` serves the published files.
- Use `sound_effects.reset_history` to restart a category's shuffle round, or `sound_effects.refresh` to request a catalog update.
