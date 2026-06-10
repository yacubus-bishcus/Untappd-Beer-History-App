# Windows Installer

Build the Windows desktop executable with PyInstaller, then wrap it in an Inno Setup installer.

Run these commands from a Windows machine with Python 3.12, Google Chrome, and Inno Setup 6 installed:

```powershell
python --version 
where iscc 
winget install JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build-installer.ps1
```

The script creates a local build virtual environment, installs the app dependencies, installs PyInstaller and `toga-winforms`, builds `dist\UntappdBeerHistory\UntappdBeerHistory.exe`, and then writes the installer to:

```text
dist\installer\Untappd-Beer-History-Setup-<version>.exe
```

If the `py` launcher is unavailable, pass a Python executable:

```powershell
.\packaging\windows\build-installer.ps1 -Python python -PythonVersion ""
```

If Inno Setup is installed somewhere unusual, pass the compiler path:

```powershell
.\packaging\windows\build-installer.ps1 -InnoCompiler "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

The installed app stores generated CSV, cache, config, and report files under:

```text
%LOCALAPPDATA%\Untappd Beer History
```
