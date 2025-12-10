# launcher.py - Juna Assistant Controller Application

## Overview

`launcher.py` is the main GUI controller for the Juna Assistant FastAPI server. It provides a CustomTkinter-based interface for managing the web server lifecycle, monitoring its status, and ingesting documents into the knowledge base.

## Purpose

This application serves as a system tray-style controller that:
- Starts/stops the FastAPI web server (uvicorn)
- Displays real-time server status and logs
- Manages knowledge base document ingestion
- Provides quick access to web interface and admin dashboard
- Handles zombie process cleanup automatically

## Architecture

### Main Components

1. **BotManager Class** (`ctk.CTk` subclass)
   - Main application window and UI controller
   - Manages subprocess lifecycle for the FastAPI server
   - Handles all user interactions via button callbacks

2. **Server Process Management**
   - Spawns FastAPI server as subprocess with real-time log streaming
   - Monitors process health and automatically detects crashes
   - Implements graceful shutdown and zombie process cleanup

3. **UI Layout**
   - **Left Column**: Server controls (START/STOP, status display, quick action buttons)
   - **Right Column**: Knowledge base ingestion controls
   - **Bottom Section**: System console with color-coded log output

## Key Features

### 1. Server Lifecycle Management

**Start Server** (`start_server()`, `run_server_process()`)
- Spawns `uvicorn` process with unbuffered output (`-u` flag)
- Streams stdout/stderr to UI console in real-time
- Automatically filters verbose HTTP logs and JSON debug output
- Detects port-in-use errors and triggers automatic cleanup

**Stop Server** (`stop_server()`)
- Force-kills process tree using `taskkill /T /F` on Windows
- Triggers background zombie cleanup to ensure port is released
- Resets UI state to OFFLINE

**Restart Server** (`restart_server()`)
- Non-blocking restart using `self.after()` to avoid UI freeze
- Waits 1 second (UPDATE_INTERVAL_MS) between stop and start

### 2. Auto Zombie Cleanup (`autoclean_zombies()`)

Automatically scans for processes holding the configured port (default: 8000) on startup and after server stop:
- Uses `netstat -ano | findstr :{PORT}` to find PIDs
- Validates netstat output format before parsing (prevents IndexError)
- Force-kills processes using `taskkill /F /PID {pid}`
- Runs in background thread to avoid blocking UI during startup

### 3. Log Management

**Thread-Safe Logging** (`log()`, `_log_ui()`)
- `log()` can be called from any thread - uses `self.after(0, ...)` to marshal to main thread
- `_log_ui()` performs actual UI update (must run on main thread)
- Automatically colorizes logs based on content keywords:
  - **Red (error)**: Contains 'error', '[failed]', '[x]', 'critical', 'crash', 'errno'
  - **Orange (warning)**: Contains '[warning]', '[debug]', '⚠', 'failed to'
  - **Green (success)**: Contains '[ok]', '[skip]', 'complete', '✓', 'success'
  - **Blue (info)**: Contains '[system]', '[ingest]', 'starting', '[auto-cleanup]', 'ready'

**Log Filtering** (`_should_show_log()`)
- Hides verbose uvicorn HTTP request logs
- Filters out raw JSON debug output
- Suppresses DEBUG: Generating/Payload messages
- Hides favicon.ico 404 errors

### 4. Knowledge Base Ingestion

**Folder Ingestion** (`start_ingestion()`, `_run_ingest_process()`)
- Executes `scripts/ingest.py` as subprocess
- Tracks metrics (processed/skipped/errors) from log output
- Parses JSON_SUMMARY lines for accurate final statistics
- Displays formatted summary card with duration and file counts

**Single File Ingestion** (`start_single_file_ingestion()`, `_run_single_file_ingest()`)
- Opens file picker for user to select PDF, TXT, MD, or DOCX files  
- Executes `scripts/ingest_single_file.py` with selected file path
- Streams real-time progress to console
- Shows completion summary with duration

**JSON Summary Parsing** (`_parse_json_summary()`)  
- Helper method to extract and parse JSON_SUMMARY lines from subprocess output
- Returns parsed stats dict or None on error
- Centralizes JSON parsing logic to avoid duplication

### 5. Quick Actions

**Open Web Interface** (`open_web_interface()`)
- Opens `http://127.0.0.1:{SERVER_PORT}` in default browser
- Runs in background thread to avoid blocking UI
- Uses `webbrowser.open()` for cross-platform compatibility

**Open Admin Dashboard** (`open_admin_dashboard()`)
- Opens `http://127.0.0.1:{SERVER_PORT}/admin` in default browser
- Runs in background thread to avoid blocking UI

### 6. Status Monitoring (`update_status()`)

- Polls process every UPDATE_INTERVAL_MS (1000ms = 1 second)
- Detects crashes via `process.poll() is not None`
- Updates status label (OFFLINE/STARTING/ONLINE/CRASHED)
- Shows real-time uptime, PID, and port

### 7. Cleanup on Exit (`on_closing()`)

- Registered via `protocol("WM_DELETE_WINDOW", ...)` 
- Ensures server process is stopped before app closes
- Prevents zombie processes when closing the GUI

## Configuration

### Class Constants

```python
SERVER_PORT = 8000               # FastAPI server port
UPDATE_INTERVAL_MS = 1000        # Status update frequency in milliseconds
```

### Global Constants

```python
PROJECT_ROOT                     # Project root directory (2 levels up from this file)
LAUNCHER_DIR                     # Directory containing this file
```

## Dependencies

### Python Standard Library
- `subprocess` - Process management
- `threading` - Background tasks  
- `time` - Timestamps and delays
- `os` - OS-specific operations
- `sys` - Python executable path
- `json` - JSON parsing
- `webbrowser` - Browser launch
- `pathlib.Path` - Path manipulation

### External Libraries
- `customtkinter` - Modern UI framework
- `tkinter` - Base Tk bindings (comes with Python)

## Windows-Specific Features

1. **DPI Awareness** (lines 17-22)
   - Sets process DPI awareness for crisp rendering on high-DPI displays
   - Uses `windll.shcore.SetProcessDpiAwareness(1)`

2. **AppUserModelID** (lines 38-45)
   - Sets unique app ID to prevent grouping with pythonw.exe in taskbar
   - Allows custom taskbar icon instead of Python logo

3. **CREATE_NO_WINDOW Flag** (subprocess calls)
   - Prevents command prompt windows from appearing when spawning subprocesses

4. **taskkill Command**
   - Uses `/T` flag to kill process tree (includes child processes)
   - Uses `/F` flag for forceful termination

## Usage Examples

### Basic Launch

```python
if __name__ == \"__main__\":
    app = BotManager()
    app.mainloop()
```

### Programmatic Server Control

```python
app = BotManager()

# Start server
app.start_server()

# Check status
if app.process:
    print(f\"Server running on port {app.SERVER_PORT}, PID: {app.process.pid}\")

# Stop server
app.stop_server()
```

### Custom Port Configuration

```python
class CustomBotManager(BotManager):
    SERVER_PORT = 8080  # Override default port
```

## Error Handling

### Port Already in Use
- Automatically detects `Errno 10048` or "address already in use"
- Triggers `autoclean_zombies()` to kill blocking process
- Logs helpful message to retry starting server

### Process Termination Failures
- Catches `subprocess.SubprocessError` and `OSError` when killing processes
- Logs warning with PID and error details instead of silent failure

### Icon Loading Failures
- Logs `[WARNING]` message if favicon.ico cannot be loaded
- Application continues normally (icon is non-critical)

### JSON Parsing Errors
- Returns `None` from `_parse_json_summary()` on parse failure
- Logs `[ERROR]` message with exception details
- Fallback metrics counting still works

## Best Practices

### Thread Safety
1. **Always use `self.log()` from background threads** - never call `self.log_area` methods directly
2. **Use `self.after()` for non-blocking delays** - never use `time.sleep()` on main thread
3. **Use local variables in `run_server_process()`** - prevents race conditions (`proc` vs `self.process`)

### Process Management
1. **Check `self.process` before operations** - prevents AttributeError on None
2. **Always set CREATE_NO_WINDOW** - prevents console windows on Windows
3. **Use tree kill (`/T`)** - ensures child processes are also terminated

### UI Updates
1. **Disable buttons during operations** - prevents double-clicking issues
2. **Re-enable buttons in finally blocks** - ensures UI doesn't get stuck
3. **Update status text** - keeps user informed during long operations

## Troubleshooting

### Server Won't Start
- **Check logs** - Look for import errors or dependency issues in console
- **Port conflict** - Click "Emergency Restart" to trigger zombie cleanup
- **Check project root** - Ensure PROJECT_ROOT path is correct

### UI Freezes
- **Check for blocking operations** - All long-running tasks should use `threading.Thread`
- **Verify after() usage** - Never use `time.sleep()` on main thread

### Logs Not Appearing
- **Check filter rules** - `_should_show_log()` may be hiding messages
- **Verify unbuffered mode** - Ensure `-u` flag is passed to Python subprocess

### Browser Buttons Don't Work
- **Check webbrowser import** - Verify `import webbrowser` exists
- **Check SERVER_PORT** - Ensure port matches running server
- **Try localhost** - If 127.0.0.1 doesn't work, try `localhost` URL

## File Structure

```
scripts/launch/
├── launcher.py              # This file
└── Start_Juna_Assistant.bat # Batch file to launch this

app/
├── main.py                  # FastAPI application entry point
└── static/
    └── favicon.ico          # Window icon

scripts/
├── ingest.py               # Folder ingestion script
└── ingest_single_file.py   # Single file ingestion script
```

## Changelog

### Latest Changes (Analysis & Fixes)

#### Critical Fixes
- ✅ Added missing `import webbrowser` - buttons now work
- ✅ Fixed UI freeze on restart - replaced `time.sleep(1)` with `self.after()`
- ✅ Added cleanup handler - prevents zombie processes on exit

#### Code Quality
- ✅ Replaced hardcoded port 8000 with `SERVER_PORT` constant (9 instances)
- ✅ Unified error message format to `[ERROR]` (was mixed `[Error]`/`[ERROR]`)
- ✅ Eliminated duplicate JSON parsing code with helper method
- ✅ Moved `import json` to top level for performance

#### Error Handling
- ✅ Replaced bare `except:` with specific exception types
- ✅ Added bounds check for netstat output parsing (prevents IndexError)
- ✅ Fixed icon loading to use `self.log()` instead of `print()`

#### Performance
- ✅ Added `UPDATE_INTERVAL_MS` constant instead of magic number 1000
- ✅ Browser opens in background thread - no UI blocking

## License

Part of the Juna Assistant project.
