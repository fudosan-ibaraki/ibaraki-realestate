@echo off
REM ============================================================
REM  不動産取引データ 自動取得バッチ
REM  Windowsタスクスケジューラから3ヶ月ごとに実行する
REM ============================================================

cd /d "%~dp0"

REM ── Python実行 ───────────────────────────────────────────
"C:\Users\shun2\AppData\Local\Programs\Python\Python311\python.exe" step1_fetch_and_save.py

REM ── 終了コードをログに記録 ───────────────────────────────
if %ERRORLEVEL% neq 0 (
    echo [ERROR] 実行失敗 (終了コード: %ERRORLEVEL%) >> logs\scheduler.log
) else (
    echo [OK] 正常終了 %DATE% %TIME% >> logs\scheduler.log
)
