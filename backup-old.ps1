$ErrorActionPreference = "Stop"

$src = "C:\bots\voicebot\data"
$dst = "C:\bots\backups\voicebot"
$log = "C:\bots\backups\voicebot-backup.log"
$python = "C:\bots\voicebot\.venv\Scripts\python.exe"
New-Item -ItemType Directory -Force -Path $dst | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stage = Join-Path $env:TEMP "voicebot_db_backup_$stamp"
$zip = Join-Path $dst "voicebot_db_$stamp.zip"
New-Item -ItemType Directory -Force -Path $stage | Out-Null

$env:VOICEBOT_SRC = $src
$env:VOICEBOT_STAGE = $stage
@'
import glob
import json
import os
import sqlite3

src = os.environ["VOICEBOT_SRC"]
stage = os.environ["VOICEBOT_STAGE"]
for path in glob.glob(os.path.join(src, "*.db")):
    name = os.path.basename(path)
    source = sqlite3.connect(path)
    target = sqlite3.connect(os.path.join(stage, name))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
for path in glob.glob(os.path.join(src, "*.json")):
    with open(path, "rb") as f:
        data = f.read()
    with open(os.path.join(stage, os.path.basename(path)), "wb") as f:
        f.write(data)
print("DB_BACKUP_FILES", len(os.listdir(stage)))
'@ | & $python -

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
try {
    $hasDb = $archive.Entries | Where-Object { $_.FullName -eq "bot.db" }
    if (-not $hasDb) { throw "bot.db отсутствует в архиве" }
} finally {
    $archive.Dispose()
}

Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue

Get-ChildItem $dst -Filter "voicebot_*.zip" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force

Add-Content $log "$(Get-Date -Format o) OK $zip $((Get-Item $zip).Length) bytes"
