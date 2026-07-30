param(
  [string]$LocalUrl = "http://127.0.0.1:8085"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  throw "cloudflared was not found. Install it first, then open a new PowerShell window."
}

Write-Host "Starting temporary Cloudflare Quick Tunnel for $LocalUrl"
Write-Host "Copy the generated https://*.trycloudflare.com URL."
Write-Host "Use that URL as the API base with /api appended, for example: https://example.trycloudflare.com/api"
cloudflared tunnel --url $LocalUrl
