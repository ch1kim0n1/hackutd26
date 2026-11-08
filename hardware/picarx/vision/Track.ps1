param([ValidateSet("rack-01","rack-02")][string]$Cabinet="rack-02",
      [ValidateRange(1,20)][int]$Steps=1)
$ErrorActionPreference="Stop"
$key=$env:NVIDIA_API_KEY
if (!$key) {
    $secret=Read-Host "NVIDIA API key (hidden)" -AsSecureString
    $key=[Net.NetworkCredential]::new('', $secret).Password
}
$marker=if ($Cabinet -eq "rack-02") {"blue painter's tape"} else {"red metal plate"}
$prompt="This image has nine numbered cells. Locate the $marker used as a cabinet marker. Return exactly the single cell number (1-9) containing the center of that marker. If no marker is visible, return none. If multiple plausible markers or uncertain, return ambiguous. Do not assume the marker is present."
try {
    for ($i=0; $i -lt $Steps; $i++) {
        $frame=Invoke-RestMethod http://127.0.0.1:18112/frame -TimeoutSec 5
        [IO.File]::WriteAllBytes((Join-Path (Get-Location).Path 'last-grid.jpg'),[Convert]::FromBase64String($frame.jpeg))
        $body=@{
            model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
            temperature=0; max_tokens=64; chat_template_kwargs=@{enable_thinking=$false}
            messages=@(@{role="user";content=@(@{type="text";text=$prompt},
                @{type="image_url";image_url=@{url="data:image/jpeg;base64,$($frame.jpeg)"}})})
        } | ConvertTo-Json -Depth 10
        $reply=Invoke-RestMethod -Uri 'https://integrate.api.nvidia.com/v1/chat/completions' -Method Post -ContentType 'application/json' -Headers @{Authorization="Bearer $key"} -Body $body -TimeoutSec 20
        $cell=([string]$reply.choices[0].message.content).Trim().ToLowerInvariant()
        if ($cell -notmatch '^(?:[1-9]|none|ambiguous)$') {throw "Unexpected model output: $cell"}
        $cmd=@{id=$frame.id;cell=$cell} | ConvertTo-Json
        Invoke-RestMethod http://127.0.0.1:18112/observation -Method Post -Body $cmd -ContentType 'application/json' -TimeoutSec 3
        if ($cell -in @("none","ambiguous","5")) {break}
        Start-Sleep -Milliseconds 750
    }
} finally {Remove-Variable key,secret -ErrorAction SilentlyContinue}
