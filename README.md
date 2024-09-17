
# Cosmog Monitor Agent

## Overview

The **Cosmog Monitor Agent** is a Python script designed to monitor and manage devices running the Cosmog app. It checks the status of multiple devices and workers, restarts malfunctioning devices, and reports status updates via Discord webhooks. The script is highly configurable through the `config.ini` file and offers the ability to dynamically assess the health of your device network.

## Features

- **Device Monitoring**: Continuously checks the health of parent devices and workers using an API endpoint.
- **Automatic Restart**: Detects malfunctioning or offline devices and automatically restarts the Cosmog app or reboots the device.
- **Discord Notifications**: Sends real-time status updates and issues alerts via Discord webhook.
- **Grace Period Management**: Implements a grace period after restarting devices to avoid frequent restarts.
- **Dynamic Thresholding**: Adjusts thresholds based on the total number of workers for more flexible monitoring.
- **Logging**: Logs all operations and errors, making it easier to track device status and any problems that arise.

## Prerequisites

1. Python 3.6 or later
2. Required libraries:
   - `requests`
   - `json`
   - `configparser`
   - `socket`
   - `logging`

Install these dependencies by running:
```bash
pip install requests configparser
```

3. Android Debug Bridge (ADB) must be installed and added to your system's PATH.

## Configuration

The script reads its settings from a `config.ini` file. The configuration file must be present in the same directory as the Python script. Below are the keys in the configuration file:

### config.ini

```ini
[DEFAULT]
STATUS_URL = http://0.0.0.0:7072/api/status
TIMEOUT = 1200
CHECK_INTERVAL = 1800
PROBLEM_CHECK_INTERVAL = 90
MAX_WAIT_TIME = 3600
HOST = 192.168.0.
PORT = 5555
DEVICE_IP_FILE = DeviceIP.txt
DEVICE_NAME_IP_FILE = DeviceNameIP.txt
DISCORD_WEBHOOK = https://discord.com/api/webhooks/your_webhook_url_here
CONSECUTIVE_PROBLEM_THRESHOLD = 2
BUGGED_DEVICE_THRESHOLD = 3
GRACE_PERIOD = 900
```

### Key Descriptions

- **STATUS_URL**: The API endpoint to check device and worker status.
- **TIMEOUT**: Timeout in seconds for each request to the STATUS_URL.
- **CHECK_INTERVAL**: Time in seconds between each health check.
- **PROBLEM_CHECK_INTERVAL**: Interval between problem checks when an issue is detected.
- **MAX_WAIT_TIME**: Maximum time to wait before pausing monitoring due to a persistent problem.
- **HOST**: The base IP for scanning devices on the network.
- **PORT**: The port number where devices are listening.
- **DEVICE_IP_FILE**: A file to store discovered device IPs.
- **DEVICE_NAME_IP_FILE**: A file to store device names and corresponding IPs.
- **DISCORD_WEBHOOK**: URL for sending status updates to a Discord channel.
- **CONSECUTIVE_PROBLEM_THRESHOLD**: Number of consecutive problem checks before taking action.
- **BUGGED_DEVICE_THRESHOLD**: Number of failed attempts before marking a device as bugged.
- **GRACE_PERIOD**: Time in seconds before rechecking a device after restarting it.

## Usage

1. Clone this repository or download the script.
2. Install the required dependencies.
3. Edit the `config.ini` file to fit your setup.
4. Run the script:

```bash
python cosmog-monitor-agent.py
```

The script will:
- Discover devices within the specified IP range.
- Continuously monitor the health of devices and workers.
- Send status updates and alerts to Discord.
- Automatically reboot devices or restart the Cosmog app when needed.

## Logging

Logs are printed to the console and include timestamps, making it easy to troubleshoot or check device status at any point. Errors related to device restarts, JSON parsing, or ADB commands are logged with detailed messages.

