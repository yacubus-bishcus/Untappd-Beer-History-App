@echo off
setlocal

cd /d "%~dp0\..\.."

set "PYTHON_DOWNLOAD_URL=https://www.python.org/downloads/"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
  if %errorlevel%==0 (
    set "PY_CMD=py -3"
  ) else (
    echo Python 3.9+ is required, but the detected py launcher points to an older version.
    echo Please install the official Python 3.12 release from python.org.
    set /p OPEN_PYTHON=Open the Python download page now? [Y/n] 
    if /I not "%OPEN_PYTHON%"=="n" start "" "%PYTHON_DOWNLOAD_URL%"
    exit /b 1
  )
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
    if %errorlevel%==0 (
      set "PY_CMD=python"
    ) else (
      echo Python 3.9+ is required, but the detected python is too old.
      echo Please install the official Python 3.12 release from python.org.
      set /p OPEN_PYTHON=Open the Python download page now? [Y/n] 
      if /I not "%OPEN_PYTHON%"=="n" start "" "%PYTHON_DOWNLOAD_URL%"
      exit /b 1
    )
  ) else (
    echo Python 3.9+ is required, but no Python installation was found.
    echo Please install the official Python 3.12 release from python.org.
    set /p OPEN_PYTHON=Open the Python download page now? [Y/n] 
    if /I not "%OPEN_PYTHON%"=="n" start "" "%PYTHON_DOWNLOAD_URL%"
    exit /b 1
  )
)

if not exist ".venv" (
  %PY_CMD% -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt >nul

python -c "import tkinter" >nul 2>nul
if %errorlevel%==0 (
  python desktop_launcher.py
) else (
  echo Tkinter is not available in this Python build.
  echo Please install the official Python 3.12 release from python.org, which includes Tkinter.
  set /p OPEN_PYTHON=Open the Python download page now? [Y/n] 
  if /I not "%OPEN_PYTHON%"=="n" start "" "%PYTHON_DOWNLOAD_URL%"
  echo Falling back to the browser-based Streamlit app...
  python run.py streamlit
)

endlocal
