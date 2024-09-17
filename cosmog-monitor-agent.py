import requests
import json
import time
import subprocess
import socket
import os
import logging
import configparser
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Read configuration from config.ini
config = configparser.ConfigParser()
config.read('config.ini')

# Configurations
STATUS_URL = config['DEFAULT'].get('STATUS_URL', 'http://0.0.0.0:7072/api/status')
TIMEOUT = config['DEFAULT'].getint('TIMEOUT', 1200)
CHECK_INTERVAL = config['DEFAULT'].getint('CHECK_INTERVAL', 1800)
PROBLEM_CHECK_INTERVAL = config['DEFAULT'].getint('PROBLEM_CHECK_INTERVAL', 90)
MAX_WAIT_TIME = config['DEFAULT'].getint('MAX_WAIT_TIME', 3600)
HOST = config['DEFAULT'].get('HOST', '192.168.0.')
PORT = config['DEFAULT'].getint('PORT', 5555)
DEVICE_IP_FILE = config['DEFAULT'].get('DEVICE_IP_FILE', 'DeviceIP.txt')
DEVICE_NAME_IP_FILE = config['DEFAULT'].get('DEVICE_NAME_IP_FILE', 'DeviceNameIP.txt')
DISCORD_WEBHOOK = config['DEFAULT'].get('DISCORD_WEBHOOK', 'https://discord.com/api/webhooks/your_webhook_url_here')
CONSECUTIVE_PROBLEM_THRESHOLD = config['DEFAULT'].getint('CONSECUTIVE_PROBLEM_THRESHOLD', 2)
BUGGED_DEVICE_THRESHOLD = config['DEFAULT'].getint('BUGGED_DEVICE_THRESHOLD', 3)
GRACE_PERIOD = config['DEFAULT'].getint('GRACE_PERIOD', 900)

# Global variables
discord_message_id = None
current_status = "Script Started"
current_message = "Device monitoring script has started."
consecutive_problem_count = 0  # Counter for consecutive checks below threshold

def is_port_open(host, port):
    s = socket.socket()
    try:
        s.settimeout(0.5)
        s.connect((host, port))
    except:
        return False
    else:
        s.close()
        return True

def get_file_modification_time(filename):
    try:
        return os.path.getmtime(filename)
    except FileNotFoundError:
        return 0

def write_devicename(hostport):
    subprocess.call("adb connect " + str(hostport), shell=True)
    time.sleep(1)  # Introduce a delay after connecting to ensure the device is ready

    cosmog_config_path = "cosmog.json"
    old_mod_time = get_file_modification_time(cosmog_config_path)

    timeout_duration = 10  # Timeout after 10 seconds

    try:
        subprocess.call(f"adb -s {hostport} pull /data/local/tmp/{cosmog_config_path}", shell=True,
                        timeout=timeout_duration)
        new_mod_time = get_file_modification_time(cosmog_config_path)

        if new_mod_time > old_mod_time:
            try:
                with open(cosmog_config_path) as jsonFile:
                    jsonObject = json.load(jsonFile)
                devicename = "=" + jsonObject['device_id']
                with open(DEVICE_NAME_IP_FILE, "a") as x:
                    x.write(hostport + devicename + "\n")
                return True
            except json.JSONDecodeError:
                logging.error(f"Could not decode JSON from {cosmog_config_path} for {hostport}.")
        else:
            logging.error(f"{cosmog_config_path} has not been updated for {hostport}.")
    except subprocess.TimeoutExpired:
        logging.error(f"Timeout expired while pulling {cosmog_config_path} for {hostport}.")
    except Exception as e:
        logging.error(f"Failed to pull {cosmog_config_path} for {hostport}: {e}")
    return False

def get_connected_devices():
    try:
        with open(DEVICE_NAME_IP_FILE, "r") as file:
            return {line.split('=')[1].strip(): line.split('=')[0] for line in file.read().splitlines()}
    except FileNotFoundError:
        logging.error(f"{DEVICE_NAME_IP_FILE} not found. Make sure the discovery script has been run.")
        return {}

def send_discord_embed():
    global discord_message_id, current_status, current_message

    embed = {
        "title": "Device Status Update",
        "description": current_message,
        "color": get_status_color(current_status),
        "timestamp": datetime.utcnow().isoformat()
    }

    data = {
        "embeds": [embed]
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(DISCORD_WEBHOOK, json=data, headers=headers)
        response.raise_for_status()
        logging.info("Discord embed sent successfully.")
    except requests.RequestException as e:
        logging.error(f"Failed to send Discord embed: {e}")

def get_status_color(status):
    status_colors = {
        "Everything Good": 0x00FF00,  # Green
        "Minor Issue": 0xFFFF00,  # Yellow
        "Problem": 0xFF0000,  # Red
        "Major Issue": 0xFF00FF,  # Purple
        "Significant Problem": 0xFF8000,  # Orange
        "Critical Problem": 0x8B0000,  # Dark Red
        "Investigating Issue": 0x0000FF,  # Blue
        "Improving": 0x00FFFF,  # Cyan
        "Deteriorating": 0xFF69B4,  # Hot Pink
        "Resolved": 0x32CD32,  # Lime Green
        "Partial Improvement": 0x9ACD32,  # Yellow Green
        "Persistent Problem": 0x8B0000,  # Dark Red
        "Script Started": 0x0000FF,  # Blue
        "Script Stopped": 0x808080,  # Grey
        "Bugged": 0xFFA500  # Orange
    }
    return status_colors.get(status, 0x808080)  # Default to grey if status not found

def restart_cosmog_app(device_ip, device_id, grace_period_devices):
    logging.info(f"Restarting Cosmog app on device {device_id}")
    try:
        subprocess.run(f"adb disconnect", shell=True)
        subprocess.run(f"adb connect {device_ip}", shell=True)
        subprocess.run(f'adb -s {device_ip} shell "am force-stop com.sy1vi3.cosmog"', shell=True)
        subprocess.run(f'adb -s {device_ip} shell "am start -n com.sy1vi3.cosmog/com.sy1vi3.cosmog.MainActivity"', shell=True)
        subprocess.run(f"adb disconnect", shell=True)
        logging.info(f"Cosmog app restarted on device {device_id}")
        # Start grace period after starting the app
        grace_period_devices[device_id] = datetime.now()
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to restart Cosmog app on device {device_id}: {e}")

def reboot_and_start_device(device_ip, device_id, grace_period_devices):
    global current_status, current_message
    logging.info(f"Rebooting device {device_id}")

    current_status = "Bugged"
    current_message = f"🔧 Rebooting bugged device {device_id}..."
    send_discord_embed()

    try:
        # Reboot device
        subprocess.run(f"adb -s {device_ip} reboot", shell=True, check=True)
        logging.info(f"Device {device_id} reboot command sent.")

        # Wait for device to reboot and become available
        time.sleep(120)  # Wait 2 minutes for reboot. Adjust as needed.

        # Try to reconnect to the device
        max_attempts = 10
        for attempt in range(max_attempts):
            time.sleep(10)  # Wait 10 seconds between attempts
            result = subprocess.run(f"adb connect {device_ip}", shell=True, capture_output=True, text=True)
            if "connected" in result.stdout or "already connected" in result.stdout:
                logging.info(f"Device {device_id} reconnected after reboot.")
                break
            else:
                logging.info(f"Attempt {attempt + 1}/{max_attempts}: Could not reconnect to device {device_id}.")
        else:
            logging.error(f"Failed to reconnect to device {device_id} after reboot.")
            return

        # Start the Cosmog app
        subprocess.run(f'adb -s {device_ip} shell "am start -n com.sy1vi3.cosmog/com.sy1vi3.cosmog.MainActivity"', shell=True, check=True)
        logging.info(f"Started Cosmog app on device {device_id}.")

        # Start grace period after starting the app
        grace_period_devices[device_id] = datetime.now()

    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to reboot and start device {device_id}: {e}")

def check_devices():
    try:
        response = requests.get(STATUS_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        parent_devices = {device['deviceId']: device for device in data.get('devices', [])}
        worker_devices = {worker['workerId']: worker for worker in data.get('workers', [])}
        return parent_devices, worker_devices
    except requests.RequestException as e:
        logging.error(f"Failed to fetch device status: {e}")
        return {}, {}

def get_status_summary(parent_devices, worker_devices):
    # Calculate total_workers and set thresholds dynamically
    total_workers = len(worker_devices)
    UNALLOCATED_WORKER_THRESHOLD = round(0.09 * total_workers)
    MIN_WORKER_THRESHOLD = total_workers - UNALLOCATED_WORKER_THRESHOLD

    offline_parents = [device_id for device_id, device in parent_devices.items() if not device.get('isAlive', False)]
    unallocated_workers = [worker_id for worker_id, worker in worker_devices.items() if
                           not worker.get('isAllocated', False)]

    total_parents = len(parent_devices)

    if total_workers == 0:
        return "Critical Problem", f"0 worker devices detected. This is a critical issue."
    elif total_workers < MIN_WORKER_THRESHOLD:
        return "Potential Problem", f"{total_workers} worker devices detected. Below the lenient threshold of {MIN_WORKER_THRESHOLD} workers."
    elif len(offline_parents) > 10:
        return "Major Issue", f"{len(offline_parents)}/{total_parents} parent devices offline. Monitoring and restarting halted."
    elif offline_parents:
        return "Problem", f"{len(offline_parents)}/{total_parents} parent devices offline."
    elif len(unallocated_workers) > UNALLOCATED_WORKER_THRESHOLD:
        percent_unallocated = (len(unallocated_workers) / total_workers) * 100
        return "Minor Issue", f"{len(unallocated_workers)} ({percent_unallocated:.2f}%) worker devices unallocated."
    else:
        return "Everything Good", f"All parent devices are online. {len(unallocated_workers)} unallocated workers (within acceptable range)."

def fix_offline_devices_on_startup(grace_period_devices):
    logging.info("Checking for offline devices on startup...")
    parent_devices, worker_devices = check_devices()
    offline_parents = [device_id for device_id, device in parent_devices.items() if not device.get('isAlive', False)]
    devices = get_connected_devices()

    for device_id in offline_parents:
        if device_id in devices:
            device_ip = devices[device_id]
            logging.info(f"Attempting to restart Cosmog app on device {device_id} at IP {device_ip}")
            restart_cosmog_app(device_ip, device_id, grace_period_devices)
        else:
            logging.warning(f"Device {device_id} not found in {DEVICE_NAME_IP_FILE}")

def monitor_and_restart():
    global current_status, current_message, consecutive_problem_count
    try:
        last_offline_workers = None
        offline_count = {}
        low_worker_count = {}
        devices = get_connected_devices()
        grace_period_devices = {}
        fix_offline_devices_on_startup(grace_period_devices)  # Fix offline devices on startup
        while True:
            parent_devices, worker_devices = check_devices()
            # Calculate total_workers and set thresholds dynamically
            total_workers = len(worker_devices)
            UNALLOCATED_WORKER_THRESHOLD = round(0.09 * total_workers)
            MIN_WORKER_THRESHOLD = total_workers - UNALLOCATED_WORKER_THRESHOLD

            status, message = get_status_summary(parent_devices, worker_devices)

            # Build parent_workers mapping
            parent_workers = {}
            for worker_id, worker in worker_devices.items():
                if worker.get('isAllocated', False):
                    parent_device_id = worker.get('parentDeviceId')
                    if parent_device_id:
                        parent_workers.setdefault(parent_device_id, []).append(worker_id)

            # Update low_worker_count for devices with 0-1 workers
            for device_id, device in parent_devices.items():
                if device_id in grace_period_devices:
                    # Skip devices in grace period
                    grace_start_time = grace_period_devices[device_id]
                    if (datetime.now() - grace_start_time).total_seconds() >= GRACE_PERIOD:
                        del grace_period_devices[device_id]
                        logging.info(f"Grace period ended for device {device_id}")
                    else:
                        continue  # Skip this device

                if device.get('isAlive', False):
                    num_workers = len(parent_workers.get(device_id, []))
                    if num_workers <= 1:
                        low_worker_count[device_id] = low_worker_count.get(device_id, 0) + 1
                    else:
                        if device_id in low_worker_count:
                            del low_worker_count[device_id]
                else:
                    if device_id in low_worker_count:
                        del low_worker_count[device_id]

            # Handle bugged devices
            for device_id, count in list(low_worker_count.items()):
                if count >= BUGGED_DEVICE_THRESHOLD:
                    if device_id in devices:
                        device_ip = devices[device_id]
                        # Validate the device is actually bugged by attempting to restart Cosmog app first
                        restart_cosmog_app(device_ip, device_id, grace_period_devices)
                        # Since we start the grace period after restarting the app, we don't need to check immediately
                        del low_worker_count[device_id]
                    else:
                        logging.warning(f"Device {device_id} not found in {DEVICE_NAME_IP_FILE}")
                        del low_worker_count[device_id]

            if status == "Potential Problem":
                consecutive_problem_count += 1
                if consecutive_problem_count >= CONSECUTIVE_PROBLEM_THRESHOLD:
                    status = "Significant Problem"
                    message = f"Worker count has been below {MIN_WORKER_THRESHOLD} for {CONSECUTIVE_PROBLEM_THRESHOLD} consecutive checks."
            else:
                consecutive_problem_count = 0

            if status != "Everything Good":
                logging.warning(f"Problem detected: {status} - {message}")
                current_status = status
                current_message = f"Problem detected: {message}"
                send_discord_embed()  # Post initial problem detection to Discord

                start_time = datetime.now()
                last_update_time = start_time

                while True:
                    # Update grace period devices
                    for device_id in list(grace_period_devices.keys()):
                        grace_start_time = grace_period_devices[device_id]
                        if (datetime.now() - grace_start_time).total_seconds() >= GRACE_PERIOD:
                            del grace_period_devices[device_id]
                            logging.info(f"Grace period ended for device {device_id}")

                    # Check and repair offline devices
                    offline_parents = [device_id for device_id, device in parent_devices.items() if
                                       not device.get('isAlive', False)]

                    for device_id in offline_parents:
                        offline_count[device_id] = offline_count.get(device_id, 0) + 1
                    offline_count = {device_id: count for device_id, count in offline_count.items() if
                                     device_id in offline_parents}

                    if offline_parents:
                        devices = get_connected_devices()
                        for device_id in offline_parents:
                            if device_id in grace_period_devices:
                                continue  # Skip devices in grace period
                            if offline_count.get(device_id, 0) >= 3:
                                if device_id in devices:
                                    logging.info(f"Attempting to restart Cosmog app on device {device_id}")
                                    restart_cosmog_app(devices[device_id], device_id, grace_period_devices)
                                    offline_count[device_id] = 0  # Reset count after attempt
                                else:
                                    logging.warning(f"Device {device_id} not found in {DEVICE_NAME_IP_FILE}")

                    # Update low_worker_count for devices with 0-1 workers
                    for device_id, device in parent_devices.items():
                        if device_id in grace_period_devices:
                            continue  # Skip devices in grace period
                        if device.get('isAlive', False):
                            num_workers = len(parent_workers.get(device_id, []))
                            if num_workers <= 1:
                                low_worker_count[device_id] = low_worker_count.get(device_id, 0) + 1
                            else:
                                if device_id in low_worker_count:
                                    del low_worker_count[device_id]
                        else:
                            if device_id in low_worker_count:
                                del low_worker_count[device_id]

                    # Handle bugged devices (as above)
                    for device_id, count in list(low_worker_count.items()):
                        if count >= BUGGED_DEVICE_THRESHOLD:
                            if device_id in devices:
                                device_ip = devices[device_id]
                                # Validate the device is actually bugged by attempting to restart Cosmog app first
                                restart_cosmog_app(device_ip, device_id, grace_period_devices)
                                del low_worker_count[device_id]
                            else:
                                logging.warning(f"Device {device_id} not found in {DEVICE_NAME_IP_FILE}")
                                del low_worker_count[device_id]

                    time.sleep(PROBLEM_CHECK_INTERVAL)
                    parent_devices, worker_devices = check_devices()
                    # Recalculate thresholds
                    total_workers = len(worker_devices)
                    UNALLOCATED_WORKER_THRESHOLD = round(0.09 * total_workers)
                    MIN_WORKER_THRESHOLD = total_workers - UNALLOCATED_WORKER_THRESHOLD

                    new_status, new_message = get_status_summary(parent_devices, worker_devices)
                    offline_workers = len([worker_id for worker_id, worker in worker_devices.items() if
                                           not worker.get('isAllocated', False)])

                    logging.debug(f"Offline workers: {offline_workers}, Last offline workers: {last_offline_workers}")

                    # Update Discord every PROBLEM_CHECK_INTERVAL
                    if (datetime.now() - last_update_time) >= timedelta(seconds=PROBLEM_CHECK_INTERVAL):
                        current_status = new_status
                        current_message = f"Current status: {new_message}"
                        send_discord_embed()
                        last_update_time = datetime.now()

                    if last_offline_workers is not None:
                        if offline_workers < last_offline_workers:
                            current_status = "Improving"
                            current_message = f"Situation improving: {offline_workers} workers offline (down from {last_offline_workers})."
                            send_discord_embed()
                            logging.info("Situation improving.")
                        elif offline_workers > last_offline_workers:
                            current_status = "Deteriorating"
                            current_message = f"Situation worsening: {offline_workers} workers offline (up from {last_offline_workers})."
                            send_discord_embed()
                            logging.warning("Situation worsening.")
                    else:
                        logging.debug("Initializing last_offline_workers")

                    last_offline_workers = offline_workers

                    if new_status == "Everything Good":
                        current_status = "Resolved"
                        current_message = f"Issue resolved: {new_message}"
                        send_discord_embed()
                        logging.info("Problem resolved.")
                        break

                    # Check if it's been an hour since the last improvement
                    if (datetime.now() - start_time) >= timedelta(seconds=MAX_WAIT_TIME):
                        current_status = "Persistent Problem"
                        current_message = f"No significant change after an hour: {new_message}"
                        send_discord_embed()
                        logging.error(current_message)
                        logging.info("Pausing monitoring due to lack of improvement in the last hour.")
                        input("Press Enter to resume monitoring...")
                        break

            else:
                if status != current_status or message != current_message:
                    current_status = status
                    current_message = message
                    send_discord_embed()
                    logging.info(f"Status update: {status} - {message}")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logging.info("Monitoring stopped by user.")
        current_status = "Script Stopped"
        current_message = "Monitoring script has been stopped by the user."
        send_discord_embed()

def discover_devices():
    with open(DEVICE_IP_FILE, "w") as f, open(DEVICE_NAME_IP_FILE, "w") as x:
        for DeviceIP in range(2, 255):
            ip = f"{HOST}{DeviceIP}"
            if is_port_open(ip, PORT):
                logging.info(f"[+] {ip}:{PORT} is open")
                if write_devicename(f"{ip}:{PORT}"):
                    f.write(f"{ip}:{PORT}\n")
            else:
                logging.debug(f"[!] {ip}:{PORT} is closed")

if __name__ == "__main__":
    send_discord_embed()
    discover_devices()
    monitor_and_restart()
