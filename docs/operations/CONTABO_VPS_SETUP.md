# Contabo VPS — Inspection and Hardening

Part of [PHASE6_DEPLOYMENT_PLAN.md](PHASE6_DEPLOYMENT_PLAN.md) (stages 6A and 6B).

**Status: nothing has been run on the server.** Section 1 is safe and read-only. Section 3 changes
the server. Do not run it until the inspection results have been reviewed and the founder has
approved, and use the version tailored to this server at that time. The main ZUVOORA application
may share this VPS and must keep working throughout.

## 1. Read-only inspection (stage 6A)

These commands only **read** information. They do not stop, delete, install or change anything.
Connect from Windows PowerShell with the username and IP from the Contabo panel:

```powershell
ssh YOUR_USERNAME@YOUR_VPS_IP
```

The password asked for is the **server (root) password** set when the VPS was ordered. It is not
the my.contabo.com account password, and not the VNC password. If it is lost, use the Contabo
panel: VPS → ⋮ → **Reset credentials** → **Password** tab. This may restart the server. Step-by-step help and fixes for
"Permission denied" are in
[PHASE6_FOUNDER_GUIDE.md, step 2.2](PHASE6_FOUNDER_GUIDE.md#step-22--connect-to-the-server).

Then paste this whole block. It saves everything into one file in your home folder:

```bash
{
echo "== OS ==";            cat /etc/os-release; uname -r
echo "== CPU/MEM ==";       nproc; free -h; swapon --show
echo "== DISK ==";          df -h; df -i /
echo "== UPTIME ==";        uptime
echo "== WHO AM I ==";      id
echo "== LISTENING PORTS =="; sudo ss -tulpn
echo "== FIREWALL ==";      sudo ufw status verbose 2>&1; sudo iptables -S 2>/dev/null | head -40
echo "== DOCKER ==";        docker --version 2>&1; docker compose version 2>&1
echo "== CONTAINERS ==";    sudo docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1
echo "== COMPOSE PROJECTS =="; sudo docker compose ls 2>&1
echo "== DOCKER NETWORKS =="; sudo docker network ls 2>&1
echo "== DOCKER DISK ==";   sudo docker system df 2>&1
echo "== DOCKER DAEMON CONFIG =="; sudo cat /etc/docker/daemon.json 2>&1
echo "== WEB SERVERS ==";   systemctl is-active nginx caddy apache2 traefik 2>&1; ls /etc/nginx/sites-enabled /etc/caddy 2>&1
echo "== SERVICES ==";      systemctl list-units --type=service --state=running --no-pager
echo "== SSH SETTINGS ==";  sudo sshd -T 2>/dev/null | grep -Ei '^(port|permitrootlogin|passwordauthentication|pubkeyauthentication|kbdinteractiveauthentication|allowusers|x11forwarding) '
echo "== USERS WITH SHELLS =="; grep -Ev '(nologin|false)$' /etc/passwd | cut -d: -f1
echo "== SUDO AND DOCKER GROUPS =="; getent group sudo docker
echo "== UPDATES ==";       systemctl is-active unattended-upgrades 2>&1; apt list --upgradable 2>/dev/null | wc -l
echo "== FAIL2BAN ==";      systemctl is-active fail2ban 2>&1
echo "== TIME ==";          timedatectl | grep -E 'Time zone|synchronized'
} > ~/engage-inspection.txt 2>&1; echo "Saved to ~/engage-inspection.txt"
```

Copy the file to your laptop. Run this in a **new** PowerShell window on your laptop, not on the
server:

```powershell
scp YOUR_USERNAME@YOUR_VPS_IP:~/engage-inspection.txt $HOME\Desktop\engage-inspection.txt
```

### What to remove before sharing the output

Open the file in Notepad. Replace each of these with `[REDACTED]`:

- the server's public IP address (and any other public IPs);
- host names you consider private;
- account names other than your own.

Never share passwords, keys or the contents of `.env` files. The commands above do not print any.

### What the output tells us

| Section | Decision it drives |
|---|---|
| OS | Ubuntu 22.04 or 24.04 LTS is fine. Anything older needs an upgrade plan first. |
| CPU, memory, disk | Whether staging and production both fit next to ZUVOORA (budget in the plan §5) |
| Listening ports and web servers | Whether to reuse an existing Nginx, Caddy or Traefik, or install Caddy |
| Containers and Compose projects | What belongs to ZUVOORA and must not be touched; name clashes |
| Firewall and iptables | What is open today; whether Docker already bypasses UFW for ZUVOORA |
| SSH settings | Whether passwords or root login are on (6B fixes this) |
| Groups | Who effectively has root (`sudo` and `docker` members) |
| Updates and fail2ban | What 6B must install or enable |

### Inspection results (2026-11-25)

Run by the founder as `root` after the SSH key login worked. The IP address is not recorded here.

| Area | Finding | Consequence |
|---|---|---|
| OS | **Ubuntu 24.04.5 LTS**, kernel 6.8 | Supported until 2029 (standard support). No upgrade needed. |
| CPU, memory, disk | 6 cores, 11 GiB usable RAM, **no swap**, 193 GB disk with 2.7 GB used | Enough for both environments. Add a 2 GB swap file as a safety net (3.7). |
| What runs | **Nothing but the base system.** No Docker, no web server, no containers, no ZUVOORA application. The only public listener is SSH on port 22. | No neighbour to protect yet. **Proxy decision: Caddy** (plan §5). Docker is installed from Docker's official repository (3.5). |
| Firewall | UFW **inactive**; iptables policies ACCEPT | Enable UFW with 22, 80 and 443 only (3.3). |
| SSH | `permitrootlogin yes`, `passwordauthentication yes`, `x11forwarding yes`. The key login for root works (key added through Contabo "Reset credentials" → SSH-Key). | Turn off passwords, root login and X11 after the admin user works (3.1–3.2). |
| Users | `root`; `ubuntu` (in the `sudo` group, image default, unused); `sync` (system) | Lock the unused `ubuntu` account (3.1). |
| Updates | unattended-upgrades active; **21 packages waiting** | Apply them first (3.4). |
| fail2ban | Not installed | Install (3.4). |
| Time | Europe/Berlin, synchronised | Fine. The application stores times in UTC. |
| Backups | Contabo Auto Backup add-on not active; no snapshots | Take a snapshot before hardening if the panel allows. The server is empty, so the risk is low. |

### Access method (from 2026-11-25)

- **Login:** SSH key only (ed25519). The key was added through the Contabo panel: Reset
  credentials → SSH-Key.
- **User:** `root` until stage 6B, then `engageadmin`.
- **Snapshot:** a Contabo snapshot was taken by the founder before hardening, on 2026-11-25.

Day-to-day login steps, the `ssh engage-vps` shortcut, the key backup and lost-key recovery are
in [PHASE6_FOUNDER_GUIDE.md, Part 2b](PHASE6_FOUNDER_GUIDE.md#part-2b--how-to-log-in-to-your-server-every-time-with-your-ssh-key).

## 2. Safety rules for every server change (stage 6B onward)

1. **Take a Contabo snapshot first**, if the plan includes one (Contabo panel → your VPS →
   Snapshots).
2. **Keep your current SSH session open** while you change SSH or firewall settings, and test a
   **new** login in a second window before closing the first.
3. Know the way back in: the Contabo panel's **VNC / rescue console** works even when SSH and the
   firewall are broken.
4. **Check ZUVOORA before and after each step:** open its website, and run `sudo docker ps` to
   confirm its containers are "Up".
5. One change at a time. Write down each command and its result.

## 3. Hardening outline (stage 6B — not yet approved)

These steps are a **template**. The exact commands will be adjusted to the inspection output, for
example the existing user, ports and proxy. They are listed here so the founder knows what to
expect.

### 3.1 Named admin user and SSH key

On the **laptop**: `ssh-keygen -t ed25519 -C "engage-admin-laptop"`, with a passphrase. See the
founder guide.

On the server:

```bash
sudo adduser engageadmin            # choose a strong password (for sudo), store it in the password manager
sudo usermod -aG sudo engageadmin
sudo install -d -m 700 -o engageadmin -g engageadmin /home/engageadmin/.ssh
# This server: root already has the founder's PUBLIC key (added through Contabo), so copy it:
sudo install -m 600 -o engageadmin -g engageadmin /root/.ssh/authorized_keys /home/engageadmin/.ssh/authorized_keys
# Lock the unused image account "ubuntu" (no password login, no shell):
sudo passwd -l ubuntu && sudo usermod -s /usr/sbin/nologin ubuntu
```

Test in a **second** window: `ssh engageadmin@YOUR_VPS_IP`, then `sudo whoami`. It should print
`root`.

### 3.2 Turn off passwords and root login (only after 3.1 works)

```bash
sudo tee /etc/ssh/sshd_config.d/60-engage-hardening.conf >/dev/null <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
EOF
sudo sshd -t && sudo systemctl reload ssh
```

Test a new login again before closing the old window.

**If ZUVOORA deploys through another account (for example CI over SSH), keep that account's key
working.** The inspection shows this.

### 3.3 Firewall (keep ZUVOORA's ports)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# + any port ZUVOORA needs, from the inspection
sudo ufw enable
sudo ufw status verbose
```

UFW does **not** protect ports that Docker publishes. That is why Engage containers publish
nothing publicly: either no host ports at all, or `127.0.0.1` only. ZUVOORA's own published ports
are reviewed separately and not changed without approval.

### 3.4 Automatic security updates, fail2ban and time

```bash
sudo apt update
sudo apt full-upgrade -y                          # this server had 21 waiting updates
[ -f /var/run/reboot-required ] && echo "REBOOT NEEDED"   # if printed: sudo reboot, wait 1 min, log in again
sudo apt install -y unattended-upgrades fail2ban
sudo dpkg-reconfigure -plow unattended-upgrades   # answer "Yes"
sudo systemctl enable --now fail2ban            # default sshd jail
timedatectl                                      # "System clock synchronized: yes"
```

Automatic reboots stay **off**. Kernel updates are applied with a planned reboot that is announced
to the pilot clinics.

### 3.5 Install Docker (official repository) and set daemon defaults

This server has no Docker. Use Docker's own apt repository, not the snap package or `docker.io`:

```bash
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker --version && docker compose version
```

Do **not** add `engageadmin` to the `docker` group. Use `sudo docker ...`, because docker group
membership is equivalent to root without a password.

Then create `/etc/docker/daemon.json` with the content below, and run
`sudo systemctl restart docker`. Nothing else runs on this server, so the restart is safe.

```json
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "live-restore": true,
  "no-new-privileges": true
}
```

Engage's Compose file sets these per container anyway, so this step is optional and can wait.

### 3.6 Folders and permissions for Engage

```bash
sudo install -d -m 750 -o root -g root /opt/zuvoora-engage
sudo install -d -m 700 -o root -g root /opt/zuvoora-engage/production /opt/zuvoora-engage/staging
# later: each env file is created by the founder with  sudo nano /opt/zuvoora-engage/<env>/.env
#        and protected with                         sudo chmod 600 /opt/zuvoora-engage/<env>/.env
```

### 3.7 Swap (recommended on this server: there is none)

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf && sudo sysctl --system >/dev/null
free -h
```

### 3.8 Acceptance checks for 6B

```bash
sudo sshd -T | grep -Ei '^(passwordauthentication|permitrootlogin) '   # both "no"
sudo ufw status verbose
systemctl is-active unattended-upgrades fail2ban
```

From the laptop, `ssh root@YOUR_VPS_IP` must be refused. ZUVOORA must still work.

### 3.9 Undo

- **SSH:** remove `/etc/ssh/sshd_config.d/60-engage-hardening.conf`, then
  `sudo systemctl reload ssh`. Use the VNC console if locked out.
- **Firewall:** `sudo ufw disable`.
- **Last resort:** restore the snapshot. This also loses ZUVOORA changes made since the snapshot.
