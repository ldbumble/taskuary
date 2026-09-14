param([Parameter(Mandatory=$true)][string]$Scenes, [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SelectVoice('Microsoft Zira Desktop')
    $speaker.Rate = 0
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $items = Get-Content -LiteralPath $Scenes -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($item in $items) {
        $speaker.SetOutputToWaveFile((Join-Path $OutputDirectory ($item.id + '.wav')))
        $speaker.Speak($item.voice)
        $speaker.SetOutputToNull()
    }
} finally { $speaker.Dispose() }
