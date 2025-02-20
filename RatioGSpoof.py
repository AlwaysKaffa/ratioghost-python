#!/usr/bin/env python3
"""
Ratio Ghost (Python Edition)
A full translation of the original Ratio Ghost project from Tcl to Python,
with dynamic upload multipliers, a "report 0 download" option, and a "pretend to seed" option.
Settings are persisted to a configuration file. HTTPS support and update checking are omitted.
"""

import re
import socket
import threading
import logging
import tkinter as tk
import time
import configparser
import os

# --- Global Configuration Defaults & Globals ---
DEFAULT_LISTEN_PORT = 8080   # Port where proxy listens

# Dynamic multiplier settings:
# If the last tracker response shows seeder count >= MIN_SEEDERS_THRESHOLD,
# then use UPLOAD_MULTIPLIER_HIGH; otherwise use UPLOAD_MULTIPLIER_LOW.
MIN_SEEDERS_THRESHOLD = 5      # Default threshold (can be changed via GUI)
UPLOAD_MULTIPLIER_LOW = 3.0    # Multiplier if seeders < threshold
UPLOAD_MULTIPLIER_HIGH = 1.5   # Multiplier if seeders >= threshold

# Other options:
NO_DOWNLOAD = False            # If True, reported "downloaded" value becomes 0.
PRETEND_TO_SEED = False        # If True, reported "left" value becomes 0 (appear as a seeder).

CONFIG_FILE = "ratio_ghost.ini"  # Configuration file name

LOG_LEVEL = logging.DEBUG      # Logging level

# Global dictionary to store seed counts by info_hash.
seed_counts = {}

# --- Logging Setup ---
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("RatioGhost")

# --- Configuration Persistence ---
def load_config():
    global NO_DOWNLOAD, PRETEND_TO_SEED, MIN_SEEDERS_THRESHOLD, UPLOAD_MULTIPLIER_LOW, UPLOAD_MULTIPLIER_HIGH
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        NO_DOWNLOAD = config.getboolean("Settings", "no_download", fallback=NO_DOWNLOAD)
        PRETEND_TO_SEED = config.getboolean("Settings", "pretend_to_seed", fallback=PRETEND_TO_SEED)
        MIN_SEEDERS_THRESHOLD = config.getint("Settings", "min_seeders_threshold", fallback=MIN_SEEDERS_THRESHOLD)
        UPLOAD_MULTIPLIER_LOW = config.getfloat("Settings", "upload_multiplier_low", fallback=UPLOAD_MULTIPLIER_LOW)
        UPLOAD_MULTIPLIER_HIGH = config.getfloat("Settings", "upload_multiplier_high", fallback=UPLOAD_MULTIPLIER_HIGH)
        logger.info("Configuration loaded from file.")

def save_config():
    config = configparser.ConfigParser()
    config["Settings"] = {
        "no_download": str(NO_DOWNLOAD),
        "pretend_to_seed": str(PRETEND_TO_SEED),
        "min_seeders_threshold": str(MIN_SEEDERS_THRESHOLD),
        "upload_multiplier_low": str(UPLOAD_MULTIPLIER_LOW),
        "upload_multiplier_high": str(UPLOAD_MULTIPLIER_HIGH)
    }
    with open(CONFIG_FILE, "w") as configfile:
        config.write(configfile)
    logger.info("Configuration saved to file.")

# --- Minimal Bencoding Decoder ---
def bdecode(data):
    """
    A minimal bdecoder that supports integers, byte strings, lists, and dictionaries.
    Returns the decoded Python object.
    """
    def decode_next(index):
        if data[index:index+1] == b"i":
            index += 1
            end = data.index(b"e", index)
            number = int(data[index:end])
            return number, end + 1
        elif data[index:index+1].isdigit():
            colon = data.index(b":", index)
            length = int(data[index:colon])
            start = colon + 1
            s = data[start:start+length]
            return s, start + length
        elif data[index:index+1] == b"l":
            index += 1
            lst = []
            while data[index:index+1] != b"e":
                item, index = decode_next(index)
                lst.append(item)
            return lst, index + 1
        elif data[index:index+1] == b"d":
            index += 1
            d = {}
            while data[index:index+1] != b"e":
                key, index = decode_next(index)
                value, index = decode_next(index)
                d[key] = value
            return d, index + 1
        else:
            raise ValueError("Invalid bencoded data")
    result, _ = decode_next(0)
    return result

# --- Proxy & Tracker Interception ---
def handle_client(client_socket, client_address):
    """
    Handles a client connection:
      - Reads the HTTP request.
      - Intercepts tracker GET requests containing an info_hash.
      - Modifies the "uploaded" parameter using a dynamic multiplier based on seed count.
      - If NO_DOWNLOAD is enabled, sets "downloaded" to 0.
      - If PRETEND_TO_SEED is enabled, sets "left" to 0.
      - Forwards the modified request to the tracker.
      - Parses the tracker response to update seed counts and logs a detailed message.
      - Returns the response to the client.
    """
    try:
        logger.debug(f"Client connected: {client_address}")
        request_data = client_socket.recv(8192)
        if not request_data:
            client_socket.close()
            return

        # Decode request
        request_text = request_data.decode("utf-8", errors="ignore")
        logger.debug(f"Received request:\n{request_text}")

        # Only process GET requests with a full URL.
        get_match = re.search(r"GET (http://[^ ]+) HTTP/1\.[01]", request_text)
        if not get_match:
            logger.debug("Not a valid tracker GET; forwarding unmodified.")
            forward_request(client_socket, request_data)
            return

        url = get_match.group(1)
        logger.debug(f"Parsed URL: {url}")

        # Extract tracker host, port, and path.
        url_regex = r"http://([-a-zA-Z0-9\.]+)(?::([0-9]+))?(/.*)"
        m = re.match(url_regex, url)
        if not m:
            logger.error("URL parsing failed.")
            client_socket.close()
            return

        host = m.group(1)
        port = int(m.group(2)) if m.group(2) else 80
        path = m.group(3)
        logger.debug(f"Tracker host: {host}, port: {port}, path: {path}")

        # Separate path and query string.
        if '?' in path:
            path_only, query_string = path.split('?', 1)
        else:
            path_only, query_string = path, ""

        # Only process if this is a tracker announce (must include info_hash).
        if "info_hash=" not in query_string:
            logger.debug("No info_hash found; forwarding unmodified.")
            forward_request(client_socket, request_data)
            return

        # Extract parameters.
        params = {}
        for key in ["downloaded", "uploaded", "left", "info_hash", "event"]:
            param_match = re.search(rf"{key}=([^&]+)", query_string)
            if param_match:
                params[key] = param_match.group(1)
        logger.debug(f"Extracted parameters: {params}")

        # Save the info_hash for dynamic multiplier lookup.
        info_hash = params.get("info_hash", None)
        # Choose multiplier based on stored seed count (default to low if unknown).
        if info_hash in seed_counts and seed_counts[info_hash] >= MIN_SEEDERS_THRESHOLD:
            multiplier = UPLOAD_MULTIPLIER_HIGH
        else:
            multiplier = UPLOAD_MULTIPLIER_LOW
        logger.debug(f"Using multiplier: {multiplier} for info_hash: {info_hash}")

        # Modify "uploaded" parameter.
        if "uploaded" in params:
            try:
                original_uploaded = int(params["uploaded"])
            except Exception:
                original_uploaded = 0
            modified_uploaded = original_uploaded * multiplier
            query_string = re.sub(r"(uploaded=)([^&]+)", r"\g<1>" + str(modified_uploaded), query_string, count=1)
            logger.debug(f"Modified 'uploaded': {original_uploaded} -> {modified_uploaded}")

        # If NO_DOWNLOAD is enabled, set "downloaded" to 0.
        if NO_DOWNLOAD and "downloaded=" in query_string:
            query_string = re.sub(r"(downloaded=)([^&]+)", r"\g<1>0", query_string, count=1)
            logger.debug("NO_DOWNLOAD enabled: Set 'downloaded' to 0.")

        # If PRETEND_TO_SEED is enabled, set "left" to 0.
        if PRETEND_TO_SEED and "left=" in query_string:
            query_string = re.sub(r"(left=)([^&]+)", r"\g<1>0", query_string, count=1)
            logger.debug("PRETEND_TO_SEED enabled: Set 'left' to 0.")

        # Reconstruct the new path and request line (using relative URL for tracker).
        new_path = f"{path_only}?{query_string}" if query_string else path_only
        new_request_line = f"GET {new_path} HTTP/1.1\r\n"

        # Reassemble the rest of the headers.
        header_lines = request_text.split("\r\n")[1:]
        updated_headers = []
        for line in header_lines:
            if line.lower().startswith("host:"):
                updated_headers.append(f"Host: {host}:{port}")
            elif line:
                updated_headers.append(line)
        headers = "\r\n".join(updated_headers) + "\r\n\r\n"

        modified_request = new_request_line + headers
        logger.debug(f"Modified request:\n{modified_request}")

        # Forward the modified request to the tracker.
        tracker_response = forward_to_tracker(host, port, modified_request)
        if tracker_response:
            # Attempt to decode the tracker response.
            try:
                decoded = bdecode(tracker_response)
            except Exception:
                logger.warning("Tracker response is not valid bencoded data; skipping seed count update.")
                decoded = None

            if decoded and isinstance(decoded, dict):
                complete = decoded.get(b"complete", b"0")
                incomplete = decoded.get(b"incomplete", b"0")
                interval = decoded.get(b"interval", b"0")
                # Update seed count.
                if info_hash:
                    seed_counts[info_hash] = int(complete)
                # Log a detailed message with tracker response data.
                logger.info(f"Tracker response for info_hash {info_hash}: complete={complete}, incomplete={incomplete}, interval={interval}")
            client_socket.sendall(tracker_response)
        else:
            logger.error("No response from tracker.")
    except Exception:
        logger.exception("Error handling client.")
    finally:
        client_socket.close()
        logger.debug(f"Client disconnected: {client_address}")

def forward_to_tracker(host, port, request_text):
    """
    Connects to the tracker, sends the modified request,
    and returns the full response.
    """
    try:
        with socket.create_connection((host, port), timeout=10) as tracker_sock:
            tracker_sock.sendall(request_text.encode("utf-8"))
            response = b""
            while True:
                chunk = tracker_sock.recv(8192)
                if not chunk:
                    break
                response += chunk
            logger.debug(f"Received {len(response)} bytes from tracker.")
            return response
    except Exception:
        logger.exception("Error forwarding to tracker.")
        return None

def forward_request(client_socket, data):
    """
    Forwards the original request unmodified.
    """
    try:
        client_socket.sendall(data)
    except Exception:
        logger.exception("Error forwarding request.")
    finally:
        client_socket.close()

def start_proxy_server(listen_port):
    """
    Starts the proxy server on the specified port.
    Each incoming connection is handled in a separate thread.
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('127.0.0.1', listen_port))
    server_socket.listen(50)
    logger.info(f"Proxy server listening on 127.0.0.1:{listen_port}")

    def server_loop():
        while True:
            client_sock, addr = server_socket.accept()
            threading.Thread(target=handle_client, args=(client_sock, addr), daemon=True).start()

    threading.Thread(target=server_loop, daemon=True).start()

# --- Graphical User Interface (Tkinter) ---
class RatioGhostGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Ratio Ghost (Python Edition)")
        self.root.geometry("550x500")
        
        # Upload Multiplier (Low) Label & Entry
        tk.Label(root, text="Upload Multiplier (Low):", font=("Arial", 12)).grid(
            row=0, column=0, padx=10, pady=5, sticky="e"
        )
        self.multiplier_low_var = tk.StringVar(value=str(UPLOAD_MULTIPLIER_LOW))
        self.entry_multiplier_low = tk.Entry(root, textvariable=self.multiplier_low_var, font=("Arial", 12))
        self.entry_multiplier_low.grid(row=0, column=1, padx=10, pady=5, sticky="w")
        
        # Upload Multiplier (High) Label & Entry
        tk.Label(root, text="Upload Multiplier (High):", font=("Arial", 12)).grid(
            row=1, column=0, padx=10, pady=5, sticky="e"
        )
        self.multiplier_high_var = tk.StringVar(value=str(UPLOAD_MULTIPLIER_HIGH))
        self.entry_multiplier_high = tk.Entry(root, textvariable=self.multiplier_high_var, font=("Arial", 12))
        self.entry_multiplier_high.grid(row=1, column=1, padx=10, pady=5, sticky="w")
        
        # Minimum Seeder Threshold Label & Entry
        tk.Label(root, text="Minimum Seeder Threshold:", font=("Arial", 12)).grid(
            row=2, column=0, padx=10, pady=5, sticky="e"
        )
        self.threshold_var = tk.StringVar(value=str(MIN_SEEDERS_THRESHOLD))
        self.entry_threshold = tk.Entry(root, textvariable=self.threshold_var, font=("Arial", 12))
        self.entry_threshold.grid(row=2, column=1, padx=10, pady=5, sticky="w")
        
        # Checkbutton for "Report 0 Download"
        self.no_download_var = tk.BooleanVar(value=NO_DOWNLOAD)
        self.chk_no_download = tk.Checkbutton(
            root,
            text="Report 0 Download",
            variable=self.no_download_var,
            command=self.toggle_no_download,
            font=("Arial", 12)
        )
        self.chk_no_download.grid(row=3, column=0, columnspan=2, pady=5)
        
        # Checkbutton for "Pretend to Seed"
        self.pretend_var = tk.BooleanVar(value=PRETEND_TO_SEED)
        self.chk_pretend = tk.Checkbutton(
            root,
            text="Pretend to Seed (set left=0)",
            variable=self.pretend_var,
            command=self.toggle_pretend,
            font=("Arial", 12)
        )
        self.chk_pretend.grid(row=4, column=0, columnspan=2, pady=5)
        
        # Save Settings Button
        self.btn_save = tk.Button(root, text="Save Settings", command=self.save_settings, font=("Arial", 12))
        self.btn_save.grid(row=5, column=0, columnspan=2, pady=10)
        
        # Log Display (Text widget)
        self.text_log = tk.Text(root, width=70, height=15, font=("Courier", 10))
        self.text_log.grid(row=6, column=0, columnspan=2, padx=10, pady=10)
        
        self.update_log_display()

    def save_settings(self):
        global UPLOAD_MULTIPLIER_LOW, UPLOAD_MULTIPLIER_HIGH, MIN_SEEDERS_THRESHOLD
        global NO_DOWNLOAD, PRETEND_TO_SEED
        try:
            UPLOAD_MULTIPLIER_LOW = float(self.multiplier_low_var.get())
            UPLOAD_MULTIPLIER_HIGH = float(self.multiplier_high_var.get())
            MIN_SEEDERS_THRESHOLD = int(self.threshold_var.get())
            NO_DOWNLOAD = self.no_download_var.get()
            PRETEND_TO_SEED = self.pretend_var.get()
            logger.info(f"Settings updated: Low={UPLOAD_MULTIPLIER_LOW}, High={UPLOAD_MULTIPLIER_HIGH}, "
                        f"Threshold={MIN_SEEDERS_THRESHOLD}, NO_DOWNLOAD={NO_DOWNLOAD}, "
                        f"PRETEND_TO_SEED={PRETEND_TO_SEED}")
            self.log("Settings saved.")
            save_config()
        except ValueError:
            self.log("Invalid input. Please check your numeric values.")

    def toggle_no_download(self):
        self.log(f"Report 0 Download {'enabled' if self.no_download_var.get() else 'disabled'}.")

    def toggle_pretend(self):
        self.log(f"Pretend to Seed {'enabled' if self.pretend_var.get() else 'disabled'}.")

    def log(self, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.text_log.insert(tk.END, f"{timestamp} {message}\n")
        self.text_log.see(tk.END)

    def update_log_display(self):
        self.root.after(1000, self.update_log_display)

# --- Application Initialization ---
def main():
    load_config()  # Load settings from configuration file
    start_proxy_server(DEFAULT_LISTEN_PORT)
    logger.info("Proxy server started.")
    root = tk.Tk()
    app = RatioGhostGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
