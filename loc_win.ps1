Add-Type -AssemblyName System.Device
$w = New-Object System.Device.Location.GeoCoordinateWatcher([System.Device.Location.GeoPositionAccuracy]::High)
$w.Start()
for ($i = 0; $i -lt 150; $i++) {
    if ($w.Status -eq 'Ready' -or $w.Status -eq 'Disabled' -or $w.Permission -eq 'Denied') { break }
    Start-Sleep -Milliseconds 100
}
if ($w.Permission -eq 'Denied') { '{"error":"denied"}'; exit }
if ($w.Status -eq 'Disabled') { '{"error":"disabled"}'; exit }
$l = $w.Position.Location
if ($l.IsUnknown) { '{"error":"unknown"}'; exit }
@{ lat = $l.Latitude; lon = $l.Longitude; acc = $l.HorizontalAccuracy } | ConvertTo-Json -Compress