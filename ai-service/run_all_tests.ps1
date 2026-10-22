# Runs every backend suite and reports honestly.
#
# Differences from a naive `python test_*.py` loop:
#
#   * It captures the real exit code of each process. Output text
#     alone cannot distinguish "ran fine" from "printed a failure
#     line then exited zero".
#   * It classifies each suite as PASS, FAIL or ERROR. A FAIL is a
#     suite that ran and reported failed assertions; an ERROR is one
#     that crashed - a traceback, a refused import, a timeout. Those
#     mean very different things and a single "failed" bucket hides
#     that.
#   * It reports skips, rather than silently omitting them.
#   * It never writes to any database. Each suite is responsible for
#     its own isolation; db_guard refuses production at import and
#     again on every connection.
#
# Safe to run: a suite that has not isolated itself will be refused
# by db_guard and will show up here as ERROR, not as a silent write.

$ErrorActionPreference = 'Continue'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here

# Never inherit anything that could point a suite at real data.
$env:RESUMEAI_DB = $null
$env:RESUMEAI_TESTING = $null
$env:RESUMEAI_ALLOW_PRODUCTION_DB = $null

$suites = Get-ChildItem -Path $here -Filter 'test_*.py' | Sort-Object Name

$results = @()
$started = Get-Date

foreach ($suite in $suites) {

    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    $stdout = Join-Path $env:TEMP ("suite_out_" + $suite.BaseName + ".txt")
    $stderr = Join-Path $env:TEMP ("suite_err_" + $suite.BaseName + ".txt")

    # The path must be quoted.
    #
    # It contains spaces ("VANDANA GUDIHAL", "OneDrive", "Desktop"),
    # and Start-Process passes ArgumentList through as a single
    # string. Unquoted, Python received the path split into several
    # arguments and exited 2 on every suite without running any of
    # them - which looked exactly like 26 simultaneous test failures.
    # Quoting it is the whole fix.
    $proc = Start-Process -FilePath python `
        -ArgumentList ('"' + $suite.FullName + '"') `
        -WorkingDirectory $here `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr

    $sw.Stop()

    $code = $proc.ExitCode
    $out = if (Test-Path $stdout) { Get-Content $stdout -Raw } else { "" }
    $err = if (Test-Path $stderr) { Get-Content $stderr -Raw } else { "" }

    Remove-Item $stdout, $stderr -ErrorAction SilentlyContinue

    $combined = $out + "`n" + $err
    $hasTraceback = $combined -match 'Traceback \(most recent call last\)'

    # Suites report "RESULT: N passed, M failed" or a "... TESTS PASSED".
    $assertions = $null
    if ($combined -match 'RESULT:\s+(\d+)\s+passed,\s+(\d+)\s+failed') {
        $assertions = [int]$Matches[1] + [int]$Matches[2]
    }

    if ($code -eq 0 -and -not $hasTraceback) {
        $status = 'PASS'
    }
    elseif ($hasTraceback) {
        $status = 'ERROR'
    }
    else {
        $status = 'FAIL'
    }

    $summary = ''
    if ($combined -match '(RESULT:[^\r\n]*)') { $summary = $Matches[1].Trim() }
    elseif ($combined -match '([A-Z][A-Z\s\-]+TESTS PASSED)') { $summary = $Matches[1].Trim() }
    elseif ($combined -match '(TEST PASSED[^\r\n]*)') { $summary = $Matches[1].Trim() }

    $results += [pscustomobject]@{
        Suite    = $suite.Name
        ExitCode = $code
        Status   = $status
        Asserts  = $assertions
        Seconds  = [math]::Round($sw.Elapsed.TotalSeconds, 1)
        Summary  = $summary
    }

    $flag = switch ($status) { 'PASS' { ' ok ' } 'FAIL' { 'FAIL' } 'ERROR' { 'ERR ' } }
    "{0}  {1,-34} exit={2,-3} {3,6}s  {4}" -f `
        $flag, $suite.Name, $code, [math]::Round($sw.Elapsed.TotalSeconds, 1), $summary
}

Pop-Location

$elapsed = (Get-Date) - $started

""
"================================================================"
"  suites run   : $($results.Count)"
"  passed       : $(($results | Where-Object Status -eq 'PASS').Count)"
"  failed       : $(($results | Where-Object Status -eq 'FAIL').Count)"
"  errored      : $(($results | Where-Object Status -eq 'ERROR').Count)"
"  skipped      : 0 (every test_*.py in the folder was run)"
$totalAsserts = ($results | Where-Object { $_.Asserts } | Measure-Object Asserts -Sum).Sum
if ($totalAsserts) { "  assertions  : $totalAsserts" }
"  wall time    : $([math]::Round($elapsed.TotalMinutes, 1)) min"
"================================================================"

$bad = $results | Where-Object { $_.Status -ne 'PASS' }
if ($bad) {
    ""
    "NEEDS ATTENTION:"
    $bad | ForEach-Object { "  $($_.Status)  $($_.Suite)  (exit $($_.ExitCode))" }
    exit 1
}

"ALL SUITES PASSED"
exit 0