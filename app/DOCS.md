# Sound Effects Studio

Sound Effects Studio is a Home Assistant panel for importing, organizing, editing and normalizing sound effects. It publishes ready-to-use audio files for the Sound Effects HACS integration.

## First steps

1. Open **Sound Effects** from the Home Assistant sidebar.
2. Create categories and seasons that match how you organize your sounds.
3. Upload audio files, or import them from the folders available in the App's import screen.
4. Install the **Sound Effects** integration through HACS. It discovers this App automatically and loads its catalog.

If discovery does not configure the integration, add it manually. Use the App hostname shown in **System → Connection** in the App (also listed on the App's page in Home Assistant) as the host, port `8099`, and copy the token from **System → Connection** in the App.

## Normalization profiles

Choose a built-in profile when preparing a sound: **Standard** balances everyday effects, **Loud** raises perceived loudness, **Soft** keeps effects quieter, and **Voice** is tuned for spoken clips. You can adjust the profile controls for an individual sound before publishing. Processing creates an MP3 suitable for Home Assistant playback while preserving the original upload in the App's data.

## Seasons

Assign a sound to one or more seasons to control when it appears in the integration. The built-in **Regular** season is always available. Seasonal entries can have date ranges, priorities, colors and icons; use **all seasons** for a sound that should remain available year-round.

## Testing on speakers

Configure your speakers in **System** before using the test controls. For Music Assistant or Snapcast setups, prefer a Home Assistant script as the test target when the speaker entity does not play directly or needs a group/routing step.

## Published files and `/local`

The App publishes processed files under `/config/www/sound-effects` in Home Assistant. Home Assistant serves these as `/local/sound-effects/...`. Home Assistant only serves `/local` when its `www` directory existed at startup. If you create `/config/www` after Home Assistant has started, restart Home Assistant. The App shows a banner when its published files are not reachable through `/local`.

## Backups

The Home Assistant App backup includes Sound Effects Studio's database, uploads and other App data. Published files are stored in `/config/www/sound-effects` and are included in Home Assistant backups. Keep a Home Assistant backup before removing the App if you need to retain published files.

## Troubleshooting

- If the panel does not load, check the App log and confirm the App is running.
- If the integration cannot connect, confirm it uses the App hostname shown in **System → Connection**, port `8099`, and the current token shown in **System → Connection**.
- If sounds appear in the catalog but do not play, check the `/local` status banner and restart Home Assistant if `www` was created after startup.
- If an import is missing, check that its source folder is available to the App and that the audio format is supported.

## Español

Sound Effects Studio permite organizar, importar y normalizar efectos de sonido para Home Assistant. Abra el panel **Sound Effects**, cree categorías y temporadas, y luego cargue o importe sus archivos. Instale la integración de Sound Effects desde HACS; se conecta automáticamente con la aplicación. Si `/config/www` se creó después de iniciar Home Assistant, reinicie Home Assistant para que `/local` pueda servir los archivos publicados. Los datos de la aplicación y los archivos publicados se incluyen en las copias de seguridad correspondientes de Home Assistant.
