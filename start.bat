@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  TMS 8.0 - Toyota Loom Monitoring System
::  Script profissional de inicializacao
:: ============================================================

:: Configuracoes
set PORT=8000
set HOST=0.0.0.0
set APP=tms.app.main:app
set DB_URL=postgresql+psycopg://tms:tms@localhost:5432/tms
set DB_PORT=5432

:: Diretorio do script
cd /d "%~dp0"

echo ========================================
echo   TMS 8.0 - Toyota Loom Monitoring System
echo ========================================

:: ------------------------------------------------------------------
:: 1. Verificar se o PostgreSQL esta rodando na porta %DB_PORT%
:: ------------------------------------------------------------------
echo [INFO] Verificando se o PostgreSQL esta disponível na porta %DB_PORT%...
netstat -ano | findstr ":%DB_PORT%" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [AVISO] PostgreSQL nao esta respondendo na porta %DB_PORT%.
    echo [INFO] Tentando iniciar o servico do PostgreSQL...

    :: Tenta iniciar servicos conhecidos do PostgreSQL no Windows
    net start postgresql >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        net start postgres >nul 2>&1
    )
    if !ERRORLEVEL! neq 0 (
        net start postgresql-x64-16 >nul 2>&1
    )
    if !ERRORLEVEL! neq 0 (
        net start postgresql-x64-15 >nul 2>&1
    )
    if !ERRORLEVEL! neq 0 (
        net start postgresql-x64-14 >nul 2>&1
    )

    :: Aguarda o PostgreSQL ficar disponível (max ~60 segundos)
    set /a tentativas=0
    :aguardar_postgres
    netstat -ano | findstr ":%DB_PORT%" >nul 2>&1
    if !ERRORLEVEL! == 0 (
        echo [INFO] PostgreSQL esta online.
    ) else (
        set /a tentativas+=1
        if !tentativas! geq 60 (
            echo.
            echo [ERRO] O PostgreSQL nao iniciou apos aguardar.
            echo       Inicie o servico manualmente e tente novamente.
            echo.
            pause
            exit /b 1
        )
        timeout /t 1 >nul
        goto aguardar_postgres
    )
) else (
    echo [INFO] PostgreSQL ja esta online na porta %DB_PORT%.
)

echo.

:: Verificar se ja existe instancia online na porta
netstat -ano | findstr ":%PORT%" >nul 2>&1
if !ERRORLEVEL! == 0 (
    echo.
    echo [AVISO] Ja existe uma instancia online na porta %PORT%.
    echo       Nenhuma nova instancia sera iniciada.
    echo       Se o servidor nao estiver respondendo, encerre o
    echo       processo que esta usando a porta e tente novamente.
    echo.
    pause
    exit /b 1
)

:: Verificar se o Python esta disponível
where python >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo.
    echo [ERRO] Python nao encontrado no PATH do sistema.
    echo       Instale o Python ou adicione-o ao PATH e tente novamente.
    echo.
    pause
    exit /b 1
)

:: Variaveis de ambiente necessarias
set PYTHONPATH=%~dp0src
set TMS_DATABASE_URL=%DB_URL%
:: Coletor continuo sempre ligado (60 segundos). Use 0 para desligar.
set TMS_COLLECT_INTERVAL=60

echo [INFO] Diretorio: %~dp0
echo [INFO] Banco:     %TMS_DATABASE_URL%
echo [INFO] Porta:     %PORT%
echo [INFO] Coletor continuo: ligado (intervalo %TMS_COLLECT_INTERVAL%s)
echo.

:: Aplicar migracoes do banco
echo [INFO] Aplicando migracoes (alembic upgrade head)...
python -m alembic upgrade head
if !ERRORLEVEL! neq 0 (
    echo.
    echo [ERRO] Falha ao aplicar as migracoes do banco de dados.
    echo       Verifique se o PostgreSQL esta rodando e acessivel.
    echo.
    pause
    exit /b 1
)

echo [INFO] Migracoes aplicadas com sucesso.
echo [INFO] Subindo servidor em http://%HOST%:%PORT%
echo [INFO] Pressione Ctrl+C para encerrar.
echo.

:: Subir o servidor
python -m uvicorn %APP% --host %HOST% --port %PORT% --proxy-headers

endlocal
