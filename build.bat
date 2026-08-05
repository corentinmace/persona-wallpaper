@echo off
REM Produit dist\main.exe : meme chemin que l'ancien build, la tache
REM planifiee Windows n'a pas besoin d'etre modifiee.
REM
REM --onefile     un seul fichier directement dans dist\ (pas dist\main\)
REM --name main   le nom attendu par la tache existante
REM --windowed    aucune console, ni pour le run horaire ni pour la GUI
REM               (d'ou l'importance du fichier de log)

pyinstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --noconsole ^
  --hidden-import win32api ^
  --hidden-import win32con ^
  --hidden-import win32gui ^
  main.py

REM Les assets ne sont PAS embarques dans l'exe : ils restent remplacables
REM sans rebuild. app_dir() pointe sur le dossier de l'exe, donc dist\assets.
xcopy /E /I /Y assets dist\assets

echo.
echo Build termine : dist\main.exe
echo Config GUI    : dist\main.exe --config
