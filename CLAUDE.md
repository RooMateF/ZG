# 給 Claude 的工作規則

《末日第十四天》：繁體中文的回合制殭屍求生遊戲。文字版（Python，`zg/`）已完成，正在做成 HD-2D 風格的 PC 版（Godot 4.7.2，`hd2d/`）。

對話紀錄和記憶不會跟著專案換電腦，所以規則寫在這裡。

## 接手時先讀

1. `docs/HD2D_PLAN.md`：改版計畫、現況、架構決定。
2. `docs/GAME_DESIGN_HD2D.md`：HD-2D 版的玩法設計。第一節是使用者的定案，不要推翻。
   `docs/FIRST_BUILD.md`：初版（住宅區第一棟房子）的工作清單，做完一項勾一項。
3. `docs/ART_DIRECTOR.md`：三方分工、美術的硬性要求、檔案交換方式。
4. `docs/handoff/art_to_eng.md` 和 `docs/handoff/eng_to_art.md`：和美術總監之間最新的來往，最新的在最上面。
5. `hd2d/README.md`：測試專案和工具怎麼用。
6. `DESIGN.md`：文字版的完整規則，查數值時再看。

## 誰負責什麼

- **使用者**：所有決定。操作繪圖 AI。
- **ChatGPT（美術總監）**：透過 GitHub 讀寫這個倉庫。`hd2d/art/inbox/`、`docs/ART_TRACKER.md`、`docs/WORLD_BIBLE.md`、`docs/handoff/art_to_eng.md` 歸她寫。
- **Claude**：規則、Godot 程式、匯入美術、引擎內打光、截圖、在 `docs/handoff/eng_to_art.md` 回覆。風格不是 Claude 決定的，有意見寫進交接檔。

## 一定要守的

- **提交和推送只在使用者開口時做。** 提交訊息用繁體中文，結尾照當時對話給的署名行。
- **提交的作者身分**是倉庫內的設定：`RooMateF`、`106058573+RooMateF@users.noreply.github.com`。新電腦 clone 之後要重設（見 `docs/NEW_MACHINE.md`）。使用者的私人信箱不要寫進提交，也不要送到任何外部服務。
- **`save.json`、`meta.json` 是使用者正在玩的存檔**，不刪、不覆蓋。在專案根目錄跑 `play.py` 會動到它。
- **改含有反引號、`>`、`$`、反斜線的文字（Markdown 最常見）時，用編輯工具，或把補丁寫成檔案再執行。** 不要塞進 shell 的字串裡：反引號會被當成命令執行，反斜線會被吃掉。這件事出過事故。
- **平台只有 PC。** 不要提虛擬搖桿或以手機為主的設計。Android 的匯出設定只是保留的移植入口，用到 Android 工具時一律加 `--no-metrics`。
- **場景美術的兩條規則**（`docs/ART_DIRECTOR.md`「已經定案的事」）：只放現代都市裡有的東西；東西大部分是新的。
- **文件的寫法**：繁體中文。設計文件裡每一節標「定案」「預設」「提案」，不要把自己的提案寫成定案。
- **沒驗證的事要寫明沒驗證。** 舊電腦沒有顯示卡，流暢度、走路動作、軟體算圖和真顯示卡的差異都沒有人看過。

## 常用指令

文字版測試（應該全部通過）：

```
python -X utf8 tests/test_endings.py
```

檢查 Godot 腳本有沒有錯（不需要顯示卡，沒有錯誤訊息就是通過）：

```
C:\tools\hd2d\godot\Godot_v4.7.2-stable_win64_console.exe --headless --path hd2d --quit-after 30
```

截圖（有顯示卡加 `-Gpu`；沒有的話用 CPU 算，一張約一分鐘）：

```
powershell -ExecutionPolicy Bypass -File hd2d\shot.ps1 -Out 路徑.png -Size 1280x720
```

## 美術總監交圖之後

1. `git fetch origin`，再 `git merge --ff-only origin/main`。
2. 讀 `docs/handoff/art_to_eng.md` 最上面那一則。
3. 匯入（工具都在 `hd2d/tools/`，每支開頭有用法）：
   - 立繪：`import_portrait.py`
   - 轉身圖：`import_turn.py`，身高照交接檔的表傳 `--cm`
   - 方塊家具：把 `_front`、`_top`、`_side` 三張複製到 `hd2d/art/furniture/`，`main.gd` 的 `_furniture()` 會照貼圖像素數算大小
4. 讓 Godot 認得新圖：跑 `--headless --path hd2d --import`，再跑 `python hd2d/tools/fix_imports.py`，再跑一次 `--import`。不做第二步，像素圖會被壓縮糊掉。
5. 截圖存到 `docs/handoff/shots/`，自己看過。
6. 在 `docs/handoff/eng_to_art.md` 最上面寫回覆，更新 `docs/ART_TRACKER.md` 的狀態。
