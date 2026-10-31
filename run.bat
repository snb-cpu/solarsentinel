@echo off
rem Windows launcher for the ML program (Pratham's laptop). Usage:   run.bat https://solarsentinel-api.pages.dev
rem Add  --key SECRET  after the address if the API has a key. Needs Python 3.9 to 3.13 (python.org, "Add python to PATH" ticked).
rem The first run builds the program's Python environment, which takes a few minutes. Not tested by me on Windows.
if "%~1"=="" (
  echo Give the API address, for example:  run.bat https://solarsentinel-api.pages.dev
  exit /b 2
)
cd /d "%~dp0\2-ml-ai"
if not exist venv\Scripts\python.exe (
  echo Setting up the ML program Python environment, first time only, a few minutes...
  python -m venv venv || ( echo Could not create it. Is Python installed and on the PATH? & exit /b 1 )
  venv\Scripts\python -m pip install --quiet -r requirements.txt || ( echo pip failed. Read the message above. & exit /b 1 )
)
venv\Scripts\python ml_worker.py --api %1 %2 %3
