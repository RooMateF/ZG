# 換到另一台電腦

## 1. 拿到專案

倉庫是私人的，第一次 clone 時 Git 會跳出 GitHub 登入視窗，用 RooMateF 登入。

```
git clone https://github.com/RooMateF/ZG.git
```

存檔（`save.json`、`meta.json`）不在版控裡。想帶著走就手動複製到專案根目錄。

## 2. 文字版

需要 Python 3.12 以上，沒有其他相依套件。在專案根目錄：

```
python play.py
```

```
python -X utf8 tests/test_endings.py
```

測試應該全部通過。

## 3. HD-2D 工具

只做 PC 的話，只需要 Godot 編輯器（約 300MB）。在 PowerShell 裡、專案根目錄執行：

```
powershell -ExecutionPolicy Bypass -File hd2d\setup_tools.ps1
```

它會把 Godot 4.7.2 裝到 `C:\tools\hd2d\godot`（自帶設定模式，不動系統），並把使用者環境變數 `HD2D_TOOLS` 設成 `C:\tools\hd2d`。想裝在別的位置就加 `-Root D:\somewhere`。

## 4. 開編輯器看畫面（需要顯示卡）

```
C:\tools\hd2d\godot\Godot_v4.7.2-stable_win64.exe --path hd2d -e
```

按 F5 直接跑。操作：方向鍵、WASD 或手把移動，滑鼠點地板走過去。

第一次在有顯卡的電腦上跑，請特別看 SSAO 和體積霧的效果。這些參數是在沒有顯示卡的機器上盲寫的，很可能要調。

要匯出 PC 版的執行檔，從編輯器選單的「編輯器」裡找「管理匯出範本」，下載完整範本。

## 5. Android 建置鏈（選用，移植入口）

手機版已經放棄，平常不需要這一步。將來想建 Android 安裝檔時，再跑：

```
powershell -ExecutionPolicy Bypass -File hd2d\setup_tools.ps1 -WithAndroid -AcceptAndroidLicense
```

會多裝約 700MB：Temurin JDK 17、Android SDK（platform-tools、build-tools 35.0.1、platforms android-35）、Android 匯出範本、測試用簽章金鑰。需要 Python（腳本用它只抓需要的匯出範本）。

`-AcceptAndroidLicense` 代表你同意 Google 的 Android SDK 授權條款（https://developer.android.com/studio/terms ），沒加這個參數腳本不會裝 Android 的部分。腳本呼叫 Android 工具時都加了 `--no-metrics`，不回傳使用數據。

裝好之後建安裝檔：

```
hd2d\build_apk.bat
```

## 6. 讓新的 Claude 對話接手

對話紀錄不會跟著專案走。開新對話時請它先讀：

1. `docs/HD2D_PLAN.md`：改版計畫、決定、進度
2. `DESIGN.md`：文字版規則
3. `hd2d/README.md`：測試專案和工具
