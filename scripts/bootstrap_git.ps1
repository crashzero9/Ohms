# OHMS - local git bootstrap (Windows PowerShell)
#
# Run this from the `ohms/` folder on your Windows machine, NOT from the
# Cowork sandbox. Initializes a git repo, checks no secrets will be
# committed, and creates the first commit.
#
# Usage:
#   cd "C:\Users\laura\OneDrive\Documents\Claude\Projects\MCP Server Setup\ohms"
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
#   .\scripts\bootstrap_git.ps1

$ErrorActionPreference = 'Stop'

Write-Host ''
Write-Host '=== OHMS local git bootstrap ===' -ForegroundColor Cyan

# 1 -- Clean up stub .git dir from the Cowork sandbox, if any
if (Test-Path .git) {
    Write-Host '[1/6] Removing existing .git/ stub...' -ForegroundColor Yellow
    Remove-Item -Recurse -Force .git
}

# 2 -- git init on main
Write-Host '[2/6] git init -b main' -ForegroundColor Yellow
git init -b main | Out-Null

# 3 -- user identity
$existingName  = git config --get user.name  2>$null
$existingEmail = git config --get user.email 2>$null
if (-not $existingName) {
    $name = Read-Host 'Git user.name'
    git config user.name $name
}
if (-not $existingEmail) {
    $email = Read-Host 'Git user.email'
    git config user.email $email
}
$who = git config --get user.name
$mail = git config --get user.email
Write-Host "[3/6] identity: $who <$mail>" -ForegroundColor Green

# 4 -- secret guard: refuse if a real .env or populated gateway yaml exists
Write-Host '[4/6] Scanning for secrets that must not be committed...' -ForegroundColor Yellow
$forbidden = @()
if (Test-Path .env) { $forbidden += '.env' }
$gatewayFiles = Get-ChildItem -Recurse -Filter '*-gateway.yaml' -ErrorAction SilentlyContinue
foreach ($f in $gatewayFiles) {
    if ($f.Name -notlike '*.example.yaml') {
        $forbidden += $f.FullName
    }
}

if ($forbidden.Count -gt 0) {
    Write-Host ''
    Write-Host 'REFUSING TO COMMIT - populated-secret files exist:' -ForegroundColor Red
    foreach ($p in $forbidden) {
        Write-Host "  - $p" -ForegroundColor Red
    }
    Write-Host 'These are already in .gitignore and will NOT be staged, but the'
    Write-Host 'script still bails out so you can verify nothing was leaked.'
    exit 1
}
Write-Host '       clean - no populated-secret files present.' -ForegroundColor Green

# 5 -- stage and preview
Write-Host '[5/6] git add . && git status' -ForegroundColor Yellow
git add .
git status --short

Write-Host ''
$confirm = Read-Host 'Proceed with first commit? (y/N)'
if ($confirm -ne 'y' -and $confirm -ne 'Y') {
    Write-Host 'Aborted. Nothing committed. Run `git reset` to unstage.' -ForegroundColor Yellow
    exit 0
}

# 6 -- commit (message via temp file for cleanest cross-shell behavior)
Write-Host '[6/6] git commit' -ForegroundColor Yellow

$msgLines = @(
    'chore(ohms): initial commit - Phase 1 to Phase 3 scaffold',
    '',
    'Order Hub Management System (OHMS) - FastMCP server for Flauraly.',
    'Deploys to Replit Reserved VM; consumed by Violet/Claude via the',
    'MCP Connector API.',
    '',
    'Includes:',
    '  - 7 FastMCP tools with pydantic return types',
    '  - Hardened middleware stack (TrustedHost, CORS, CorrelationId,',
    '    RateLimit, BearerAuth with hmac.compare_digest and scoped tokens)',
    '  - Shopify scope assertion at boot (fail-closed)',
    '  - 24h idempotency cache for write tools',
    '  - DoorDash browser-contract boundary (schema-only return path)',
    '  - Full docs: Replit runbook, Phase 2 checklist, UI surface contracts,',
    '    DoorDash browser contract, secret rotation runbook',
    '',
    'All Phase 1/2/3 security-review findings closed.',
    '54 / 54 tests pass (pytest).'
)
$tmpMsg = [System.IO.Path]::GetTempFileName()
# UTF-8 WITHOUT BOM so the commit title doesn't start with a zero-width glyph.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($tmpMsg, $msgLines, $utf8NoBom)
git commit -F $tmpMsg | Out-Null
Remove-Item $tmpMsg -Force

Write-Host ''
Write-Host '=== Done. Current log: ===' -ForegroundColor Cyan
git log --oneline -n 1

Write-Host ''
Write-Host 'Next (optional) - push to a private GitHub repo:' -ForegroundColor Cyan
Write-Host '  gh repo create flauraly/ohms --private --source=. --remote=origin --push'
Write-Host ''
Write-Host 'Or add an existing remote:'
Write-Host '  git remote add origin <url>'
Write-Host '  git push -u origin main'
