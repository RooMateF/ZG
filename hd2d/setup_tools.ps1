# Sets up the HD-2D tools on a new Windows machine.
# Keep this file ASCII-only: Windows PowerShell 5.1 misreads UTF-8 without a BOM.
#
# PC only (default, about 300 MB: just the Godot editor):
#   powershell -ExecutionPolicy Bypass -File hd2d\setup_tools.ps1
#
# With the Android build chain (about 1 GB; kept as a porting option, needs python on PATH):
#   powershell -ExecutionPolicy Bypass -File hd2d\setup_tools.ps1 -WithAndroid -AcceptAndroidLicense
#
# -WithAndroid           Also install JDK 17, the Android SDK, the Android export template and a debug keystore
# -AcceptAndroidLicense  You agree to the Android SDK terms: https://developer.android.com/studio/terms
# -Root <dir>            Where to install (default C:\tools\hd2d)
# -NoEnv                 Do not set the HD2D_TOOLS user environment variable
param(
    [string]$Root = "C:\tools\hd2d",
    [switch]$WithAndroid,
    [switch]$AcceptAndroidLicense,
    [switch]$NoEnv
)
$ErrorActionPreference = "Stop"

$GodotVer   = "4.7.2-stable"
$GodotTpl   = "4.7.2.stable"
$GodotZip   = "https://github.com/godotengine/godot/releases/download/$GodotVer/Godot_v${GodotVer}_win64.exe.zip"
$GodotTpz   = "https://github.com/godotengine/godot/releases/download/$GodotVer/Godot_v${GodotVer}_export_templates.tpz"
$JdkUrl     = "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse"
$CmdUrl     = "https://dl.google.com/android/repository/commandlinetools-win-16111833_latest.zip"
$CmdSha1    = "57d04f2d75eb8e8fffc5000a987e5de4b5a63e9d"
$SdkPkgs    = @("platform-tools", "build-tools;35.0.1", "platforms;android-35")

if ($WithAndroid -and -not $AcceptAndroidLicense) {
    Write-Host "-WithAndroid installs the Android SDK, which requires accepting Google's terms:"
    Write-Host "  https://developer.android.com/studio/terms"
    Write-Host "Re-run with -AcceptAndroidLicense if you agree."
    exit 2
}

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dl   = Join-Path $Root "dl"
New-Item -ItemType Directory -Force $Root, $Dl | Out-Null

function Get-File([string]$Url, [string]$Out) {
    if (Test-Path $Out) { Write-Host "  have $Out"; return }
    Write-Host "  downloading $Url"
    & curl.exe -sSL --fail -o "$Out.part" $Url
    if ($LASTEXITCODE -ne 0) { throw "download failed: $Url" }
    Move-Item -Force "$Out.part" $Out
}

function Expand-Zip([string]$Zip, [string]$Dest) {
    New-Item -ItemType Directory -Force $Dest | Out-Null
    & tar.exe -xf $Zip -C $Dest
    if ($LASTEXITCODE -ne 0) { Expand-Archive -Force -Path $Zip -DestinationPath $Dest }
}

# ---- 1. Godot editor (self-contained: settings live next to the exe)
$GodotDir = Join-Path $Root "godot"
$GodotExe = Join-Path $GodotDir "Godot_v${GodotVer}_win64_console.exe"
Write-Host "[1/6] Godot $GodotVer"
if (-not (Test-Path $GodotExe)) {
    Get-File $GodotZip (Join-Path $Dl "godot.zip")
    Expand-Zip (Join-Path $Dl "godot.zip") $GodotDir
}
New-Item -ItemType File -Force (Join-Path $GodotDir "._sc_") | Out-Null

if ($WithAndroid) {
# ---- 2. JDK 17
Write-Host "[2/6] JDK 17"
$Jdk = Get-ChildItem $Root -Directory -Filter "jdk-17*" | Select-Object -First 1
if (-not $Jdk) {
    Get-File $JdkUrl (Join-Path $Dl "jdk17.zip")
    Expand-Zip (Join-Path $Dl "jdk17.zip") $Root
    $Jdk = Get-ChildItem $Root -Directory -Filter "jdk-17*" | Select-Object -First 1
}
if (-not $Jdk) { throw "JDK folder not found after extraction" }
$JavaHome = $Jdk.FullName
$env:JAVA_HOME = $JavaHome
$env:Path = "$JavaHome\bin;$env:Path"

# ---- 3. Android export template (only android_debug.apk, fetched by HTTP range)
Write-Host "[3/6] Android export template"
$TplDir = Join-Path $GodotDir "editor_data\export_templates\$GodotTpl"
if (-not (Test-Path (Join-Path $TplDir "android_debug.apk"))) {
    $py = (Get-Command python -ErrorAction SilentlyContinue)
    if (-not $py) { throw "python not found on PATH (needed to fetch the export template)" }
    & python -X utf8 (Join-Path $Here "tools\remote_unzip.py") $GodotTpz $TplDir "templates/version.txt" "templates/android_debug.apk"
    if ($LASTEXITCODE -ne 0) { throw "export template download failed" }
}

# ---- 4. Android SDK
Write-Host "[4/6] Android SDK"
$Sdk = Join-Path $Root "android-sdk"
$AndroidCli = Join-Path $Sdk "cmdline-tools\latest\bin\android.exe"
if (-not (Test-Path $AndroidCli)) {
    $zip = Join-Path $Dl "cmdline-tools.zip"
    Get-File $CmdUrl $zip
    $sha = (Get-FileHash -Algorithm SHA1 $zip).Hash.ToLower()
    if ($sha -ne $CmdSha1) { throw "cmdline-tools checksum mismatch: $sha" }
    $tmp = Join-Path $Sdk "cmdline-tools"
    Expand-Zip $zip $tmp
    if (Test-Path (Join-Path $tmp "latest")) { Remove-Item -Recurse -Force (Join-Path $tmp "latest") }
    Rename-Item (Join-Path $tmp "cmdline-tools") "latest"
}
if (-not (Test-Path (Join-Path $Sdk "build-tools\35.0.1\apksigner.bat")) -or -not (Test-Path (Join-Path $Sdk "platforms\android-35\android.jar")) -or -not (Test-Path (Join-Path $Sdk "platform-tools"))) {
    $quoted = ($SdkPkgs | ForEach-Object { '"' + $_ + '"' }) -join " "
    cmd /c "`"$AndroidCli`" --no-metrics --sdk=$Sdk sdk install $quoted"
    if ($LASTEXITCODE -ne 0) { throw "Android SDK install failed" }
}

# ---- 5. Debug keystore
Write-Host "[5/6] Debug keystore"
$Keys = Join-Path $Root "keys"
$Ks = Join-Path $Keys "debug.keystore"
New-Item -ItemType Directory -Force $Keys | Out-Null
if (-not (Test-Path $Ks)) {
    & "$JavaHome\bin\keytool.exe" -genkeypair -keystore $Ks -storepass android -alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "keytool failed" }
}

# ---- 6. Godot editor settings (first headless run creates the file, then patch three paths)
Write-Host "[6/6] Godot editor settings"
$Settings = Join-Path $GodotDir "editor_data\editor_settings-4.7.tres"
if (-not (Test-Path $Settings)) {
    cmd /c "`"$GodotExe`" --headless --path `"$Here`" --import >nul 2>&1"
}
if (-not (Test-Path $Settings)) { throw "Godot did not create $Settings" }
function Fwd([string]$p) { return $p.Replace("\", "/") }
$text = [System.IO.File]::ReadAllText($Settings)
$text = [regex]::Replace($text, '(?m)^export/android/debug_keystore = .*$', ('export/android/debug_keystore = "' + (Fwd $Ks) + '"'))
$text = [regex]::Replace($text, '(?m)^export/android/java_sdk_path = .*$', ('export/android/java_sdk_path = "' + (Fwd $JavaHome) + '"'))
$text = [regex]::Replace($text, '(?m)^export/android/android_sdk_path = .*$', ('export/android/android_sdk_path = "' + (Fwd $Sdk) + '"'))
[System.IO.File]::WriteAllText($Settings, $text, (New-Object System.Text.UTF8Encoding($false)))
} else {
    Write-Host "Skipping the Android build chain (re-run with -WithAndroid -AcceptAndroidLicense to add it)"
}

if (-not $NoEnv) {
    [Environment]::SetEnvironmentVariable("HD2D_TOOLS", $Root, "User")
    Write-Host "Set user environment variable HD2D_TOOLS=$Root (open a new terminal to pick it up)"
}
Remove-Item -Recurse -Force $Dl -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done. Tools are in $Root"
Write-Host "  Editor : $GodotDir\Godot_v${GodotVer}_win64.exe --path `"$Here`" -e"
if ($WithAndroid) { Write-Host "  Android: $Here\build_apk.bat" }
