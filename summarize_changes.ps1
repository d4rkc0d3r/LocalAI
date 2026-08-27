param(
    [Parameter(Mandatory = $true)][string]$ServerUrl,
    [Parameter(Mandatory = $true)][string]$Model,
    [Parameter(Mandatory = $true)][string]$Output,
    [Parameter(Mandatory = $true)][string]$Dir
)

$Dir = $Dir.TrimEnd('\')
$Files = @("$Dir\changes.md", "$Dir\README.md", "$Dir\LaunchServer.bat", "$Dir\models.ini")
Write-Host ("Files to include: " + (($Files | ForEach-Object { Split-Path $_ -Leaf }) -join ' | '))

$ErrorActionPreference = 'Stop'

$url   = $ServerUrl.TrimEnd('/')
$question = 'You are helping me review the newly fetched upstream llama.cpp changes. I maintain a personal Windows + CUDA setup; my notes (README.md), server args (LaunchServer.bat) and model list (models.ini) are appended below, together with the raw change list (changes.md). Using my notes, hardware (single RTX 4090 24GB, ~20GB usable VRAM, 32GB RAM) and the models/flags I actually use (CUDA backend, MTP, DFlash, KV cache quant, large context, single parallel slot), write a concise markdown summary of the changes I am likely to be interested in. Group them by relevance. For each commit give the short hash and title and one line on why it matters to my setup. Ignore changes for backends, models or features I do not use (Metal, SYCL, OpenCL, Hexagon, WebGPU, UI, CI).'

$parts = @($question)
foreach ($f in $Files) {
    $name = Split-Path $f -Leaf
    $parts += ''
    $parts += "===== FILE: $name ====="
    $parts += (Get-Content -Raw -LiteralPath $f -Encoding UTF8)
}
$parts += ''
$parts += '===== END OF FILES ====='

$content = $parts -join [Environment]::NewLine
Write-Host ("Prompt size: {0:N1} KB" -f ($content.Length / 1024))

$body = @{
    model        = $Model
    stream       = $false
    max_tokens   = 16384
    messages     = @(
        @{ role = 'user'; content = $content }
    )
} | ConvertTo-Json -Depth 5 -Compress

Write-Host 'Sending request (may take a few minutes)...'
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$resp = Invoke-RestMethod -Method Post -Uri ($url + '/v1/chat/completions') -ContentType 'application/json; charset=utf-8' -Body $bodyBytes
$answer = $resp.choices[0].message.content

$nl = [Environment]::NewLine
$header = ('# llama.cpp Changes Summary' + $nl +
           'Generated: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + $nl +
           'Model: ' + $Model + $nl +
           'Source: changes.md' + $nl +
           '---' + $nl + $nl)
Set-Content -LiteralPath $Output -Value ($header + $answer) -Encoding UTF8

Write-Host ("Done. Tokens: {0} prompt / {1} completion" -f $resp.usage.prompt_tokens, $resp.usage.completion_tokens)
Write-Host "Written to $Output"
