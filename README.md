# Ratio Ghost (Python Edition) Setup Guide  
### Tested Only on qBittorrent 5.0.4  
This guide provides step-by-step instructions to install, configure, and run Ratio Ghost (Python Edition) on a new device.  
**Important:** To work correctly, you must disable SSRF mitigation in qBittorrent and set up the proxy properly.  

## 1. Install Python  
### Windows Users:  
1. Download Python:  
   - Visit https://www.python.org/downloads/  
   - Download the latest stable version (e.g., Python 3.11.x).  
2. Run the Installer:  
   - **Important:** Check the box “Add Python to PATH” on the first screen.  
   - Click “Install Now” and follow the prompts.  
3. Verify Installation:  
   - Open Command Prompt (`Win + R`, type `cmd`, press Enter).  
   - Type:  
     python --version  
   - You should see the installed Python version.  

### macOS/Linux Users:  
- **macOS:** Download Python from https://www.python.org/downloads/mac-osx/ or use Homebrew:  
  brew install python  
- **Linux:** Most distributions include Python. To check, run:  
  python3 --version  
  If Python is missing, install it via:  
  sudo apt-get install python3  

## 2. Prepare the Code  
1. Create a New Folder:  
   - Create a folder (e.g., `RatioGhost`) on your desktop or another location.  
2. Save the Code:  
   - Open Notepad, VS Code, or Sublime Text.  
   - Copy the entire Ratio Ghost (Python Edition) code.  
   - Save the file as:  
     ratio_ghost.py  
     inside your `RatioGhost` folder.  

## 3. Configure qBittorrent  
### Step 1: Set Proxy Settings in qBittorrent  
1. Open **qBittorrent**.  
2. Click **Tools** → **Options**.  
3. Select **Connection** from the left panel.  
4. Under **Proxy Server**:  
   - **Type:** HTTP  
   - **Host:** 127.0.0.1  
   - **Port:** 8080 *(or the custom port set in Ratio Ghost)*  
   - **Check the following boxes**:  
     - ✅ Use proxy for peer connections  
     - ✅ Use proxy only for torrents  
     - ✅ Disable connections not supported by the proxy  
5. Click **Apply** and **OK**.  

### Step 2: Modify qBittorrent Configuration (SSRF Mitigation & HTTP Tracker Support)  
By default, qBittorrent **blocks** HTTP trackers through proxies due to security concerns. To allow Ratio Ghost to function, modify the configuration manually.  

1. **Close qBittorrent completely** (Right-click **System Tray Icon** → Exit).  
2. Open **File Explorer** and go to:  
   %AppData%\qBittorrent  
   (Paste the above in the address bar and press Enter).  
3. Locate and open `qBittorrent.ini` in Notepad.  
4. Find the section `[LegalNotice]` and **add or modify** the following lines:  
   ProxyPeerConnections=true  
   ProxyOnlyForTorrents=true  
   DisableSSRFMitigation=true  
5. Find `[BitTorrent]` and make sure HTTP trackers are allowed:  
   Session\TrackerPort=80  
6. Save and close the file.  
7. Restart **qBittorrent**.  

## 4. Run Ratio Ghost  
### Using Command Prompt / Terminal  
1. **Open Command Prompt or Terminal**:  
   - **Windows:** `Win + R` → type `cmd` → press Enter.  
   - **macOS/Linux:** Open **Terminal**.  
2. **Navigate to Your Code Folder**:  
   cd C:\Users\YourUsername\Desktop\RatioGhost  
   *(Replace `YourUsername` with your actual Windows username.)*  
3. **Run the Script**:  
   python ratio_ghost.py  
   *(On macOS/Linux, use `python3 ratio_ghost.py` if needed.)*  
4. **What to Expect**:  
   - The proxy server will start.  
   - A GUI will appear where you can:  
     - Set a **custom port** (default is `8080`).  
     - Enable **"Report 0 Download"**.  
     - Enable **"Pretend to Seed"**.  
     - Save settings (`ratio_ghost.ini` will be updated).  
   - The proxy is now **running on `127.0.0.1:8080`**.  

## 5. (Optional) Create an Executable  
If you want to run Ratio Ghost **without Python installed**, create an executable.  

1. **Install PyInstaller**:  
   pip install pyinstaller  
2. **Create Executable**:  
   pyinstaller --onefile --windowed ratio_ghost.py  
   - This will create a `dist` folder.  
   - Inside `dist`, you’ll find `ratio_ghost.exe` (Windows) or a binary file (macOS/Linux).  
3. **Run the Executable**:  
   - Double-click `ratio_ghost.exe` to start the application.  

## 6. Summary  
- ✅ **Install Python** from https://www.python.org/downloads/  
- ✅ **Save the code** as `ratio_ghost.py`  
- ✅ **Modify qBittorrent settings**  
- ✅ **Run Ratio Ghost** using:  
  python ratio_ghost.py  
- ✅ *(Optional)* **Create a standalone executable** using `pyinstaller`  

Now you’re ready to use **Ratio Ghost (Python Edition) with qBittorrent 5.0.4**! 🚀  
