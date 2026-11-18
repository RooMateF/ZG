# ZG HD-2D 外觀測試

驗證像素角色立在 3D 場景加景深和光暈，看起來方向對不對。目標平台是 PC。計畫和決定在 `docs/HD2D_PLAN.md`。

## 內容

- `main.gd`：整個場景都用程式產生，沒有任何美術檔，所以很陽春。一個房間（地板、牆、沙發、桌、櫃、前景木箱）、暖色檯燈和冷色月光、發光的窗和燈泡、三個用字元畫的像素角色（你、行屍、生存者）。鏡頭有前後景深。
- 操作：方向鍵、WASD 或手把左搖桿上下左右走，家具會擋路。滑鼠點地板會走過去。沒有虛擬搖桿。
- 左上角第一行：幀率、渲染模式、顯示晶片、機型。第二行是中文字測試（用系統字型）。
- PC 用 Forward+ 渲染，多了 SSAO 和體積霧。**這兩個效果還沒有人實際看過**，參數是在沒有顯示卡的機器上盲寫的。

## 在有顯卡的電腦上看

```
C:\tools\hd2d\godot\Godot_v4.7.2-stable_win64.exe --path hd2d -e
```

按 F5 跑。工具還沒裝的話先跑 `setup_tools.ps1`，步驟在 `docs/NEW_MACHINE.md`。

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
