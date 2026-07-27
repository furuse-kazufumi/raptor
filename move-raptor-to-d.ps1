# move-raptor-to-d.ps1
# RAPTOR を C:\dev\projects\raptor へ移動するスクリプト
# Claude Code セッションを完全に閉じてから実行してください

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$src = "C:\Users\puruy\raptor"
$dst = "C:\dev\projects\raptor"

Write-Host "RAPTOR 移動: $src -> $dst"

# コピー
robocopy $src $dst /E /NFL /NDL /NJS /NJH
Write-Host "コピー完了"

# PATH のユーザー設定を更新
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
$oldBin = "$src\bin"
$newBin = "$dst\bin"
if ($currentPath -like "*$oldBin*") {
    $newPath = $currentPath -replace [Regex]::Escape($oldBin), $newBin
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-Host "PATH 更新: $oldBin -> $newBin"
}

# 元ディレクトリを削除
Remove-Item -Path $src -Recurse -Force
Write-Host "元ディレクトリ削除完了"

Write-Host ""
Write-Host "完了しました。次回から ccr は C:\dev\projects\raptor\bin\ccr.ps1 から起動されます。"
Write-Host "新しいターミナルを開いて ccr を実行してください。"
