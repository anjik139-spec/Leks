$ErrorActionPreference = "SilentlyContinue"

$src = "C:\bots\voicebot-src"
$urlFile = "C:\bots\lex-tunnel.url"
$log = "C:\bots\lex-tunnel-watch.log"
$err = "C:\bots\lex-tunnel-watch.err"

function Get-PublicCode($url) {
    if (-not $url) { return "000" }
    return (& curl.exe --compressed -sS -m 10 -o NUL -w "%{http_code}" "$url/" 2>$null)
}

$current = (Get-Content $urlFile -Raw -ErrorAction SilentlyContinue).Trim()
if ($current -and (Get-PublicCode $current) -eq "200") {
    exit 0
}

Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
    Where-Object { $_.CommandLine -like "*localhost.run*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Remove-Item $log, $err -Force
Start-Process -FilePath "C:\WINDOWS\System32\OpenSSH\ssh.exe" `
    -ArgumentList "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=15", `
    "-o", "ServerAliveCountMax=3", "-R", "80:127.0.0.1:8090", "nokey@localhost.run" `
    -RedirectStandardOutput $log -RedirectStandardError $err -WindowStyle Hidden

$url = ""
for ($i = 0; $i -lt 25; $i++) {
    Start-Sleep -Seconds 1
    $match = Select-String -Path $log, $err -Pattern "https://[a-z0-9]+\.app\.lhr\.life" -Encoding UTF8 |
        Select-Object -Last 1
    if ($match) {
        $url = $match.Line -replace ".*(https://[a-z0-9]+\.app\.lhr\.life).*", '$1'
        break
    }
}

if (-not $url) { exit 1 }

Set-Content -Path $urlFile -Value $url -Encoding UTF8
$envText = Get-Content "C:\bots\voicebot\.env" -Encoding UTF8
$envText = $envText -replace "^WEBAPP_URL=.*$", "WEBAPP_URL=$url"
$envText | Set-Content "C:\bots\voicebot\.env" -Encoding UTF8

docker compose -f "C:\bots\voicebot-src\docker-compose.yml" up -d --force-recreate bot 2>&1 | Out-Null

Add-Content -Path "C:\bots\lex-tunnel-watch-events.log" -Value "$(Get-Date -Format o) restarted $url"
