# ALITA: create semantic embeddings for the 43 summaries (OpenRouter). Started by RUN_ME.bat.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$model = 'openai/text-embedding-3-large'
Write-Host ''
Write-Host 'ALITA - semantic embeddings' -ForegroundColor Cyan
Write-Host 'Paste your OpenRouter API key (starts with sk-or-) and press Enter.'
Write-Host '(Right-click pastes. The key stays invisible, is only sent to openrouter.ai and is not saved.)'
$sec = Read-Host -AsSecureString 'Key'
$key = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)).Trim()
if (-not $key) { Write-Host 'No key entered.' -ForegroundColor Red; exit 1 }
$src = Get-Content -Raw -Encoding UTF8 (Join-Path $here 'alita_summaries.json') | ConvertFrom-Json
$items = @($src.items)
$out = New-Object System.Collections.ArrayList
for ($i = 0; $i -lt $items.Count; $i += 16) {
  $batch = $items[$i..([Math]::Min($i + 15, $items.Count - 1))]
  $body = @{ model = $model; input = @($batch | ForEach-Object { $_.text }) } | ConvertTo-Json -Depth 4
  Write-Host ("Embedding {0}-{1} of {2} ..." -f ($i + 1), ($i + $batch.Count), $items.Count)
  $res = Invoke-RestMethod -Method Post -Uri 'https://openrouter.ai/api/v1/embeddings' `
    -Headers @{ Authorization = "Bearer $key" } -ContentType 'application/json; charset=utf-8' `
    -Body ([Text.Encoding]::UTF8.GetBytes($body))
  $data = @($res.data | Sort-Object index)
  for ($j = 0; $j -lt $batch.Count; $j++) { [void]$out.Add(@{ id = $batch[$j].id; vector = $data[$j].embedding }) }
}
$result = @{ model = $model; dim = @($out[0].vector).Count; items = $out }
$file = Join-Path $here 'alita_embeddings.json'
[IO.File]::WriteAllText($file, ($result | ConvertTo-Json -Depth 5 -Compress), (New-Object Text.UTF8Encoding($false)))
Write-Host ''
Write-Host ("Done: {0} embeddings saved to {1}" -f $out.Count, $file) -ForegroundColor Green
Write-Host 'Now go back to the chat and write: done'
