param(
    [Parameter(Mandatory)] [string]$TextFile,
    [Parameter(Mandatory)] [string]$OutFile,
    [string]$Voice = "",
    [int]$Rate = 0
)

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    if ($Voice) { $synth.SelectVoice($Voice) }
    $synth.Rate = $Rate
    $fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
    $synth.SetOutputToWaveFile($OutFile, $fmt)
    $synth.Speak((Get-Content -LiteralPath $TextFile -Raw -Encoding UTF8))
}
finally {
    $synth.Dispose()
}
