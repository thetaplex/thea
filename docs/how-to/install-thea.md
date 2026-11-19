# Install Thea

Thea is in beta. The installers do not have a code signature from Apple or Microsoft, so macOS and Windows show a warning the first time you open Thea. Use these steps to install Thea and to open it the first time.

Get the installer for your computer from the [Releases](https://github.com/thetaplex/thea/releases) page:

- macOS on Apple silicon: `Thea_<version>_aarch64.dmg`
- Windows: `Thea_<version>_x64-setup.exe`

## Install on macOS

1. Open the `.dmg` file.
2. Drag **Thea** to the **Applications** folder.
3. Open **Thea** from the **Applications** folder. macOS shows "Apple could not verify Thea is free of malware". Click **Done**.
4. Open **System Settings**, then click **Privacy & Security**.
5. Scroll down to **Security**. The text "Thea was blocked to protect your Mac" shows there. Click **Open Anyway**.
6. Type your password, then click **Open**.

macOS remembers your decision. Thea then opens without the warning.

## Install on Windows

1. Open the `-setup.exe` file. Windows shows "Windows protected your PC".
2. Click **More info**, then click **Run anyway**.
3. Do the steps of the installer.

## If macOS Says That Thea Is Damaged

Versions 0.1.0 and 0.1.1 have an incomplete code signature on macOS. macOS says "Thea is damaged and can't be opened" and has no **Open Anyway** button. Install version 0.1.2 or later.

To open version 0.1.0 or 0.1.1, drag Thea to the **Applications** folder, then type this command in **Terminal**:

```bash
xattr -dr com.apple.quarantine /Applications/Thea.app
```

The command removes the mark that macOS puts on files that you download. Thea then opens.
