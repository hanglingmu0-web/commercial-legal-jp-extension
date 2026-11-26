# 【PC(Windows PowerShell 5.1以降)で実行】Python が使えない場合の代替。fetch_legal_sources.py と同じ取得先・同じ manifest 形式。
# 使い方: powershell -ExecutionPolicy Bypass -File .\fetch_legal_sources.ps1 -OutRoot "C:\Users\<user>\Documents\CL-Extension-Work\legal_fetch"
param([Parameter(Mandatory=$true)][string]$OutRoot)
$ErrorActionPreference = "Continue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$base = "https://laws.e-gov.go.jp"; $jftc = "https://www.jftc.go.jp"
$items = @(
 @{id="act_331AC0000000120"; req=$true;  url="$base/api/2/law_data/331AC0000000120?response_format=json"; fn="raw_act_331AC0000000120.json"; kind="egov_law_data"},
 @{id="rule_507M60200000009"; req=$true; url="$base/api/2/law_data/507M60200000009?response_format=json"; fn="raw_rule_507M60200000009.json"; kind="egov_law_data"},
 @{id="revisions_331AC0000000120"; req=$true; url="$base/api/2/law_revisions/331AC0000000120?response_format=json"; fn="raw_revisions_331AC0000000120.json"; kind="egov_law_revisions"},
 @{id="amending_act_507AC0000000041"; req=$false; url="$base/api/2/law_data/507AC0000000041?response_format=json"; fn="raw_amending_act_507AC0000000041.json"; kind="egov_law_data_amending"},
 @{id="jftc_kaiseihou_jyobun"; req=$false; url="$jftc/partnership_package/toritekihou-jyobun.pdf"; fn="raw_jftc_kaiseihou_jyobun.pdf"; kind="official_pdf_suppl"},
 @{id="jftc_shinkyu"; req=$false; url="$jftc/partnership_package/toritekihou-sinkyu.pdf"; fn="raw_jftc_shinkyu.pdf"; kind="official_pdf"},
 @{id="jftc_text_r7"; req=$false; url="$jftc/toriteki/r7text.pdf"; fn="raw_jftc_text_r7.pdf"; kind="official_pdf_guide"}
)
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"; $out = Join-Path $OutRoot $stamp; New-Item -ItemType Directory -Force -Path $out | Out-Null
$man = [ordered]@{fetched_by="pc/fetch_legal_sources.ps1"; started_at=(Get-Date -Format "o"); host=$env:COMPUTERNAME; items=[ordered]@{}}
$sums = @(); $bad = 0; $log = Join-Path $out "fetch_log.txt"
foreach ($it in $items) {
  $rec = [ordered]@{url=$it.url; kind=$it.kind; required=$it.req; retrieved_at=(Get-Date -Format "o")}
  try {
    $path = Join-Path $out $it.fn
    $r = Invoke-WebRequest -Uri $it.url -OutFile $path -UseBasicParsing -TimeoutSec 60 -PassThru -Headers @{"User-Agent"="legal-extension-fetch/1.0"}
    $h = (Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLower()
    $rec.status = [int]$r.StatusCode; $rec.file = $it.fn; $rec.bytes = (Get-Item $path).Length; $rec.sha256 = $h; $rec.result = "OK"
    $sums += "$h *$($it.fn)"; "OK   $($it.id) $($rec.bytes) bytes sha256=$($h.Substring(0,16))" | Tee-Object -FilePath $log -Append
  } catch {
    $code = $null; if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    $rec.status = $code; $rec.result = "ERROR"; $rec.error = $_.Exception.Message
    if ($it.req) { $bad++ }
    "FAIL $($it.id) status=$code $($_.Exception.Message)" | Tee-Object -FilePath $log -Append
  }
  $man.items[$it.id] = $rec
}
$man.finished_at = (Get-Date -Format "o"); $man.required_failures = $bad
($man | ConvertTo-Json -Depth 6) | Out-File -Encoding utf8 (Join-Path $out "manifest.json")
$sums | Out-File -Encoding ascii (Join-Path $out "SHA256SUMS.txt")
"保存先: $out" | Tee-Object -FilePath $log -Append
if ($bad -eq 0) { "結果: 正常終了(必須資料すべて取得)" | Tee-Object -FilePath $log -Append; exit 0 } else { "結果: 異常終了(必須資料の取得失敗 $bad 件)" | Tee-Object -FilePath $log -Append; exit 2 }
