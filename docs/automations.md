# Automations

`sound_effects.select` chooses a published sound and returns data for your own playback action. It does not play audio.

## `sound_effects.select`

| Field | Required | Description |
| --- | --- | --- |
| `category` | Yes | Category ID or name. |
| `tags` | No | List of required tags; all must match. A comma-separated string is also accepted. |
| `season` | No | Season ID or name to use for this selection. |
| `dry_run` | No | Defaults to `false`; returns a pick without changing shuffle history, last-selection entities, events or Studio counters. |

Use `response_variable` on the action to capture the result. The response fields are `sound_id`, `key`, `title`, `category`, `tags`, `season`, `requested_season`, `season_fallback`, `url`, `path`, `duration`, `revision`, and `mime_type`. `path` is the `/local/sound-effects/...` path; `url` combines that path with the integration's configured public base URL.

If no sound matches the category, effective season and all tags (including Regular fallback), the action raises a validation error. Use `continue_on_error: true` when your automation has a fallback path.

## Door-opened intro

This example plays the selected sound and waits for its measured duration before continuing:

```yaml
alias: Play a door intro
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
  - delay:
      seconds: "{{ sound.duration }}"
```

## Music Assistant announcement

Pass the returned URL to Music Assistant's announcement action:

```yaml
actions:
  - action: sound_effects.select
    data:
      category: announcement
    response_variable: sound
  - action: music_assistant.play_announcement
    target:
      entity_id: media_player.kitchen
    data:
      url: "{{ sound.url }}"
```

## Filter by language tag

```yaml
actions:
  - action: sound_effects.select
    data:
      category: announcement
      tags:
        - es
    response_variable: sound
  - action: media_player.play_media
    target:
      entity_id: media_player.kitchen
    data:
      media_content_id: "{{ sound.url }}"
      media_content_type: "{{ sound.mime_type }}"
```

## Migrate from a hardcoded catalog with fallback

Before, an automation may keep a catalog and random index in `variables:`:

```yaml
variables:
  old_catalog:
    - key: greeting_one
      url: /local/old/greeting-one.mp3
      duration: 2.4
    - key: greeting_two
      url: /local/old/greeting-two.mp3
      duration: 3.1
```

After importing the files and retaining their keys, try the integration first. If selection fails (for example, if there are no eligible sounds), choose from the old catalog. Keep the existing playback steps after `sound` is set:

```yaml
variables:
  old_catalog:
    - key: greeting_one
      url: /local/old/greeting-one.mp3
      duration: 2.4
    - key: greeting_two
      url: /local/old/greeting-two.mp3
      duration: 3.1
actions:
  - action: sound_effects.select
    continue_on_error: true
    data:
      category: announcement
    response_variable: selected_sound
  - variables:
      sound: >-
        {{ selected_sound if selected_sound is defined
           else (old_catalog | random) }}
  - action: media_player.play_media
    target:
      entity_id: media_player.kitchen
    data:
      media_content_id: "{{ sound.url }}"
      media_content_type: "{{ sound.mime_type | default('audio/mpeg') }}"
```

Home Assistant continues after a failed selection because `continue_on_error` is set. For a production migration, preserve the automation's existing device routing, timing and other playback behavior around the selection change.

## Test with `dry_run`

Use Developer Tools → Actions to call the action with `dry_run: true` and request its response:

```yaml
action: sound_effects.select
data:
  category: intro
  dry_run: true
```

The response shows which sound would be selected but does not advance the shuffle bag, update last-selected entities, fire `sound_effects_selected`, or report a selection to the Studio.

## React to a selection event

Each non-dry-run selection fires `sound_effects_selected` with the selection response payload. For example, log selected keys with an automation:

```yaml
alias: Log sound selections
triggers:
  - trigger: event
    event_type: sound_effects_selected
actions:
  - action: logbook.log
    data:
      name: Sound Effects
      message: "Selected {{ trigger.event.data.title }} ({{ trigger.event.data.key }})"
```
