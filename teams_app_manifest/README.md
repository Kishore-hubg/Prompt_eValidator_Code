# Teams App Manifest Package

This folder contains a starter Teams app package for the bot bridge.

## Before upload

1. Replace `id` in `manifest.json` with a new app package GUID.
2. Replace `bots[0].botId` with your Azure Bot App ID (`BOT_APP_ID`).
3. Update developer URLs and display names.
4. Add icon files:
   - `color.png` (192x192)
   - `outline.png` (32x32)
5. Zip only these files:
   - `manifest.json`
   - `color.png`
   - `outline.png`

## Install

Upload the zip from Teams Admin Center or Teams client "Upload a custom app".
