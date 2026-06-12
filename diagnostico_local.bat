@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "LOG=diagnostico_combinix.txt"
(
  echo Diagnostico Combinix Lovelace 2.2.0-hybrid
  echo Data: %date% %time%
  echo Pasta: %cd%
  echo.
  echo ==== Localizacao do Python ====
  where py 2^>^&1
  where python 2^>^&1
  echo.
  echo ==== Versoes ====
  py -3 --version 2^>^&1
  python --version 2^>^&1
  echo.
  echo ==== Arquivos vendor essenciais ====
  if exist "vendor\flask\__init__.py" (echo Flask: OK) else (echo Flask: AUSENTE)
  if exist "vendor\werkzeug\__init__.py" (echo Werkzeug: OK) else (echo Werkzeug: AUSENTE)
  if exist "vendor\openpyxl\__init__.py" (echo openpyxl: OK) else (echo openpyxl: AUSENTE)
  echo.
  echo ==== Teste usando py -3 ====
  py -3 -c "import app; import flask, werkzeug, openpyxl; print('Importacoes OK'); print('Versao app:', app.APP_VERSION)" 2^>^&1
  echo.
  echo ==== Teste usando python ====
  python -c "import app; import flask, werkzeug, openpyxl; print('Importacoes OK'); print('Versao app:', app.APP_VERSION)" 2^>^&1
) > "%LOG%"
echo.
echo Diagnostico criado em:
echo %cd%\%LOG%
echo.
pause
