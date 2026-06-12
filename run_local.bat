@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not defined COMBINIX_PORT set "COMBINIX_PORT=5000"
set "COMBINIX_URL=http://127.0.0.1:%COMBINIX_PORT%"

where py >nul 2>&1
if not errorlevel 1 goto :use_py
where python >nul 2>&1
if not errorlevel 1 goto :use_python
goto :python_error

:use_py
set "PYTHON_CMD=py -3"
goto :check_python

:use_python
set "PYTHON_CMD=python"
goto :check_python

:check_python
%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :python_version_error

if not exist "vendor\flask\__init__.py" goto :vendor_error
if not exist "vendor\werkzeug\__init__.py" goto :vendor_error
if not exist "vendor\openpyxl\__init__.py" goto :vendor_error

%PYTHON_CMD% -c "import app; import flask, werkzeug, openpyxl" >nul 2>&1
if errorlevel 1 goto :dependency_error

echo.
echo Iniciando Combinix Lovelace em %COMBINIX_URL%
echo Nenhum pacote sera instalado e nenhuma conexao com a internet e necessaria.
echo Para encerrar o servidor, feche esta janela ou pressione Ctrl+C uma vez.
start "" "%COMBINIX_URL%"
%PYTHON_CMD% app.py
if errorlevel 1 goto :app_error
exit /b 0

:python_error
echo.
echo ERRO: Python nao foi encontrado no computador.
echo Instale o Python 3.10 ou superior e marque a opcao para adicionar o Python ao PATH.
goto :finish_error

:python_version_error
echo.
echo ERRO: a versao do Python instalada e antiga.
echo Instale o Python 3.10 ou superior.
goto :finish_error

:vendor_error
echo.
echo ERRO: a pasta vendor esta incompleta.
echo Extraia novamente o ZIP completo em uma pasta nova antes de executar este arquivo.
goto :finish_error

:dependency_error
echo.
echo ERRO: nao foi possivel carregar as dependencias locais do Combinix.
echo Extraia novamente o ZIP completo em uma pasta nova.
echo Caso o problema continue, execute diagnostico_local.bat e envie o arquivo diagnostico_combinix.txt.
goto :finish_error

:app_error
echo.
echo ERRO: o servidor foi encerrado inesperadamente.
echo Consulte as mensagens exibidas acima para identificar a causa.
goto :finish_error

:finish_error
pause
exit /b 1
