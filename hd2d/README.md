# ZG HD-2D 外觀測試

驗證像素角色立在 3D 場景加景深和光暈，看起來方向對不對。目標平台是 PC。計畫和決定在 `docs/HD2D_PLAN.md`。

## 內容

- `main.gd`：整個場景由程式組起來，圖用美術總監交的。一個房間（地板、牆、沙發、茶几、電視櫃、紙箱、檯燈）、暖色檯燈和冷色月光、發光的窗。三位主角（許晏、沈以美、符婕）和三種敵人（腫脹者、行屍、疾走者）的像素小人。鏡頭有前後景深。還沒有任何玩法。
- `house.gd`：房子模式，啟動時在最後加 `-- --house`。住宅區第一棟房子的骨架：巷子、三層樓八間房、門、樓梯。家具大多是素色方塊佔位，還沒接規則。說明在 `docs/ENG_STATUS.md` 第五節。
- `kit.gd`：`main.gd` 和 `house.gd` 共用的工具（貼圖、方塊家具、小人、截圖）。
- `art/`：`inbox/` 是美術總監交的原檔（歸她管，不要改）；`sprites/`、`furniture/`、`tiles/`、`full/`、`portraits/` 是匯入後遊戲實際用的圖。
- 操作：方向鍵、WASD 或手把左搖桿上下左右走，家具會擋路。滑鼠點地板會走過去。按 P 開人物面板，左右鍵換人。沒有虛擬搖桿。
- 左上角第一行：幀率、渲染模式、顯示晶片、機型。第二行是中文字測試（用系統字型）。
- PC 用 Forward+ 渲染，多了 SSAO 和體積霧。**這兩個效果還沒有人實際看過**，參數是在沒有顯示卡的機器上盲寫的。

## 在有顯卡的電腦上看

```
C:\tools\hd2d\godot\Godot_v4.7.2-stable_win64.exe --path hd2d -e
```

按 F5 跑。工具還沒裝的話先跑 `setup_tools.ps1`，步驟在 `docs/NEW_MACHINE.md`。

## 沒有顯示卡也能看畫面：截圖

```
powershell -ExecutionPolicy Bypass -File hd2d\shot.ps1
```

產出 `hd2d\build\shot.png`。它借用 Chrome 或 Edge 自帶的 SwiftShader（用 CPU 模擬顯示卡的 Vulkan 驅動），讓 Godot 用完整的 Forward+ 渲染算出畫面，跑二十幀後存檔結束。大約每秒 1 幀，一張圖要半分鐘到一分鐘，只能看不能玩。不用下載任何東西，但機器上要有 Chrome 或 Edge。

參數：`-Out 路徑`（要寫完整路徑，相對路徑會存不了）、`-Size 1280x720`、`-Frames 30`。在有顯示卡的電腦上加 `-Gpu` 就用真的顯示卡。加 `-Lineup` 會把所有匯入的角色排成兩排，用來比身高、檢查新交的圖。

遊戲本身也接受啟動參數 `-- --shot=路徑.png --shot-frames=20`，截圖腳本就是用它。

注意：軟體繪圖的結果和真顯示卡應該一致，但沒有實際比對過。

## 檢查腳本有沒有錯（不需要顯示卡）

```
C:\tools\hd2d\godot\Godot_v4.7.2-stable_win64_console.exe --headless --path hd2d --quit-after 30
```

沒有任何錯誤訊息就是通過。

## Android（移植入口，平常用不到）

手機版已放棄，但匯出設定保留著，隨時可以建一個安裝檔：

```
build_apk.bat
```

產出 `build/zg_hd2d_test.apk`（約 28MB，arm64，Android 7 以上，需要支援 Vulkan）。手機平台會自動改用 Mobile 渲染模式。用的是測試簽章，只能自己裝，不能上架。需要先用 `setup_tools.ps1 -WithAndroid -AcceptAndroidLicense` 裝好 Android 建置鏈。

## 工具位置（預設 C:\tools\hd2d，可用環境變數 HD2D_TOOLS 改）

| 路徑 | 內容 | 何時需要 |
|---|---|---|
| `godot\` | Godot 4.7.2 編輯器（自帶設定模式，設定在 `godot\editor_data`） | 一定要 |
| `godot\editor_data\export_templates\4.7.2.stable\` | 只放了 `android_debug.apk` 這一個匯出範本 | Android |
| `jdk-17.0.21+9\` | Temurin JDK 17 | Android |
| `android-sdk\` | platform-tools、build-tools 35.0.1、platforms android-35、cmdline-tools | Android |
| `keys\debug.keystore` | 測試用簽章金鑰（密碼 android，別名 androiddebugkey） | Android |

沒裝的：NDK、CMake（只有自訂 Gradle 建置才需要）、release 範本、Windows 匯出範本。

Android CLI 預設會回傳使用數據給 Google，指令要加 `--no-metrics`。
