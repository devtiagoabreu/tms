<#
.SYNOPSIS
    Testa rapidamente se o servidor TMS está online.
.DESCRIPTION
    Verifica se a porta 8000 está respondendo e se o PostgreSQL está na 5432.
#>

$Port = 8000
$PostgresPort = 5432

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

Write-Host "=== Teste de conectividade TMS ===" -ForegroundColor Cyan

if (Test-PortOpen -Port $PostgresPort) {
    Write-Host "✅ PostgreSQL está ONLINE na porta $PostgresPort" -ForegroundColor Green
} else {
    Write-Host "❌ PostgreSQL está OFFLINE na porta $PostgresPort" -ForegroundColor Red
}

if (Test-PortOpen -Port $Port) {
    Write-Host "✅ Servidor TMS está ONLINE na porta $Port" -ForegroundColor Green
    Write-Host "   Acesse: http://localhost:$Port" -ForegroundColor Cyan
    Write-Host "   Documentação: http://localhost:$Port/docs" -ForegroundColor Cyan
} else {
    Write-Host "❌ Servidor TMS está OFFLINE na porta $Port" -ForegroundColor Red
    Write-Host "   Execute: D:\dev\tms\start.bat" -ForegroundColor Yellow
}

Write-Host "=====================================" -ForegroundColor Cyan
