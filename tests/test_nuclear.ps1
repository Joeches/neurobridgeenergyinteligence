# Get token from .env
$envFile = "C:\Users\hp\Desktop\energy-kernel\.env"
$token = (Get-Content $envFile | Select-String "CTO_ACCESS_CODE=") -replace "CTO_ACCESS_CODE=", "" -replace "`"", "" -replace "'", "" -replace "`r", "" -replace "`n", ""

Write-Host "Using Token: $token" -ForegroundColor Cyan

# Test nuclear simulation
$body = @{
    reactor_type = "smr"
    thermal_power_mw = 300.0
    cooling_efficiency = 0.38
    load_demand = 250.0
    ambient_temp = 25.0
    safety_margin = 0.15
    cooling_type = "cooling_tower"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/energy/simulate/nuclear" `
    -Method Post `
    -Headers @{ "Authorization" = "Bearer $token"; "Content-Type" = "application/json" } `
    -Body $body

Write-Host "Success!" -ForegroundColor Green
$response | ConvertTo-Json -Depth 10