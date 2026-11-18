# Renders the test scene and saves a screenshot, then quits.
# Works on a machine WITHOUT a graphics card by using SwiftShader, the CPU Vulkan
# driver that ships inside Chrome and Edge. About 1 frame per second: fine for
# looking at the picture, useless for playing.
# Keep this file ASCII-only: Windows PowerShell 5.1 misreads UTF-8 without a BOM.
#
#   powershell -ExecutionPolicy Bypass -File hd2d\shot.ps1
#   powershell -ExecutionPolicy Bypass -File hd2d\shot.ps1 -Out C:\tmp\a.png -Size 1280x720 -Frames 30
#   powershell -ExecutionPolicy Bypass -File hd2d\shot.ps1 -Gpu      (use the real graphics card)
#   powershell -ExecutionPolicy Bypass -File hd2d\shot.ps1 -Lineup   (all characters lined up)
#   powershell -ExecutionPolicy Bypass -File hd2d\shot.ps1 -House -At kitchen   (house mode, player in the kitchen)
param(
    [string]$Out = "",
    [int]$Frames = 20,
    [string]$Size = "960x540",
    [string]$Panel = "",
    [switch]$Lineup,
    [switch]$House,
    [string]$At = "",
    [switch]$Noise,
    [switch]$Wide,
    [switch]$Gpu
)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Out) { $Out = Join-Path $Here "build\shot.png" }
$Root = $env:HD2D_TOOLS
if (-not $Root) { $Root = "C:\tools\hd2d" }
$Godot = Join-Path $Root "godot\Godot_v4.7.2-stable_win64_console.exe"
if (-not (Test-Path $Godot)) { Write-Host "Godot not found at $Godot. Run setup_tools.ps1 first."; exit 1 }

if (-not $Gpu) {
    $pf86 = ${env:ProgramFiles(x86)}
    $cands = @(
        (Join-Path $env:ProgramFiles "Google\Chrome\Application"),
        (Join-Path $pf86 "Microsoft\Edge\Application"),
        (Join-Path $env:ProgramFiles "Microsoft\Edge\Application"),
        (Join-Path $pf86 "Google\Chrome\Application")
    )
    $icd = $null
    foreach ($c in $cands) {
        if (Test-Path $c) {
            $icd = Get-ChildItem $c -Recurse -Filter "vk_swiftshader_icd.json" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($icd) { break }
        }
    }
    if (-not $icd) {
        Write-Host "SwiftShader not found (it ships with Chrome and Edge). On a machine with a graphics card use -Gpu."
        exit 1
    }
    # The Vulkan loader (vulkan-1.dll) also lives in that folder; machines without GPU drivers have none in System32.
    $env:VK_ICD_FILENAMES = $icd.FullName
    $env:VK_DRIVER_FILES = $icd.FullName
    $env:Path = "$($icd.DirectoryName);$env:Path"
    Write-Host "Software rendering via $($icd.DirectoryName)"
}

$outFwd = $Out.Replace("\", "/")
if (Test-Path $Out) { Remove-Item -Force $Out }
$extra = ""
if ($Panel) { $extra = " --panel=$Panel" }     # open the character panel on that character before the shot
if ($Lineup) { $extra += " --lineup" }         # every imported character in two rows, for checking heights
if ($House) { $extra += " --house" }           # house mode (house.gd): the first house, all floors
if ($At) { $extra += " --at=$At" }             # house mode: start in that room, e.g. -At kitchen or -At stairs1:0.5
if ($Noise) { $extra += " --noise" }           # house mode: show the running noise radius
if ($Wide) { $extra += " --wide" }             # house mode: pull the camera back to show the whole floor
$ErrorActionPreference = "Continue"
cmd /c "`"$Godot`" --path `"$Here`" --rendering-driver vulkan --rendering-method forward_plus --resolution $Size -- --shot=$outFwd --shot-frames=$Frames$extra 2>&1" | Select-String -Pattern "^SHOT |Using Device|SCRIPT ERROR|Parse Error|ERROR: .*res://"
if (Test-Path $Out) {
    Write-Host "Saved $Out"
    exit 0
}
Write-Host "No screenshot was produced."
exit 1
