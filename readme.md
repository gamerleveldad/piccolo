# Piccolo Server Infrastructure

Piccolo is a unified, containerized home server architecture running on a Raspberry Pi 5. It hosts a collection of custom Python and Node.js microservices, backend databases, and monitoring tools, all orchestrated via Docker Compose.

---

## 🛠 Hardware Specifications
* **Board:** Raspberry Pi 5 (8GB) - SC1112
* **Storage:** Silicon Power 256GB NVMe M.2 PCIe Gen3x4 2280
* **Case:** Argon NEO 5 M.2 NVMe Case
* **Power Supply:** Argon PWR GaN 27W USB-C
* **Network:** Hardwired Ethernet (Static IP: `192.168.4.55`)

---

## 🏗 Architecture & Services

All services communicate over the isolated internal `piccolo_net` Docker bridge network. Only specific web interfaces and APIs are exposed to the local host.

| Service Name | Description | Host Port |
| :--- | :--- | :--- |
| **Family Dashboard** | Tactical dashboard hub serving weather, tools, and widgets. | `8000` (TCP), `50222` (UDP) |
| **Game Scanner API** | Backend microservice for agentic video game metadata. | `8001` |
| **Game Scanner UI** | Frontend interface for the game scanner. | `8082` |
| **Crunchyroll API/UI** | Tracker for new anime releases. | `8003` (API), UI mapped internally |
| **Uptime Kuma** | Monitoring dashboard for container health and network pings. | `3001` |
| **Netdata** | Real-time hardware and resource utilization dashboard. | `19999` |
| **PostgreSQL** | Centralized database (15-alpine) for all microservices. | *Internal Only* |
| **Daemons** | Background Python workers (Game Scanner, Crunchyroll Scanner). | *Internal Only* |

> **Note on Frontend APIs:** Vite frontend configurations must explicitly target the Raspberry Pi's static IP (e.g., `VITE_API_URL=http://192.168.4.55:8001`) rather than `localhost` to ensure the client browser can route the requests properly.

---

## 💾 Backup & State Management (Crucial)

To prevent repository bloat and maintain security, the "state" of this server is **excluded** from Git version control. 

If you are migrating to a new Pi or recovering from a failure, you **must** manually restore the following from your secure backups before deploying:
1. The `.env` file in the root directory.
2. The entire `data/` directory (containing PostgreSQL volumes, Uptime Kuma configs, etc.).

---

## 🚀 Bare-Metal Deployment Guide

Follow these steps to deploy the Piccolo stack onto a brand new Raspberry Pi 5.

### 1. Initial Hardware Setup
1. Flash Raspberry Pi OS (64-bit) onto a USB drive. 
2. Assemble the Pi 5 into the Argon NEO 5 case with the NVMe drive installed.
3. Boot from the USB drive and connect via Ethernet.
4. Assign the MAC address to a DHCP Reservation/Static IP on your router (`192.168.4.55`).

### 2. NVMe & Case Configuration
SSH into the Pi and execute the Argon configuration scripts:
```bash
# Update EEPROM to boot from PCIe NVMe
curl [https://download.argon40.com/argon-eeprom.sh](https://download.argon40.com/argon-eeprom.sh) | bash

# Install Argon Neo 5 Fan & Power Button drivers
curl [https://download.argon40.com/argonneo5.sh](https://download.argon40.com/argonneo5.sh) | bash

### 3. Docker Install

# Install Docker
curl -fsSL [https://get.docker.com](https://get.docker.com) -o get-docker.sh
sudo sh get-docker.sh

# Grant user permissions (requires re-logging SSH to take effect)
sudo usermod -aG docker $USER

### 4. Clone and Data 

# Clone the repository
git clone <your-github-repo-url> ~/Piccolo

# Restore your backups (Run from wherever your backups are stored)
cp .env ~/Piccolo/
sudo cp -a data/ ~/Piccolo/

### 5. Build and Deploy

cd ~/Piccolo
docker compose up -d --build

Or use the update.sh <list of containers> file to do the update