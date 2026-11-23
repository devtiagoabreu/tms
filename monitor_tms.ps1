<#
.SYNOPSIS
    Monitora e reinicia automaticamente o servidor TMS se estiver caído.
.DESCRIPTION
    Verifica se a porta 8000 está respondendo. Se não estiver, inicia o start.bat.
    Também verifica se o PostgreSQL está rodando na porta 5432.
    Pode ser executado periodicamente pelo Agendador de Tarefas do Windows.
#>

$LogFile = "D:\dev\tms\monitor_tms.log"
$Port = 8000
$PostgresPort = 5432
$StartBat = "D:\dev\tms\start.bat"
$WorkingDir = "D:\dev\tms"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $Message"
    try { Add-Content -Path $LogFile -Value $line -ErrorAction Stop } catch {}
    Write-Host $line
}

function Test-PortOpen {
    param([int]$Port)
    try {
        $socket = New-Object Net.Sockets.TcpClient
        $connectTask = $socket.ConnectAsync("127.0.0.1", $Port)
        $wait = $connectTask.Wait(2000)
        if ($wait) {
            $socket.Close()
            return $true
        } else {
            $socket.Close()
            return $false
        }
    } catch {
        return $false
    }
}

Write-Log "=== Iniciando verificação do TMS ==="

# 1. Verificar PostgreSQL
if (-not (Test-PortOpen -Port $PostgresPort)) {
    Write-Log "PostgreSQL não está respondendo na porta $PostgresPort. Tentando iniciar serviço..."
    try {
        Start-Service -Name "postgresql" -ErrorAction Stop
        Write-Log "Serviço postgresql iniciado."
    } catch {
        try {
            Start-Service -Name "postgres" -ErrorAction Stop
            Write-Log "Serviço postgres iniciado."
        } catch {
            Write-Log "Não foi possível iniciar o PostgreSQL automaticamente."
        }
    }
    Start-Sleep -Seconds 5
} else {
    Write-Log "PostgreSQL online na porta $PostgresPort."
}

# 2. Verificar servidor TMS
if (-not (Test-PortOpen -Port $Port)) {
    Write-Log "Porta $Port não está respondendo. Iniciando servidor TMS..."
    
    # Matar processos uvicorn antigos se houver
    try {
        Get-Process -Name "python" -ErrorAction Stop | Where-Object { 
            $_.CommandLine -like "*uvicorn*" -or $_.CommandLine -like "*tms.app.main*" 
        } | Stop-Process -Force -ErrorAction SilentlyContinue
        Write-Log "Processos Python/uvicorn antigos encerrados."
        Start-Sleep -Seconds 2
    } catch {
        # Ignorar se não encontrar processos
    }

    # Inicia o servidor TMS
    try {
        $process = Start-Process -FilePath $StartBat -WorkingDirectory $WorkingDir -WindowStyle Hidden -PassThru
        Write-Log "Servidor TMS iniciado (PID: $($process.Id))."
    } catch {
        Write-Log "ERRO ao iniciar o servidor TMS: $($_.Exception.Message)"
    }
} else {
    Write-Log "Servidor TMS está online na porta $Port."
}

Write-Log "=== Verificação concluída ==="
