# Fills GitHub repository About section (description, topics, homepage).
# Requires: GitHub CLI (gh) logged in as marklabspl
# Run: powershell -ExecutionPolicy Bypass -File scripts\setup-github-about.ps1

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "Install GitHub CLI: https://cli.github.com/"
    Write-Host "Then run: gh auth login"
    exit 1
}

gh repo edit marklabspl/ha-gsm-modem `
    --description "Home Assistant integration for USB GSM modems: SMS, USSD, SMS commands and automations." `
    --homepage "https://marklabs.pl" `
    --add-topic homeassistant `
    --add-topic hacs `
    --add-topic gsm `
    --add-topic sms `
    --add-topic ussd `
    --add-topic home-automation `
    --add-topic gsm-modem

Write-Host "GitHub About section updated."
