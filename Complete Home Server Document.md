Complete Home Server Handoff Document
📋 System Overview
Hardware (HP Pavilion 15 Laptop)
Component	Spec
CPU	Intel i7-6500U (2 cores / 4 threads)
RAM	16GB DDR3
GPU	Intel HD 520 + NVIDIA 940MX
Storage	128GB SSD + 500GB SSD
Power	Always plugged in (no battery)
Proxmox Host
Item	Value
IP Address	192.168.1.60
Web Interface	https://192.168.1.60:8006/
DNS Name	panel.home.dns:8006/
🖥️ Virtual Machines & Containers
ID	Name	OS	IP	CPU	RAM	Storage
100	Linux Mint	Mint Mate	192.168.1.100	1 core	4GB	48GB
101	DNS Server	Ubuntu 22.04	192.168.1.101	1 core	512MB	4GB
200	Ubuntu Server	Ubuntu Server	192.168.1.200	3 cores	10GB	128GB
🌐 DNS Configuration
DNS Server (CT 101)
Item	Value
IP	192.168.1.101
Domain	home.dns
Software	dnsmasq
Status	✅ Running
DNS Records
Short Name	Full Address	IP
panel	panel.home.dns	192.168.1.60
mint	mint.home.dns	192.168.1.100
dns	dns.home.dns	192.168.1.101
server	server.home.dns	192.168.1.200
media-server	media-server.home.dns	192.168.1.200
files	files.home.dns	192.168.1.200
xyran	xyran.home.dns	192.168.1.200
🔗 Access URLs
From Any Device on Network (using DNS)
Service	URL
Proxmox Host	panel.home.dns:8006/
Linux Mint (SSH)	ssh user@mint.home.dns
Ubuntu Server (SSH)	ssh user@server.home.dns
Media Server	media-server.home.dns:PORT/
Files Server	files.home.dns:PORT/
Xyran	xyran.home.dns:PORT/
Direct IP Access (if DNS not configured)
Service	URL
Proxmox Host	https://192.168.1.60:8006/
Linux Mint (SSH)	ssh user@192.168.1.100
Ubuntu Server (SSH)	ssh user@192.168.1.200
🛠️ Maintenance Commands
Proxmox Host (on laptop)
bash
# Check all VM/CT status
qm list
pct list

# Start/Stop VMs
qm start 100    # Linux Mint
qm start 200    # Ubuntu Server
pct start 101   # DNS Server

# Enter container shell
pct enter 101

# Open VM console
qm terminal 100
DNS Server Management
bash
# Enter DNS container
pct enter 101

# Edit DNS records
nano /etc/dnsmasq.conf

# Restart DNS service
systemctl restart dnsmasq

# Test DNS resolution
nslookup panel
dig panel.home.dns

# Check DNS logs
journalctl -u dnsmasq -f
Add New DNS Record
bash
pct enter 101
nano /etc/dnsmasq.conf
# Add line: address=/newservice/192.168.1.X
systemctl restart dnsmasq
💻 Client Device Setup
Windows PC/Laptop
DNS Settings:

Control Panel → Network → Adapter Properties

IPv4 Properties → Use DNS: 192.168.1.101

Advanced → DNS → Append suffix: home.dns

Hosts file (optional):
C:\Windows\System32\drivers\etc\hosts

text
192.168.1.60 panel
192.168.1.100 mint
192.168.1.101 dns
192.168.1.200 server
Linux Desktop
bash
# Edit resolv.conf
sudo nano /etc/resolv.conf
Add:

text
nameserver 192.168.1.101
search home.dns
bash
# Make permanent
sudo chattr +i /etc/resolv.conf
macOS
System Settings → Network

Select connection → Details

DNS → Add 192.168.1.101

Search Domains → Add home.dns

Router (Optional - Best for whole network)
Set DHCP DNS Server to: 192.168.1.101

📊 Resource Monitoring
Check CPU/Memory Usage
bash
# From Proxmox host
pct status 101
qm status 100
qm status 200

# Real-time monitoring
htop

# Temperature monitoring
sensors
watch -n 2 sensors
Current Allocation vs Physical
Resource	Physical	Allocated	Status
CPU Cores	2 (4 threads)	5 cores	⚠️ Over-allocated
RAM	16GB	14.5GB	✅ OK
Storage	128GB + 500GB	180GB	✅ OK
Note: CPU over-allocation is fine as long as not all VMs are busy simultaneously.

🔄 Backup Strategy
Backup VMs to 500GB SSD
bash
# Manual backup
vzdump 100 101 200 --compress zstd --mode snapshot --storage ssd500

# Scheduled backup (crontab)
crontab -e
# Add: 0 2 * * * vzdump 100 101 200 --compress zstd --mode snapshot --storage ssd500
Restore a VM
bash
# List backups
ls -la /mnt/ssd500/dump/

# Restore
qmrestore /mnt/ssd500/dump/vzdump-qemu-100-*.vma.zst 100
⚠️ Important Notes
Laptop-Specific
Issue	Solution
No battery	Always keep plugged in, consider UPS
Overheating	Elevate laptop, clean fans, use thermald
CPU throttling	Monitor temps, reduce VM load if needed
WiFi instability	Use Ethernet cable for reliability
DNS Notes
DNS only resolves IPs, not ports (always include :PORT)

Chrome needs trailing slash: panel.home.dns:8006/

Windows needs DNS suffix home.dns for short names

Container 101 must be running for DNS to work



also all the vms are on the 500gb ssd and proxmox os is on 128 gb ssd 