# Release maintenance and update testing

> [!IMPORTANT]
> **No further releases may be published from this repository after the transition release (10.28.26.Transition).** Multi Pop RG DS is now developed and released from [ballardcm/multi-pop](https://github.com/ballardcm/multi-pop) under `systems/rgds`, and this repository will be deleted on 2026-11-27. A later `build-` release here would reach only devices that have not yet installed the transition, and would strand them on a repository that is going away.

A release has an installable `multi-pop-rgds-rocknix-20261001.zip`, a matching `multi-pop-rgds-source.zip`, and `SHA256SUMS`. The source download contains the tracked project files, pinned upstream frontend sources, SDL headers source, and pugixml source. Firmware libraries, credentials, user data and compiler caches are excluded. Install manifests hash every shipped theme file. The packager rejects unverified binaries, changed build inputs, substituted source archives, symlinks and embedded service-key literals.

## Build and package

Follow `frontend-build/README.md`. Register the validated binary hash, source/firmware revisions, and exact compiled input hashes in `frontend-build/release.json` and `multi-pop-rgds/frontend/compatibility.json`. Any frontend patch or compiler change requires rebuilding and testing a new binary. Theme-only updates may reuse that binary.

Published packages use date labels such as **10.21.26.1**: month, day, two-digit year, and that day's release revision. `release-version.json` records the local date (America/Los_Angeles) and revision. Start a new date at 1 and increment the revision for additional releases that day; coordinate the same label in Thor and RG DS when shipping together. The first release under this scheme is 10.21.26.1.

Packaging writes the date label into the theme and derives a separate monotonic ordering integer for compatibility with existing updaters. That integer remains greater than legacy RG DS version 302 and is never used as the new theme's display label. The source version files are a development baseline; the release configuration determines the packaged label.

The default branch is currently `prototype/rgds`. PRs get checked installable/source preview downloads; publishing occurs only when `release.yml` is manually dispatched on that default branch. Releases retain `build-<commit>` tags for updater compatibility. The workflow rejects duplicate public date labels, and existing release tags are never overwritten.

Stage all intended source changes in Git, run the checks, and package:

```sh
python3 tools/check-rgds.py
python3 tools/test-auto-update.py
python3 tools/test-package-release.py
python3 tools/package-release.py \
  --frontend multi-pop-rgds/frontend/emulationstation \
  --upstream-source /path/to/emulationstation-source.tar.gz \
  --sdl-source /path/to/SDL2-source.tar.gz \
  --output .local/release
```

The matching `pugixml-source.tar.gz` must be next to the upstream archive. All three archives are pinned in `frontend-build/release.json`. The packager inventories Git-tracked files, not ignored local storage. Make the final release from the reviewed merge commit on the default branch. Verify noreply commit metadata and retain the corresponding source download with every binary.

## Publish a reviewed release

After the release PR checks and device acceptance pass, merge through GitHub using the repository-owner handle and noreply address. Verify the resulting commit metadata, then run:

```sh
gh workflow run release.yml --repo ballardcm/multi-pop-rgds --ref prototype/rgds
```

The workflow recovers the verified frontend and source inputs from the pinned 0.3.2 release, checks their individual hashes, packages the reviewed commit, and publishes the installable ZIP, matching source ZIP, and `SHA256SUMS`. This is a manual maintainer action: merging a PR does not publish a release.

For local packaging, run `python3 tools/fetch-release-inputs.py` first. Downloads stay under ignored `.local/release-inputs`; each extracted input is checked against `frontend-build/release.json`. Use those paths with the packaging command above. Keep the release date and daily revision coordinated with Thor; do not reuse a published label.

## Transition to the monorepo

The transition release is labelled **10.28.26.Transition** through the optional `label` field in `release-version.json`. The label replaces the revision only in the displayed version; the updater still orders it by date and revision, as 20261028001, which is newer than 10.27.26.1 (20261027001). It keeps the `build-<commit>` tag, the firmware revision and the three startup helpers (`start_es_rgds.sh`, `start_after_reboot.sh`, `multi_pop_rgds_common.sh`) byte-identical to 10.27.26.1, because the installed updater refuses a release that changes any of them.

Its one functional change is where the updater looks. It reads the release list of `ballardcm/multi-pop`, skips drafts and prereleases, keeps only `rgds-MM.DD.YY.N` tags that carry `SHA256SUMS` and the installable ZIP, and picks the newest by the date and revision in the tag rather than by the order the API returns. Thor, `rgds-frontend-` and the old `build-` and `v` tags are ignored. If the first page has no match, up to two more pages are read. An empty result is reported as up to date; an unreachable or missing repository is logged as a failed check and the installed theme keeps running.

Monorepo RG DS releases must therefore keep an integer `version` above 20261028001, the same firmware revision and the same three startup helpers, or they will be skipped or refused just as before.

`tools/fetch-release-inputs.py` still recovers the pinned frontend inputs from this repository's 0.3.2 release; set `release_repo` in `frontend-build/release.json` to fetch them from another repository once they are republished there.

## Migration from 0.3.2

The installed 0.3.2 updater already accepts build-commit tags and separate display labels. The first date-based package therefore upgrades normally without a bridge updater or changes to the startup helpers. Its integer ordering value is greater than 302, while the user sees **10.21.26.1**.

Tests cover legacy-to-date staging/apply/confirmation, downgrade rejection, public-label stamping, daily revision ordering, the next-day reset, invalid dates, and deterministic packages. Device acceptance also exercises the shipped 0.3.2 updater, deliberate unconfirmed-candidate rollback, and successful confirmation of the final date-based package before publishing.

## Public automatic updates

An Internet-connected device checks GitHub directly. Checks run after frontend startup when Automatic updates is On, at most every six hours. A manual Check for updates bypasses that interval and the Off setting. Downloads are validated, staged and applied only on the next frontend start. A started update is confirmed only when the installed theme frontend is the process serving the local API and its binary hash matches. After repeated unconfirmed starts, the old theme is restored. One backup is retained.

Do not change activation scripts via an automatic update. Such releases need explicit removal/reinstallation because the on-device startup override and backup records also need updating. This restriction is checked during apply. The updater runs under a process lock, preserves settings, and never restarts gameplay to apply an update.

## Private releases or USB-only devices

Before public launch, GitHub requires authentication. For local testing, use the Mac's authenticated GitHub CLI through a loopback-only relay; no token is copied to the handheld. The same relay is useful when a handheld has USB networking but no Internet.

On the computer with this source checkout and `gh auth login` completed:

```sh
python3 tools/release-relay.py
```

The relay reads `ballardcm/multi-pop` and serves only its RG DS releases. To try a release before it is public, add `--prerelease` to include prereleases, or `--tag rgds-MM.DD.YY.N` to serve that one release even as a draft; the relay clears the prerelease and draft flags so the device will install it. `--repo` relays another repository, which with `--tag` serves a `build-` release of this one to a device that has not yet installed the transition.

In another computer terminal, keep this SSH tunnel running (replace the destination):

```sh
ssh -N -R 127.0.0.1:18765:127.0.0.1:18765 root@RK3566.local
```

On the RG DS:

```sh
mkdir -p /storage/.config/multi-pop-rgds
printf '%s\n' '{"release_api":"http://127.0.0.1:18765/releases"}' \
  > /storage/.config/multi-pop-rgds/update-source.json
```

The relay serves only the selected RG DS releases and their approved install assets. `/release` serves the newest one alone, which is what updaters before the transition expect. Keep both the computer relay and SSH tunnel alive during checks/downloads. For the normal public Internet path, delete the override:

```sh
rm -f /storage/.config/multi-pop-rgds/update-source.json
```

A missing relay or failed network check leaves the installed version running. It does not establish Internet sharing for games or scrapers.

## End-to-end acceptance

Install release A using the README, with automatic updates enabled. Publish a newer release B containing identical activation helpers. Start the frontend normally (after the six-hour interval, or clear the local `update/last-check` marker in a controlled test), observe B staged, then restart the frontend. Confirm its displayed version, `update/installed.json`, every release-manifest hash, active service, correct executable and 1920×480 canvas, both powered panels, unchanged game data/settings, and no pending update. Test corrupted archives and rollback separately with the automated suite.

## Manual rollback

Turn automatic updates Off first. Download the desired release's installable ZIP and SHA256SUMS, verify it on your computer, and copy it to `/storage/downloads/` on the RG DS. While the frontend is idle, run:

```sh
python3 /roms/themes/multi-pop-rgds/scripts/update_theme.py \
  /storage/downloads/multi-pop-rgds-rocknix-20261001.zip EXPECTED_SHA256
```

This checks the archive and activation records, keeps a backup, and restarts only an idle frontend. If it refuses a changed startup helper or firmware mismatch, use the full remove/install procedure instead. Do not remove the running theme folder manually.
