# Mizan retrieval demo (runs from the local snapshot only: no network, no model).
#
#   cd <backend folder>
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1            # runs everything, no stops
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Pause     # waits for Enter between steps (for presenting)
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Only 3    # runs one step
#
# Needs: the venv (venv\Scripts\python.exe) and data\snapshots\demo-v3 with its items.jsonl (copied or rebuilt; see docs\demo-script.md).

param([switch]$Pause, [int]$Only = 0)

$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"                       # PSX text contains characters the Windows console codepage cannot print
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location (Join-Path $PSScriptRoot "..")
$py = ".\venv\Scripts\python.exe"
$snap = "demo-v3"
$step = 0

function Step($title, $say, [scriptblock]$run) {
    $script:step++
    if ($Only -ne 0 -and $Only -ne $script:step) { return }
    Write-Host ""
    Write-Host ("=" * 100) -ForegroundColor Cyan
    Write-Host ("STEP {0}: {1}" -f $script:step, $title) -ForegroundColor Cyan
    Write-Host ("SAY: " + $say) -ForegroundColor Yellow
    Write-Host ("=" * 100) -ForegroundColor Cyan
    & $run
    if ($Pause) { Read-Host "`n[Enter for the next step]" | Out-Null }
}

if (-not (Test-Path $py)) { Write-Host "venv not found at $py; see docs\demo-script.md" -ForegroundColor Red; exit 1 }
if (-not (Test-Path "data\snapshots\$snap\items.jsonl")) { Write-Host "data\snapshots\$snap\items.jsonl is missing; copy the data folder (see docs\demo-script.md)" -ForegroundColor Red; exit 1 }

Step "Tests" "Everything below is backed by automated tests; no test touches PSX." {
    & $py -m pytest -q
}

Step "An as-of bundle: what the agents would be allowed to know on 8 Sep 2026" `
     "One ticker, one date. Every item has a date, a source, a type and a stable ID. Note the two rules at the top." {
    & $py -m mizan.retrieval.demo --snapshot $snap --ticker OGDC --as-of 2026-09-08 --limit 6
}

Step "Rule 1, no look-ahead: the same ticker a week earlier" `
     "Going from 1 Sep to 8 Sep, the annual results (announced 8 Sep) appear. On 1 Sep they must not exist yet; the list at the bottom shows what was added." {
    & $py -m mizan.retrieval.demo --snapshot $snap --ticker OGDC --as-of 2026-09-08 --compare-as-of 2026-09-01 --limit 4
}

Step "Rule 2, ticker isolation: a different company" `
     "HBL's bundle contains only HBL items. Look at 'tickers in the bundle' and 'items belonging to other tickers were left out'." {
    & $py -m mizan.retrieval.demo --snapshot $snap --ticker HBL --as-of 2026-09-08 --limit 4
}

Step "Failure case: a ticker with no data" `
     "An unknown ticker gives an explained empty bundle, not a crash." {
    & $py -m mizan.retrieval.demo --snapshot $snap --ticker ZZZZ --as-of 2026-09-08
}

Step "Search inside a bundle" `
     "Keyword search with stemming. Ask in plain words; results are ranked, dated and cited by ID." {
    & $py -m mizan.retrieval.demo --snapshot $snap --ticker OGDC --as-of 2026-09-26 --query "oil and gas discovery" --k 3 --limit 0
}

Step "Honest limitation: search that cannot read meaning" `
     "The question means 'dividend' but shares no word with the dividend items. Keyword search matches the word 'shareholders' instead, so the top hits are WRONG (director disclosures, an EGM notice). Embeddings would be the next step; we state this limit in the report." {
    & $py -m mizan.retrieval.demo --snapshot $snap --ticker HBL --as-of 2026-10-12 --query "money paid out to shareholders" --k 3 --limit 0
}

Step "A token budget: what a small model would actually receive" `
     "A full bundle is too big for a small context window, so a budget picks the latest prices, all results, and the items most relevant to the question." {
    & $py -m mizan.retrieval.demo --snapshot $snap --ticker OGDC --as-of 2026-09-26 --query "oil and gas discovery" --budget 3000 --limit 0
}

Step "How big are the bundles?" `
     "Estimated tokens per ticker (not a real tokenizer). This is why the budget step exists." {
    & $py -m mizan.retrieval.sizing --snapshot $snap --as-of 2026-10-12
}

Step "Search quality on hand-labelled questions" `
     "Plain vs stemmed keyword search on two gold sets. Small sets; the first was labelled after reading titles, so it is optimistic." {
    foreach ($gold in "gold_demo-v2", "gold_heldout_demo-v3") {
        foreach ($r in "bm25", "bm25-norm") {
            & $py -m mizan.retrieval.evaluate --snapshot $snap --gold "eval\$gold.json" --retriever $r | Select-Object -First 5
        }
    }
}

Step "Failure case: live fetching is off and nothing is cached" `
     "The fetcher never touches the network unless told to. A window we never fetched gives a clear message, not a silent empty result." {
    & $py -m mizan.fetcher.cli --source announcements --tickers OGDC --from 2025-01-01 --to 2025-01-31
}

Step "Failure case: PSX refuses a request" `
     "We cannot force a real refusal on demand, so these tests simulate one: the token is refreshed once, a second refusal stops the run with a message naming the limits (no CAPTCHA solving, no proxies)." {
    & $py -m pytest tests\test_dps_session.py -v -k "refusal" 2>&1 | Select-String -Pattern "PASSED|FAILED" | ForEach-Object { $_.Line -replace "^tests/test_dps_session.py::", "" }
}

Step "Failure case: a scanned notice" `
     "Some announcements are images. We do not hide that: the item keeps its title and says it needs OCR." {
    & $py -m mizan.retrieval.demo --snapshot $snap --ticker HUBC --as-of 2026-10-12 --query "disclosure of material information" --k 2 --limit 0 | Select-String -Pattern "needs OCR|score" -Context 0,1
}

Step "Failure case: a tampered snapshot" `
     "Snapshots carry a hash in a committed manifest. Change one byte and the demo refuses to use it." {
    $tmp = Join-Path $env:TEMP "mizan-tampered"
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    New-Item -ItemType Directory $tmp | Out-Null
    Copy-Item "data\snapshots\$snap\manifest.json", "data\snapshots\$snap\items.jsonl" $tmp
    & $py -c "from pathlib import Path; p = Path(r'$tmp') / 'items.jsonl'; b = p.read_bytes(); p.write_bytes(b.replace(b'OGDC', b'OGDX', 1))"
    & $py -m mizan.retrieval.demo --snapshot $tmp --ticker OGDC --as-of 2026-09-08
    Remove-Item -Recurse -Force $tmp
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
