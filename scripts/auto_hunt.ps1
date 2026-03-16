# auto_hunt.ps1 — Windows Watchdog for Claude Code rate limit auto-recovery
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\auto_hunt.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\auto_hunt.ps1 -Interval 300
#
# Ctrl+C to stop

param(
    [int]$Interval = 600,      # Seconds between retries (default 10 min)
    [int]$MaxRetries = 100
)

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot\..

$huntPrompt = @"
Continue HIGH bug hunting for Current Finance audit.
Target: C:\Users\shieru_k\Desktop\audit-current-main\sui-move-contract
Issue: https://github.com/NyxFoundation/security-agent/issues/138
Template: docs/report_templates/sherlock.md
Branch: hiro/high-bug-hunting

Tasks:
1. Run scraper: python3 scripts/scrape_all_sherlock.py --limit 50
2. Rebuild CSV: python3 scripts/scrape_all_sherlock.py --csv-only
3. Analyze NEW patterns from expanded dataset against Current Finance code
4. If new HIGH found: generate Sherlock template report with PoC inline, update issue #138, commit and push
5. Focus on patterns with >10 Sherlock occurrences not yet checked
6. Commit scraper data

Already found HIGHs: #003 (spot/EMA), #048 (close factor bypass), #062 (bad debt)
Keep going until all 290 contests scraped and all patterns exhausted.
"@

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " AUTO HIGH BUG HUNT - Watchdog Mode" -ForegroundColor Cyan
Write-Host " Interval: ${Interval}s | Max: $MaxRetries" -ForegroundColor Cyan
Write-Host " Ctrl+C to stop" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Cyan

for ($i = 1; $i -le $MaxRetries; $i++) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "`n[$ts] === Attempt $i / $MaxRetries ===" -ForegroundColor Green

    # Step 1: Scrape (no rate limit concern)
    Write-Host "[$ts] Running Sherlock scraper..." -ForegroundColor Yellow
    try {
        python3 scripts/scrape_all_sherlock.py --limit 30 2>&1 | Select-Object -Last 5
        python3 scripts/scrape_all_sherlock.py --csv-only 2>&1 | Select-Object -Last 3
    } catch {
        Write-Host "Scraper error: $_" -ForegroundColor Red
    }

    # Step 2: Commit new data
    $newFiles = git status --short data/sherlock/ 2>$null | Select-String "^\?\?"
    if ($newFiles) {
        Write-Host "[$ts] Committing scraper data..." -ForegroundColor Yellow
        git add data/sherlock/*_highs.json data/sherlock/all_sherlock_highs.csv 2>$null
        git commit -m "data: auto-hunt scraper batch $i`n`nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>" 2>$null
        git push origin hiro/high-bug-hunting 2>$null
    }

    # Step 3: Launch Claude Code
    Write-Host "[$ts] Launching Claude Code..." -ForegroundColor Cyan
    $logFile = "outputs/logs/auto_hunt_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

    try {
        $output = claude --print $huntPrompt 2>&1
        $output | Out-File -FilePath $logFile -Encoding utf8
        $output | Select-Object -Last 10
    } catch {
        Write-Host "Claude error: $_" -ForegroundColor Red
    }

    # Step 4: Check for rate limit
    $isRateLimited = $false
    if (Test-Path $logFile) {
        $logContent = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
        if ($logContent -match "rate.limit|429|too many|overloaded") {
            $isRateLimited = $true
        }
    }

    if ($isRateLimited) {
        Write-Host "[$ts] Rate limit hit. Waiting ${Interval}s..." -ForegroundColor Red
    } else {
        Write-Host "[$ts] Session done. Waiting 60s..." -ForegroundColor Green
        $Interval = 60
    }

    Write-Host "[$ts] Sleeping ${Interval}s... (Ctrl+C to stop)" -ForegroundColor DarkGray
    Start-Sleep -Seconds $Interval
    $Interval = 600  # Reset to default for next rate limit
}

Write-Host "Max retries reached. Done."
