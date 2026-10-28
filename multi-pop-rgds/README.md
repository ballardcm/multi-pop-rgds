# Multi Pop for RG DS

> **AI disclosure:** This theme was developed with the help of AI, and its original system illustrations were AI-generated. Third-party components and their credits are listed below.

[DekosAnjo](https://github.com/DekosAnjo) contributed the additional systems in [PR #9](https://github.com/ballardcm/multi-pop-rgds/pull/9): Channel F, Odyssey², Famicom Disk System, MSX2, Mega CD, Super Cassette Vision, Mega Duck, Nintendo 64DD, Pokémon Mini, Doom, TIC-80, WASM-4, and Watara Supervision. DekosAnjo reported generating their system illustrations with **Nano Banana 2**; the corresponding cards and hero panels derive from those illustrations. These contributions retain the project’s CC BY-NC-SA 4.0 scope where applicable. The SVG logos retain their separate upstream credits and terms. AI assistance (Codex) was used for review fixes and integration.

For Anbernic RG DS with ROCKNIX 20261001. This is the installable theme folder, including the patched frontend.

Read the complete [install, update, removal and recovery instructions](https://github.com/ballardcm/multi-pop-rgds#install) before activating. Copy this folder to `/roms/themes/`, keep SSH enabled, then run:

```sh
bash /roms/themes/multi-pop-rgds/scripts/enable_multi_pop_rgds.sh
```

To remove, first close any game and run:

```sh
bash /roms/themes/multi-pop-rgds/scripts/restore_multi_pop_rgds.sh
```

Only delete this folder after restoration succeeds. Do not delete an active theme. Backups and user settings live outside the theme folder. Automatic updates are off until enabled under Theme Configuration; Check for updates runs an immediate check.

See [LICENSING.md](LICENSING.md) for attribution and third-party exceptions. Matching public frontend source accompanies releases. AI assistance was used in development; inherited system artwork was AI-generated.


## Logo artwork acknowledgments

Our sidebar marks come from HVR88’s [Monochrome Gaming Logos](https://github.com/HVR88/Monochrome-Gaming-Logos), Rookervik and the [RetroPie Carbon contributors](https://github.com/RetroPie/es-theme-carbon), and [Fabrice Caruso’s expanded Carbon collection](https://github.com/fabricecaruso/es-theme-carbon). Carbon builds on Nils Bonenberger’s Simple theme. Please support their work and the [Pegasus](https://pegasus-frontend.org/) and [GameOS](https://github.com/PlayingKarrde/gameOS) projects that inspired HVR88. These are third-party logos, not AI-generated Multi Pop illustrations. Full credits, modifications, pinned sources, and unmodified notices ship in [assets/logos/README.md](assets/logos/README.md).


## Date-based releases

Releases use labels such as **10.21.26.1**, aligned with Thor: month, day, year, and the release revision for that day. Existing 0.3.2 installations upgrade normally; the updater retains an internal ordering value separate from the displayed label.
