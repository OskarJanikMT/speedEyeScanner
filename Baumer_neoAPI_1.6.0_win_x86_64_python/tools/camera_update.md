\page baumer_camera_update The baumer_camera_update

# The Baumer Camera Update CLI Tool

The `baumer_camera_update` is a command-line tool to update the firmware of Baumer cameras. It can be used interactively or integrated into scripts for automated deployment scenarios.

## Introduction

Cameras may receive firmware updates with new features or bugfixes. The `baumer_camera_update` tool provides a convenient way to apply these updates to single or multiple cameras simultaneously.

**Supported Update Formats:**
- `.guf` (Generic Update Format) - for newer camera models
- `.buf` (Baumer Update Format) - for legacy camera models

**Warning:** Device configuration may be lost when changing the firmware. Always backup your camera settings before updating.

## Prerequisites

- Connected camera(s) via USB3 Vision (U3V) or GigE Vision (GEV)
- Update file (.guf or .buf) matching your camera model

## Basic Usage

### List all detected cameras

`baumer_camera_update -l`

This command lists all connected Baumer cameras along with their serial numbers. It's useful to identify the cameras available for the update.

### Check and apply firmware update

`baumer_camera_update "path-to-update-container"`

Replace `"path-to-update-container"` with the actual path to your update file. This command checks all connected cameras to see if an update is possible. If compatible cameras are found, their serial numbers will be displayed, and you will be prompted to confirm the update.

### Update a specific camera

`baumer_camera_update -c "SERIAL NUMBER" -f "path-to-update-container"`

To update a specific camera, use the `-c` option followed by the camera's serial number, GUID, or MAC address. The `-f` option specifies the path to the update file. For example:

`baumer_camera_update -c 700001817369 -f bin/update.guf`

This command updates the camera with the serial number `700001817369` using the firmware file `update.guf` located in the `bin` directory.

### Automated update (skip confirmation)

`baumer_camera_update --auto "path-to-update-container"`

This command option skips the confirmation prompt and proceeds with the update automatically for all compatible cameras found.

## Command Line Parameters

| Parameter            | Description |
|----------------------|-------------|
| `-h, --help`        | Show all valid command line parameters with their description. |
| `-l, --list`        | Show all connected cameras with their serial numbers. |
| `-f, --file` ARG    | Path to the update file (.guf/.buf). |
| `-c, --camera` ARG  | Apply update only to the selected device (by serial number, GUID, or MAC address). |
| `--auto`            | Skip confirmation prompt and proceed automatically. |

## Exit Codes

The tool returns the following exit codes:

| Code | Meaning |
|------|---------|
| `0` | Success - all updates completed successfully |
| `> 0` | Error - one or more updates failed |
