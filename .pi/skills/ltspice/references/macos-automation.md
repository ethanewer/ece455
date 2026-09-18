# LTspice macOS automation

Use this reference only when an LTspice task requires GUI control or screenshots.

## Permission check

In **System Settings → Privacy & Security**:

- Enable the agent's host application under **Accessibility**.
- Enable it under **Screen & System Audio Recording**.
- Under **Automation**, allow it to control **System Events** and **LTspice**.

If the agent runs inside Visual Studio Code, grant permissions to Visual Studio Code. If it runs directly in Terminal, grant them to Terminal. Restart the host after changing permissions.

## Open a schematic

```bash
open -a LTspice /absolute/path/to/model.asc
```

Wait for the application to finish loading before sending UI actions. Confirm the expected process when necessary:

```bash
pgrep -fl 'LTspice|winewrapper'
```

## Drive menus

AppleScript can bring LTspice forward and activate menu items:

```bash
osascript \
  -e 'tell application "System Events"' \
  -e 'tell process "LTspice"' \
  -e 'set frontmost to true' \
  -e 'click menu item 3 of menu 1 of menu bar item "View" of menu bar 1' \
  -e 'delay 2' \
  -e 'end tell' \
  -e 'end tell'
```

Menu indexes can change between LTspice releases. Inspect menu item names before relying on an index. Use **Simulate → Run/Pause** to run the active schematic.

## Capture only LTspice

Read the front window position and size:

```bash
osascript -e 'tell application "System Events" to tell process "LTspice" to get {position, size} of window 1'
```

Then capture that rectangle:

```bash
screencapture -x -R<x>,<y>,<width>,<height> output.png
```

macOS Retina screenshots can have twice the pixel dimensions of the requested rectangle. This is expected. Inspect the saved PNG rather than assuming the crop is correct.

## Troubleshooting

- A full-desktop capture usually means the window rectangle was not used.
- A stale schematic usually means LTspice kept the previous file open. Close and reopen it after editing `.asc` text.
- If UI control fails despite visible permission toggles, restart both the host and LTspice.
- If a run produces no visible plot, inspect the `.log`, `.raw`, `.save`, and `.plt` files before changing the model.
