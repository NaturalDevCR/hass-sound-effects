# Installation

Sound Effects has two parts: the **Sound Effects Studio** Supervisor App and the **Sound Effects** HACS integration. Install both; the integration reads the App's published catalog.

## Install the Supervisor App

1. In Home Assistant, go to **Settings → Apps → App store**.
2. Open the **⋮** menu, choose **Repositories**, and add `https://github.com/NaturalDevCR/hass-sound-effects`.
3. Find **Sound Effects Studio** in the App store, install it, then start it.
4. Open the App from the Home Assistant sidebar. On first startup it creates its API token and submits Supervisor discovery information.

The App publishes audio to `/config/www/sound-effects`, served by Home Assistant as `/local/sound-effects/...`. Home Assistant serves `/local` only if `/config/www` existed when Home Assistant started. If the App created that directory, restart Home Assistant once after starting the App.

## Install the HACS integration

1. In HACS, open **Integrations**, choose the menu, then **Custom repositories**.
2. Add `https://github.com/NaturalDevCR/hass-sound-effects` and select category **Integration**.
3. Download **Sound Effects** and restart Home Assistant.
4. Open **Settings → Devices & services** and confirm the discovered **Sound Effects Studio** instance.

The config flow enforces a single instance. When Supervisor rediscovers this App, Home Assistant updates the existing entry's host and token automatically.

## Manual setup

If discovery is unavailable, add **Sound Effects** from **Settings → Devices & services → Add integration**. Enter:

- **Host:** the hostname shown in Sound Effects Studio under **System → Connection**.
- **Port:** `8099`.
- **Token:** reveal or copy the token in **System → Connection**.

Use the App's hostname rather than its Ingress URL. The integration checks the connection and token during setup.

## Reconfigure or reauthenticate

To change connection details, open the integration's **Configure** flow and enter the current host, port and token. If the App rejects the saved token, Home Assistant starts a reauthentication flow; reveal/copy the current token in **System → Connection** and submit it. If the App is rediscovered, its current host and token update the existing config entry.

The integration's options configure the **Public base URL** used by playback devices, an optional **Season entity**, and the catalog **Scan interval** (10–3600 seconds; default 30 seconds).

## Update

Update Sound Effects Studio from the Supervisor App store and update the integration through HACS. Restart Home Assistant after an integration update if HACS requests it. The Studio keeps its data under its App data directory; its database and originals are included in App backups. Published files live in `/config/www/sound-effects` and belong to the Home Assistant configuration backup.

## Uninstall

Remove the integration through **Settings → Devices & services**. Removing its config entry deletes its cached catalog and shuffle history from Home Assistant storage. Uninstall Sound Effects Studio from the App store when no longer needed. App data remains in its App backup, and published files remain in `/config/www/sound-effects`; remove those files separately if you want to delete them. Keep the relevant backups if you may need either set of data later.
