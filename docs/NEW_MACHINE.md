# 換到另一台電腦

照順序做，大約二十分鐘（大部分是下載）。需要：Windows、Git、Python 3.12 以上。

## 1. 拿到專案

倉庫是私人的，第一次 clone 時 Git 會跳出 GitHub 登入視窗，用 RooMateF 登入。

```
git clone https://github.com/RooMateF/ZG.git
```

**接著設定提交的作者身分。** 這個設定存在每台電腦的倉庫裡，不會跟著 clone 過來。不設的話，提交會用這台電腦的全域設定，可能把私人信箱寫進提交紀錄。在專案資料夾裡：

```
git config user.name RooMateF
```

```
git config user.email 106058573+RooMateF@users.noreply.github.com
```

## 2. 不在倉庫裡、要手動帶的東西

| 東西 | 在舊電腦的哪裡 | 要不要帶 |
|---|---|---|
| 文字版存檔 `save.json`、`meta.json` | 專案根目錄 | 想接著玩才要。複製到新電腦的專案根目錄 |
| Godot 和其他工具 | `C:\tools\hd2d` | 不用帶，第 4 步會重新下載 |
| Godot 的匯入快取 `hd2d\.godot` | 專案裡 | 不用帶，第一次開專案會自動重建 |
| 截圖和安裝檔 `hd2d\build` | 專案裡 | 不用帶，都可以重新產生 |
| Claude 的對話紀錄和記憶 | 使用者資料夾 | 帶不走。規則已經寫進專案根目錄的 `CLAUDE.md` |

## 3. 文字版

文字版本身沒有相依套件。在專案根目錄：

```
python play.py
```

```
python -X utf8 tests/test_endings.py
```

測試應該全部通過。

美術匯入工具（`hd2d/tools/` 裡的 Python 腳本）需要兩個套件：

```
python -m pip install pillow numpy
```

## 4. HD-2D 工具

只需要 Godot 編輯器（約 300MB）。在 PowerShell 裡、專案根目錄執行：

```
powershell -ExecutionPolicy Bypass -File hd2d\setup_tools.ps1
```

它會把 Godot 4.7.2 裝到 `C:\tools\hd2d\godot`（自帶設定模式，不動系統），並把使用者環境變數 `HD2D_TOOLS` 設成 `C:\tools\hd2d`。想裝在別的位置就加 `-Root D:\somewhere`。

## 5. 開編輯器看畫面（需要顯示卡）

```
C:\tools\hd2d\godot\Godot_v4.7.2-stable_win64.exe --path hd2d -e
```

第一次開會花一點時間匯入圖檔。按 F5 直接跑。

操作：方向鍵、WASD 或手把移動，滑鼠點地板走過去，按 P 開人物面板（左右鍵換人）。

要匯出 PC 版的執行檔，從編輯器選單的「編輯器」裡找「管理匯出範本」，下載完整範本。

## 6. 第一次在有顯示卡的電腦上，請看這幾件事

舊電腦沒有顯示卡，下面這些從來沒有人看過。看完請告訴 Claude 結果。

| 看什麼 | 為什麼 |
|---|---|
| 流暢度（左上角的 FPS） | 舊電腦是每秒一幀的軟體算圖，完全沒有真實數據 |
| 走路的動作 | 是程式做的暫代動作（身體下沉、兩腳輪流抬），只看過靜態截圖 |
| 畫面和 `docs/handoff/shots/scene_furniture_2026-11-18.png` 像不像 | 軟體算圖和真顯示卡有沒有差異，沒有比對過 |
| 景深、光暈、環境光遮蔽、體積霧 | 參數是盲調的，很可能要改 |
| 夜晚的氣氛 | 為了看清楚角色把場景調亮了，現在不太像晚上 |
| 小人的樣子（56 像素高、三頭身） | 這是不是你要的風格 |
| 房間的比例 | 房間偏大偏空，家具之後會放大到 1.35 倍 |

這一關是計畫裡的「階段 1 外觀驗證」。方向不對就在這裡停下來調，不要往下量產內容。

用真顯示卡截圖，可以和舊電腦的軟體算圖直接比對：

```
powershell -ExecutionPolicy Bypass -File hd2d\shot.ps1 -Gpu -Out hd2d\build\gpu.png -Size 1280x720
```

## 7. 讓新的 Claude 對話接手

對話紀錄不會跟著專案走。在新電腦的專案資料夾開 Claude Code，它會自動讀專案根目錄的 `CLAUDE.md`，裡面有工作規則、先讀哪些文件、常用指令。

開頭可以直接跟它說：「讀 `CLAUDE.md` 列的文件，告訴我現在做到哪裡。」

目前的進度和下一步在 `docs/HD2D_PLAN.md` 的「現況」和「下一步」。

## 8. Android 建置鏈（選用，移植入口）

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
