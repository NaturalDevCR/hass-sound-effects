# Troubleshooting

## The integration is not discovered

The App announces itself to Home Assistant when it starts. If you installed the HACS integration (and restarted Home Assistant) after the App was already running, that first announcement had nowhere to go. Restart the App once (**Settings → Apps → Sound Effects Studio → Restart**); a **Sound Effects** card then appears under **Settings → Devices & services → Discovered**. Manual setup always works too.

## Integration cannot connect

Check **System → Connection** in Sound Effects Studio and confirm the integration uses the displayed hostname, port `8099`, and current API token. If the token was rotated, use the integration's reauthentication flow or reconfigure it with the new token. The host must be reachable from Home Assistant on its local network; do not use the App's Ingress panel URL.

## Published files return 404 under `/local`

Home Assistant serves `/local` only when `/config/www` existed at Home Assistant startup. Start the App, then restart Home Assistant once if that directory was created afterward. Check the `/config/www` status in the Studio's System view.

## Speakers cannot fetch the returned URL

The integration's default media base URL may not be reachable by your playback device. Set **Public base URL** in the integration options to an address that your speakers can reach, including the scheme and port if needed. This setting affects the returned `url`; the returned `path` remains under `/local/sound-effects/`.

## No eligible sound

Check that the category contains enabled sounds with a published revision. Confirm each has the requested tags and is assigned to the effective season or **all seasons**. If no sound matches the selected seasonal period, the integration retries against **Regular**, but it does not relax tag filters. A `sound_effects.select` validation error means none matched after that fallback.

## Render or upload fails

Check the per-file error and the Studio App log. Unsupported or corrupt input files are rejected; ffmpeg render errors are recorded in the App log and sound status. Supported input formats include MP3, WAV, FLAC, OGG/Opus, M4A/AAC, WebM, MP4 and MOV (audio stream only). Uploading over plain HTTP is supported and is not by itself a cause of failure; uploads use chunked requests.

## Studio App is offline

After a catalog has been cached, the integration can keep selecting from that snapshot while Studio is offline. The connectivity binary sensor turns off, but selection remains available. On a first setup without a cached catalog, the integration needs the App to be reachable.

## Download diagnostics

Open **Settings → Devices & services → Sound Effects → Download diagnostics** to collect the integration's connection and cached-catalog summary. The token is redacted. Include the diagnostics and relevant App log excerpt when reporting a connection or selection issue.
