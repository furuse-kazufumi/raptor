# rp — RAPTOR lightweight project picker
#
# Replaces the heavy ccr launcher (claude-auto.mjs). ccr's node-pty machinery
# existed almost entirely to auto-type `/effort ultracode` into the TUI, which
# spawned a long tail of terminal/concatenation bugs. rp drops ALL of that:
#   - no node-pty / no PTY (plain `claude` inherits this console)
#   - no `/effort` injection (type it yourself in the TUI if you ever want it)
#   - no auto-rotate while-loop / no .rotate-signal watch
#
# What rp keeps (ccr-compatible): scan C:\dev\projects\, show a resume-tagged
# menu, write .raptor-session.json (same schema ccr wrote), set
# RAPTOR_CALLER_DIR, then launch plain `claude` from the raptor dir so
# CLAUDE.md / SESSION START runs and restores the chosen project.
#
# Usage:
#   rp                       # interactive menu (default = most recently worked)
#   rp -Project <path>       # skip menu, use this project path
#   rp -NoProject            # launch with no project (汎用)
#   rp -NoLaunch             # write session + print launch command, don't start claude
#   rp -NoRemote             # launch without Remote Control (default: enabled,
#                            #   session named after the project)

[CmdletBinding()]
param(
  [string]$Project,
  [switch]$NoProject,
  [switch]$NoLaunch,
  [int]$Pick = -1,    # non-interactive menu selection (skip Read-Host); -1 = ask
  [switch]$Serve,     # run the work-graph driver loop (autonomous headless workers)
  [switch]$Next,      # print the next runnable work-graph task and exit
  [switch]$Watch,     # -Serve: resident PoC/debug monitoring (never exits on idle)
  [int]$MaxTicks = 0, # -Serve: stop after N ticks (0 = until idle-escalate/auth-halt)
  [switch]$Detach,    # -Serve: run the driver as a detached background process
  [switch]$Web,       # launch the local visual review dashboard (images/video)
  [int]$Port = 8765,  # -Web: port
  [switch]$NoRemote,  # launch WITHOUT Remote Control (default: enabled)
  [switch]$Help       # print usage and exit
)

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$ErrorActionPreference = 'Stop'

$RaptorDir   = Split-Path $PSScriptRoot -Parent
$ProjectsDir = 'C:\dev\projects'
$MetadataCfg = Join-Path $RaptorDir 'claude-projects.json'
$SessionCfg  = Join-Path $RaptorDir '.raptor-session.json'
$WorklogCli  = Join-Path $RaptorDir 'libexec\raptor-worklog'

if ($Help) {
  Write-Host @"
rap — RAPTOR project launcher + work-graph entry point (replaces ccr)

  rap                    プロジェクトをメニューで選び Claude を起動
  rap -Project <path>    指定パスのプロジェクトで起動
  rap -NoProject         プロジェクト指定なしで起動
  rap -Pick <n>          メニューを非対話で選択 (n=0 は指定なし)
  rap -NoLaunch          セッション書込 + 起動コマンド表示のみ (claude 起動しない)
  rap -Next              work-graph の次の runnable タスクを表示
  rap -Serve [-Watch] [-MaxTicks N]   work-graph ドライバを実行 (空なら自動シード)
  rap -Serve -Detach     ドライバを独立プロセスで起動 (対話→自律へ切替; 終了しても継続)
  rap -Web [-Port N]     ローカル視覚レビュー・ダッシュボード (画像/GIF/mp4 をブラウザ表示)
  rap -NoRemote          Remote Control を無効にして起動 (既定は有効)
  rap -Help              このヘルプ

Remote Control は既定で有効。セッション名 = プロジェクトのディレクトリ名
(指定なしは "raptor") なので、複数セッションでもスマホ側で区別できる。

work-graph CLI の詳細ヘルプ:
  py -3.11 $WorklogCli -h          (全コマンドの Usage)
  py -3.11 $WorklogCli <cmd> -h    (各コマンドの引数)
"@
  exit 0
}

# ── work-graph modes (bypass the project picker) ──────────────────────
if ($Serve) {
  # The external driver loop: runs autonomous headless workers (local Ollama /
  # Codex), respawns fresh per-task sessions, escalates idle/stuck, halts at auth.
  $svArgs = @('serve')
  if ($MaxTicks -gt 0) { $svArgs += @('--max-ticks', "$MaxTicks") }
  if ($Watch) { $svArgs += '--watch' }
  if ($Detach) {
    # spawn the driver as an independent process so the interactive session can
    # hand off to autonomous mode and then exit (llterm's "go autonomous" hook).
    $logDir = Join-Path $RaptorDir 'out\worklog'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $out = Join-Path $logDir 'driver.out.log'
    $err = Join-Path $logDir 'driver.err.log'
    $proc = Start-Process -FilePath 'py' -ArgumentList (@('-3.11', $WorklogCli) + $svArgs) `
              -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    Write-Host "  [DETACH] driver 起動 (PID $($proc.Id)) → log: $out" -ForegroundColor Green
    exit 0
  }
  & py -3.11 $WorklogCli @svArgs
  exit $LASTEXITCODE
}
if ($Next) {
  & py -3.11 $WorklogCli next
  exit $LASTEXITCODE
}
if ($Web) {
  $wArgs = @('web'); if ($Port -ne 8765) { $wArgs += @('--port', "$Port") }
  & py -3.11 $WorklogCli @wArgs
  exit $LASTEXITCODE
}

function Resolve-ClaudeExe {
  # RP_CLAUDE_EXE overrides the resolved binary (for launch verification / testing).
  if ($env:RP_CLAUDE_EXE) { return $env:RP_CLAUDE_EXE }
  $cand = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
  if (Test-Path -LiteralPath $cand) { return $cand }
  return 'claude'
}

function Get-RelTime($t) {
  if (-not $t) { return '' }
  $sec = [int]((Get-Date) - $t).TotalSeconds
  if ($sec -lt 60) { return ("{0}秒前" -f $sec) }
  $min = [int]($sec / 60)
  if ($min -lt 60) { return ("{0}分前" -f $min) }
  $hr = [int]($min / 60)
  if ($hr -lt 24) { return ("{0}時間前" -f $hr) }
  return ("{0}日前" -f [int]($hr / 24))
}

# Optional metadata overrides: { "<dirname|lowercase>": { name, description }, ... }
$meta = $null
if (Test-Path -LiteralPath $MetadataCfg) {
  try { $meta = Get-Content -Raw -Encoding UTF8 -LiteralPath $MetadataCfg | ConvertFrom-Json } catch { $meta = $null }
}
function Get-Meta([string]$dir) {
  if ($null -eq $meta) { return $null }
  $names = $meta.PSObject.Properties.Name
  foreach ($k in @($dir, $dir.ToLower())) {
    if ($names -contains $k) { return $meta.$k }
  }
  return $null
}

function Get-Projects {
  if (-not (Test-Path -LiteralPath $ProjectsDir)) {
    Write-Host "[ERROR] プロジェクトディレクトリが見つかりません: $ProjectsDir" -ForegroundColor Red
    return @()
  }
  $dirs = Get-ChildItem -LiteralPath $ProjectsDir -Directory -ErrorAction SilentlyContinue
  $list = foreach ($d in $dirs) {
    $m = Get-Meta $d.Name
    $summary = Join-Path $d.FullName 'docs\SESSION_SUMMARY.md'
    $mtime = $null
    if (Test-Path -LiteralPath $summary) { $mtime = (Get-Item -LiteralPath $summary).LastWriteTime }
    [pscustomobject]@{
      Name        = if ($m -and $m.name) { $m.name } else { $d.Name }
      Path        = $d.FullName
      Description = if ($m -and $m.description) { [string]$m.description } else { '' }
      Mtime       = $mtime
    }
  }
  ,@($list | Sort-Object Name)
}

function Write-SessionConfig([string]$projectPath, [string]$projectName) {
  $base = if ($projectPath) { $projectPath } else { $RaptorDir }
  $docs = Join-Path $base 'docs'
  $name = if ($projectName) { $projectName } elseif ($projectPath) { Split-Path $projectPath -Leaf } else { 'default' }
  $cfg = [ordered]@{
    projectName  = $name
    projectPath  = $base
    docsDir      = $docs
    summaryFile  = Join-Path $docs 'SESSION_SUMMARY.md'
    progressFile = Join-Path $docs 'PROGRESS.md'
    debugFile    = Join-Path $docs 'DEBUG_LOG.md'
    testFile     = Join-Path $docs 'TEST_RESULTS.md'
  }
  try {
    $json = ($cfg | ConvertTo-Json)
    # Write UTF-8 WITHOUT BOM (match ccr's Node writeFileSync; avoid BOM in JSON).
    [System.IO.File]::WriteAllText($SessionCfg, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "  [SESSION] .raptor-session.json 書込: $name" -ForegroundColor DarkGray
  } catch {
    Write-Host "  [SESSION] .raptor-session.json 書込失敗: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "            CLAUDE.md SESSION START の自動継続が機能しません。" -ForegroundColor Red
  }
}

# ── Resolve chosen project path ───────────────────────────────
$chosenPath = $null
$chosenName = $null

if ($NoProject) {
  $chosenPath = $null
} elseif ($Project) {
  if (-not (Test-Path -LiteralPath $Project)) {
    Write-Host "[ERROR] 指定パスが存在しません: $Project" -ForegroundColor Red
    exit 1
  }
  $chosenPath = (Resolve-Path -LiteralPath $Project).Path
  $m = Get-Meta (Split-Path $chosenPath -Leaf)
  if ($m -and $m.name) { $chosenName = $m.name }
} else {
  $projects = Get-Projects
  if ($projects.Count -eq 0) {
    Write-Host "  ($ProjectsDir にプロジェクトが見つかりません)" -ForegroundColor DarkGray
  }

  # default = most recently worked (max SESSION_SUMMARY mtime)
  $defaultNum = 0
  $maxMtime = $null
  for ($i = 0; $i -lt $projects.Count; $i++) {
    $mt = $projects[$i].Mtime
    if ($mt -and (($null -eq $maxMtime) -or ($mt -gt $maxMtime))) {
      $maxMtime = $mt; $defaultNum = $i + 1
    }
  }

  Write-Host ''
  Write-Host '╔══ RAPTOR プロジェクト選択 ══╗' -ForegroundColor Cyan
  for ($i = 0; $i -lt $projects.Count; $i++) {
    $p = $projects[$i]
    $num = $i + 1
    $marker = if ($num -eq $defaultNum) { '▶' } else { ' ' }
    $rel = Get-RelTime $p.Mtime
    $resume = if ($p.Mtime) { " [resume $rel]" } else { '' }
    $desc = if ($p.Description) {
      $d = $p.Description
      if ($d.Length -gt 60) { $d = $d.Substring(0, 60) + '…' }
      " — $d"
    } else { '' }
    $line = ("  {0}{1,2}. {2}{3}{4}" -f $marker, $num, $p.Name, $desc, $resume)
    if ($num -eq $defaultNum) { Write-Host $line -ForegroundColor Green }
    else { Write-Host $line }
  }
  Write-Host '   0. プロジェクト指定なし'
  Write-Host '╚════════════════════════════╝' -ForegroundColor Cyan

  $promptDefault = if ($defaultNum -gt 0) { $defaultNum } else { 0 }
  if ($Pick -ge 0) {
    $num = $Pick
    Write-Host "番号を選択 [$promptDefault]: $num (非対話)" -ForegroundColor DarkGray
  } elseif ([Console]::IsInputRedirected) {
    # non-interactive (piped / no TTY): use the default instead of blocking on Read-Host
    $num = $promptDefault
    Write-Host "番号を選択 [$promptDefault]: (入力なし → 既定)" -ForegroundColor DarkGray
  } else {
    $answer = Read-Host "番号を選択 [$promptDefault]"
    $num = if ([string]::IsNullOrWhiteSpace($answer)) { $promptDefault } else { [int]($answer -replace '[^0-9-]', '') }
  }

  if ($num -ge 1 -and $num -le $projects.Count) {
    $chosenPath = $projects[$num - 1].Path
    $chosenName = $projects[$num - 1].Name
  } else {
    $chosenPath = $null   # 0 or out of range → no project
  }
}

# ── Write session + set env + launch ──────────────────────────
Write-SessionConfig $chosenPath $chosenName

if ($chosenPath) {
  $env:RAPTOR_CALLER_DIR = $chosenPath
  $tag = if ($chosenName) { $chosenName } else { Split-Path $chosenPath -Leaf }
  Write-Host "  → $tag ($chosenPath)" -ForegroundColor Green
} else {
  Remove-Item Env:\RAPTOR_CALLER_DIR -ErrorAction SilentlyContinue
  Write-Host "  → プロジェクト指定なし (汎用)" -ForegroundColor Green
}

$claude = Resolve-ClaudeExe

# Remote Control on by default: long autonomous runs (renders, NAS sweeps) finish
# while nobody is at the terminal, and a session without it can only report to a
# console no one is reading. The session is NAMED after the project so several
# concurrent rap sessions stay distinguishable on the phone. -NoRemote opts out.
$claudeArgs = @('--dangerously-skip-permissions')
if (-not $NoRemote) {
  $rcName = if ($chosenPath) { Split-Path $chosenPath -Leaf } else { 'raptor' }
  # keep the name shell- and URL-safe (the picker allows any dir name)
  $rcName = ($rcName -replace '[^A-Za-z0-9._-]', '-')
  $claudeArgs += @('--remote-control', $rcName)
}

if ($NoLaunch) {
  Write-Host ''
  Write-Host '  次を実行してください:' -ForegroundColor Cyan
  Write-Host "    Set-Location '$RaptorDir'"
  if ($chosenPath) { Write-Host "    `$env:RAPTOR_CALLER_DIR = '$chosenPath'" }
  Write-Host "    & $claude $($claudeArgs -join ' ')"
  exit 0
}

# work-graph guidance: show the next runnable node for a human worker (fast path,
# no ollama probe). Non-fatal — the picker still works without the work-graph.
if (Test-Path -LiteralPath $WorklogCli) {
  try {
    Write-Host ''
    Write-Host '  work-graph → 次の runnable タスク:' -ForegroundColor Cyan
    # scope to the picked project (its claude-projects.json key = dir basename)
    if ($chosenPath) {
      $projKey = Split-Path $chosenPath -Leaf
      & py -3.11 $WorklogCli next --project $projKey --available claude,codex,tool:deterministic 2>$null
    } else {
      & py -3.11 $WorklogCli next --available claude,codex,tool:deterministic 2>$null
    }
  } catch {}
}

if (-not $NoRemote) {
  Write-Host ''
  Write-Host "  Remote Control: 有効 (session: $rcName)" -ForegroundColor Cyan
}

Set-Location -LiteralPath $RaptorDir
& $claude @claudeArgs
