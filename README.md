# Bodycam Map Kit

Make your own **custom maps for Bodycam** in Unreal Engine 5.5 and put them in the game as a new card in
**Play > Custom**, in all 7 modes (Hardpoint, Team Deathmatch, Deathmatch, Versus, Gun Game, Body Bomb, Wingman), with
bots that move.

Made by MrLovac (Prison V2P and Prison V3XXL on Nexus Mods). Fan-made: not made, supported or endorsed by Reissad Studio.

**Download:** green **Code** button > **Download ZIP**, then unzip it somewhere with a short path (e.g. `C:\BodycamMapKit`).

## What you need

| | |
|---|---|
| Bodycam | from Steam |
| Unreal Engine **5.5** | Epic Games Launcher > Unreal Engine > Library > + > **5.5**. Not 5.6 or newer: the game will not load it. |
| Git for Windows | https://gitforwindows.org (default options). Gives "Git Bash", which runs the build. |
| Python 3 + Pillow | https://www.python.org - tick **"Add python.exe to PATH"**, then in a command window: `py -m pip install Pillow` |

The kit contains **no file of the game**. On the first build it takes the few game files the build reads (the hardpoint
zone classes, a menu template and the list of files in the game's paks) from **your own** Bodycam install, with
Unreal's UnrealPak. It finds Bodycam through Steam; if it cannot, set `BCM_GAME` to the Bodycam folder, e.g.
`BCM_GAME="D:/SteamLibrary/steamapps/common/Bodycam" bash Scripts/newmap.sh ...`.

## Try it first (10 minutes)

The kit comes with a small test map. Close Bodycam, then open **Git Bash** in the kit folder. Git Bash is not in
the kit: it comes with Git for Windows (see What you need). Open the kit folder in Explorer, right-click an empty spot >
**Show more options** > **Open Git Bash here**. Do not double-click `newmap.sh`: its window closes before you can
read it. In the Git Bash window type:

```
bash Scripts/newmap.sh KitSample "Kit Sample" Sample/kit_sample_photo.png 0.1.0
```

The first run takes a few minutes. When it says `DONE`, start Bodycam > Play > Custom > **Kit Sample**. If it stops
with a line starting `***`, that line says what to fix. If you see an arena with an orange crate, your PC
can make maps. Remove the test card with `Saved/release/app/BodycamMapInstaller.exe --remove KitSample`.

## A full example: Prison V2P

The kit includes the level of the Prison V2P map (`Content/Sandbox/PrisonV2P/PrisonV2P_BP`, with its meshes in
`Content/Sandbox/Meshes/PrisonV2P`). Open it to see a finished map: team spawns, the hardpoint zone with its preview
points, lights, materials. To build your own version, save it under a NEW name first (File > Save Current Level As,
`Content/Sandbox/<Name>/<Name>_BP`). Please do not re-upload it as "Prison V2P"; make it your own and credit
"Prison V2P by MrLovac".

## Your own map

1. Open `BodycamSandbox.uproject` with Unreal 5.5.
2. Make a level and save it as `Content/Sandbox/<Name>/<Name>_BP`.
   `<Name>` = letters and digits, 2-13 characters, no spaces (and not the name of a Bodycam map or the word "lobby").
3. Put in the level:
   * **PlayerStart** actors standing flat on the ground, tagged `1` or `2` for the two sides (6 per side is good);
   * one **DirectionalLight** (sun) and one **SkyLight**;
   * for Hardpoint: **1 HardPointZone** and **2 to 32 BP_PointZonePreview**, from `Content/GM/Gamemode/HardPoint`.
4. **Everything your level uses must be inside `Content/Sandbox/<Name>/`** (your meshes, materials, textures), or be
   one of the game's own assets (the folders in `Content` that mirror the game). The packer refuses anything else and
   tells you which file.
5. Save, close Unreal, then in Git Bash:

```
bash Scripts/newmap.sh <Name> "<Name players see>" <a screenshot .png> 0.1.0
```

It checks the level, builds the 7 game modes, bakes the bot navigation, makes the menu card from your picture, cooks,
packs and installs. Each step says what it is doing; if something is wrong it stops with one sentence saying what to
fix. To update the map later run the same command with a higher version (0.1.1, 0.1.2 ...).

## Bought or downloaded assets

They work, including their own materials and shaders: they go into your map's files. Two rules from experience:

* Copy them into `Content/Sandbox/<Name>/` (rule 4 above). **Import the whole package, not just the level**: the level
  only points at its meshes, materials and textures, and the build needs all of them inside your map's folder.
* In your own materials, **every texture parameter needs a default texture of the same kind** (color texture on a color
  slot, normal map on a normal slot, mask texture on a mask slot). Without one the game cannot compile the material
  and draws everything plain grey. If your map looks grey in game, this is why.

Keep maps at a size the game is made for (a few hundred metres across): bots need a baked navigation mesh over the
whole map, and the build bakes it over the level's bounds.

## Sharing your map

The build writes your map to `Saved/maps/<Name>/` and installs it with `Saved/release/app/BodycamMapInstaller.exe`.
Players can use the same installer, or the web importer at https://lovac.github.io/bodycam-map-importer/ with the
`.bcmap` file from `Saved/maps/<Name>/`. Custom maps are for **private matches with bots**; everyone in a match needs
the same files.

## What is in the kit

* `BodycamSandbox.uproject`, `Config`, `Source`, `Binaries`, `Plugins/BodycamNativeStubs`: the Unreal project, with
  editor stand-ins for the game's own code and assets so your level can use them (nothing of the game is copied into
  your map).
* `Content/GM_Maps`: the 3 game-mode templates the build copies for your map.
* `Content/Sandbox/KitSample`, `Content/Sandbox/PrisonV2P`: the test map and the Prison V2P example.
* `Scripts/newmap.sh`, `Scripts/kit_game_files.py` and `Saved/prison2`, `Saved/hpgate`: the build (probe, modes,
  menu, cook, packing checks).
* `Saved/release/app`: the map installer (source: https://github.com/Lovac/bodycam-map-importer).

## Credits

* MrLovac: the kit, the build scripts, Kit Sample and Prison V2P.
* Reissad Studio: Bodycam. No file of the game is included; the build reads your own install.
* Epic Games: Unreal Engine 5.5. Scripts written with AI assistance (Claude, by Anthropic).

The scripts are under the MIT license (LICENSE). Bodycam, its names and its files belong to Reissad Studio.
