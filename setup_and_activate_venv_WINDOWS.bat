@echo off
REM ==============================
REM Virtualenv setup for Windows
REM ==============================

REM Garante que estamos no diretório do script
cd /d %~dp0

REM Verifica se o Python está disponível
where python >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale o Python e marque a opcao "Add Python to PATH".
    pause
    exit /b 1
)

REM Verifica se a venv existe
IF NOT EXIST ".venv\" (
    echo [INFO] Virtualenv nao encontrada. Criando...
    python -m venv .venv

    IF %ERRORLEVEL% NEQ 0 (
        echo [ERRO] Falha ao criar a virtualenv.
        pause
        exit /b 1
    )
) ELSE (
    echo [INFO] Virtualenv ja existe.
)

REM Ativa a virtualenv
echo [INFO] Ativando a virtualenv...
call .venv\Scripts\activate.bat

REM Confirma ativacao
echo.
echo [OK] Virtualenv ativada.
python --version
