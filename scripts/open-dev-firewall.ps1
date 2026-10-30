# Mo firewall Windows cho 2 cong dev cua DocuVault (chay may chu web + API
# de mo app tren dien thoai trong LAN). Chay voi quyen admin. Xoa rule:
#   netsh advfirewall firewall delete rule name="DocuVault API 8000"
#   netsh advfirewall firewall delete rule name="DocuVault Web 53123"
$ErrorActionPreference = 'Stop'

netsh advfirewall firewall add rule name="DocuVault API 8000" dir=in action=allow protocol=TCP localport=8000 profile=any
netsh advfirewall firewall add rule name="DocuVault Web 53123" dir=in action=allow protocol=TCP localport=53123 profile=any
