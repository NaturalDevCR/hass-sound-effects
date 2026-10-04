# Sound Effects for Home Assistant

Sound Effects Studio is a Supervisor App for uploading, organizing, trimming and leveling audio, paired with a HACS integration that chooses a suitable sound for an automation and returns its playable URL and measured duration. Home Assistant automations remain in control of playback, so the App can be offline while cached selections continue to work.

## Features

- Organize sounds by category, season and tags.
- Trim, fade and normalize audio with reusable loudness profiles.
- Preview edits and test sounds on configured Home Assistant targets.
- Select sounds using a persistent shuffle bag with no immediate repeats.
- Keep a local catalog snapshot for selection while the Studio is offline.
- Use response data such as URL, duration, title and stable key in automations.

## How it works

```text
Sound Effects Studio publishes immutable MP3s to /config/www/sound-effects
        → Home Assistant serves them under /local/sound-effects
        → the integration caches the catalog and selects without network access
        → your automation plays the returned URL
```

The App owns audio editing and publishing; the integration owns catalog caching, season resolution and selection; automations own playback.

## Screenshots

Screenshots are coming soon: `docs/images/library.png`, `docs/images/editor.png`, and `docs/images/system.png`.

## Installation summary

1. In Home Assistant, open **Settings → Apps → App store → ⋮ → Repositories** and add `https://github.com/NaturalDevCR/hass-sound-effects`.
2. Install and start **Sound Effects Studio** from the App store.
3. In HACS, add `https://github.com/NaturalDevCR/hass-sound-effects` as a custom repository of category **Integration**, install **Sound Effects**, and restart Home Assistant.
4. Confirm the discovered Studio instance in **Settings → Devices & services**. See [Installation](docs/installation.md) for manual setup and update details.

## Quick example

```yaml
alias: Play a random door intro
triggers:
  - trigger: state
    entity_id: binary_sensor.front_door
    to: "on"
actions:
  - action: sound_effects.select
    data:
      category: intro
    response_variable: sound
  - action: media_player.play_media
    target:
      entity_id: media_player.hallway
    data:
      media_content_id: "{{ sound.url }}"
      media_content_type: "{{ sound.mime_type }}"
```

## Inicio rápido (Español)

Agregue el repositorio `https://github.com/NaturalDevCR/hass-sound-effects` a la tienda de Apps de Home Assistant e instale **Sound Effects Studio**. En HACS, agregue el mismo repositorio como integración personalizada, instale **Sound Effects** y reinicie Home Assistant. Confirme el descubrimiento automático y abra el panel para crear categorías, temporadas y cargar sonidos. Consulte la [guía de instalación](docs/installation.md) para configurar la conexión manualmente.

## Documentation

- [Installation](docs/installation.md)
- [Usage](docs/usage.md)
- [Automations](docs/automations.md)
- [API](docs/api.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development](docs/development.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
