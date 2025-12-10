# Start_Juna_Assistant.bat - Launch Script Documentation

## Overview

`Start_Juna_Assistant.bat` is a Windows batch script that launches the Juna Assistant Controller GUI (`launcher.py`). It includes comprehensive error checking and validation to ensure a reliable startup experience.

## Purpose

This script serves as the primary entry point for starting the Juna Assistant system on Windows. It:
- Validates the runtime environment (Python installation)
- Verifies required files exist
- Launches the GUI controller in windowless mode
- Provides clear error messages when problems occur

## How It Works

### Execution Flow

```
1. Navigate to project root directory
   ↓
2. Validate Python (pythonw.exe) is in PATH
   ↓
3. Verify launcher.py exists
   ↓
4. Launch GUI using pythonw (no console window)
   ↓
5. Exit batch script with success code
```

### Key Features

#### 1. Directory Navigation (Lines 5-11)
```batch
cd /d "%~dp0..\.."
if errorlevel 1 (
    echo ERROR: Failed to change to project directory
    pause
    exit /b 1
)
```

**What it does:**
- `%~dp0` = Directory containing this batch file
- `..\.."` = Go up two levels (from `scripts/launch/` to project root)
- `/d` flag = Change drive if needed (e.g., from C: to D:)
- Error check ensures the directory change succeeded

**Why it matters:**
- All subsequent file paths are relative to project root
- Prevents "file not found" errors from wrong working directory

#### 2. Python Installation Check (Lines 13-22)
```batch
where pythonw >nul 2>&1
if errorlevel 1 (
    echo ERROR: pythonw.exe not found in PATH
    echo.
    echo Please ensure Python is installed and added to your system PATH
    echo You can download Python from: https://www.python.org/downloads/
    pause
    exit /b 1
)
```

**What it does:**
- `where pythonw` searches for pythonw.exe in PATH
- `>nul 2>&1` suppresses output (only check exit code)
- `errorlevel 1` means pythonw was NOT found

**Why it matters:**
- Prevents cryptic "'pythonw' is not recognized" errors
- Provides actionable guidance (download link) for fixing the issue
- Catches environment problems before attempting launch

#### 3. File Existence Validation (Lines 24-32)
```batch
if not exist "scripts\launch\launcher.py" (
    echo ERROR: launcher.py not found!
    echo.
    echo Expected location: %CD%\scripts\launch\launcher.py
    echo Current directory: %CD%
    pause
    exit /b 1
)
```

**What it does:**
- Checks if `launcher.py` exists at expected location
- `%CD%` = Current directory (for debugging)

**Why it matters:**
- Detects incomplete installations or corrupted file structures
- Shows exact path for easier troubleshooting
- Prevents silent failures from launching non-existent script

#### 4. GUI Launch (Line 35)
```batch
start "Juna Assistant" pythonw "scripts\launch\launcher.py"
```

**Command breakdown:**
- `start` = Launches program in new window
- `"Juna Assistant"` = Window title (shown in Task Manager)
- `pythonw` = Python interpreter without console window (windowless)
- `"scripts\launch\launcher.py"` = Script to execute (quoted for spaces)

**Why pythonw instead of python:**
- `python.exe` = Shows console window
- `pythonw.exe` = No console window (GUI-only application)
- For GUI apps like CustomTkinter, pythonw provides cleaner UX

#### 5. Exit with Status Code (Line 38)
```batch
exit /b 0
```

**What it does:**
- `exit /b` = Exit batch script only (not entire command window)
- `0` = Success exit code
- Error paths use `exit /b 1` for failure

**Why it matters:**
- Allows batch file to be called from other scripts
- Proper exit codes enable automation and error handling

## Error Handling

### Error Types and Messages

1. **Directory Change Failed**
   ```
   ERROR: Failed to change to project directory
   ```
   **Cause**: Batch file in unexpected location or drive access issue  
   **Solution**: Ensure batch file is in `scripts/launch/` directory

2. **Python Not Found**
   ```
   ERROR: pythonw.exe not found in PATH
   
   Please ensure Python is installed and added to your system PATH
   You can download Python from: https://www.python.org/downloads/
   ```
   **Cause**: Python not installed or not in system PATH  
   **Solution**: Install Python or add to PATH (System → Environment Variables)

3. **Launcher Script Missing**
   ```
   ERROR: launcher.py not found!
   
   Expected location: C:\path\to\project\scripts\launch\launcher.py
   Current directory: C:\path\to\project
   ```
   **Cause**: File deleted, moved, or incomplete installation  
   **Solution**: Restore `launcher.py` from backup or reinstall

### Pause Behavior

All error messages include `pause` command:
- **Purpose**: Prevents error window from closing immediately
- **User action**: Press any key to dismiss
- **Rationale**: Ensures errors are readable, not missed

## Usage Examples

### Normal Usage
1. Double-click `Start_Juna_Assistant.bat`
2. GUI window appears if all checks pass
3. Batch window closes automatically

### Command Line Usage
```batch
cd C:\path\to\support_chatbot\scripts\launch
Start_Juna_Assistant.bat
```

### Automated Launch
```batch
:: Start Juna Assistant and capture exit code
call Start_Juna_Assistant.bat
if %errorlevel% neq 0 (
    echo Launch failed with code %errorlevel%
)
```

### Silent Launch (No Error Prompts)
```batch
:: Remove or comment out 'pause' commands for automation
:: Then run with output redirection
Start_Juna_Assistant.bat >nul 2>&1
```

## File Location

```
support_chatbot/
├── scripts/
│   └── launch/
│       ├── Start_Juna_Assistant.bat  ← This file
│       └── launcher.py
└── app/
    └── main.py
```

**Important**: This batch file MUST be in `scripts/launch/` because:
- It uses relative path `%~dp0..\..` to find project root
- If moved, directory navigation will fail

## Dependencies

### System Requirements
- **Windows**: Tested on Windows 10/11
- **Python**: Python 3.8+ with pythonw.exe in PATH
- **Permissions**: Read access to project directory

### Python Packages
The batch file itself doesn't check for these, but `launcher.py` requires:
- `customtkinter`
- `tkinter` (included with Python)
- See `requirements.txt` for full list

## Troubleshooting

### Issue: "pythonw.exe not found in PATH"

**Diagnosis:**
```batch
:: Check if Python is installed
python --version

:: Check if pythonw exists
where pythonw
```

**Solutions:**
1. **Python not installed**: Download from python.org
2. **Python not in PATH**: Add to environment variables
   - Windows Key + "environment variables"
   - Edit System PATH
   - Add Python installation directory (e.g., `C:\Python311\`)
   - Add Scripts directory (e.g., `C:\Python311\Scripts\`)
3. **Using virtual environment**: Activate venv first

### Issue: "launcher.py not found"

**Diagnosis:**
- Check if file exists: `dir scripts\launch\launcher.py`
- Verify you're in project root: `echo %CD%`

**Solutions:**
1. **File deleted**: Restore from Git or backup
2. **Wrong directory**: Ensure batch file is in `scripts/launch/`
3. **Permissions**: Check file permissions (right-click → Properties → Security)

### Issue: GUI doesn't appear (no error)

**Diagnosis:**
- Check Task Manager for "pythonw.exe" process
- Look for error log in launcher.py log file

**Solutions:**
1. **Check dependencies**: Run `pip install -r requirements.txt`
2. **Check Python version**: Ensure Python 3.8+
3. **Test launcher directly**: `python scripts\launch\launcher.py` (with console)

### Issue: Window closes immediately

**Possible causes:**
1. Error in launcher.py initialization
2. Missing dependencies
3. Configuration file issues

**Debug steps:**
```batch
:: Run with console window to see errors
python scripts\launch\launcher.py
```

## Best Practices

### For Users
1. **Don't modify this file** unless you understand batch scripting
2. **Create shortcuts** from this file to Desktop for easy access
3. **Check errors** - if launch fails, READ the error message before closing

### For Developers
1. **Keep paths relative** - don't hardcode absolute paths
2. **Test on fresh Windows install** to verify PATH assumptions
3. **Update error messages** if project structure changes
4. **Consider logging** for production deployments

### For Deployment
1. **Include in installer** as part of application setup
2. **Create desktop shortcut** pointing to this file
3. **Test with different Windows versions** (7, 10, 11)
4. **Document Python installation** as prerequisite

## Comparison with Other Launch Methods

### Why not use `python.exe` instead of `pythonw.exe`?
- `python.exe` shows console window alongside GUI
- `pythonw.exe` is designed for GUI-only applications
- Result: Cleaner user experience without console clutter

### Why not create Windows shortcut directly to launcher.py?
- No error checking (fails silently if Python not in PATH)
- No working directory control (may run from wrong folder)
- No validation (can't verify files exist before launch)

### Why not use Python entry points or setuptools?
- Requires package installation (`pip install -e .`)
- More complex for simple GUI application
- Batch file provides explicit error messages

## Advanced Customization

### Adding Logging
```batch
:: Create log directory if it doesn't exist
if not exist "logs" mkdir logs

:: Log launch attempt
echo %date% %time% - Launching Juna Assistant >> logs\launcher.log
start "Juna Assistant" pythonw "scripts\launch\launcher.py" 2>> logs\launcher_errors.log
```

### Auto-restart on Crash
```batch
:RESTART
start "Juna Assistant" /wait pythonw "scripts\launch\launcher.py"
if errorlevel 1 (
    echo Process crashed. Restarting in 5 seconds...
    timeout /t 5
    goto RESTART
)
```

### Environment Variable Support
```batch
:: Check for custom Python path
if defined JUNA_PYTHON (
    set PYTHON=%JUNA_PYTHON%
) else (
    set PYTHON=pythonw
)

start "Juna Assistant" %PYTHON% "scripts\launch\launcher.py"
```

## Exit Codes

| Code | Meaning | Details |
|------|---------|---------|
| 0    | Success | Launcher started successfully |
| 1    | Error   | Check error message for details |

## Changelog

### Version 2.0 (Current)
- ✅ Added Python validation with helpful error message
- ✅ Added file existence check with path display
- ✅ Added directory change validation
- ✅ Improved error messages with actionable guidance
- ✅ Added window title "Juna Assistant"
- ✅ Changed from `exit` to `exit /b` with proper codes
- ✅ Added quotes around launcher.py path for spaces
- ✅ Added comprehensive comments

### Version 1.0 (Original)
- Basic `cd` and `start` commands
- No error checking
- Silent failures

## Related Documentation

- **launcher.py**: See `docs/scripts/launcher.md` for GUI application details
- **requirements.txt**: See project root for Python dependencies
- **README.md**: See project root for installation instructions

## License

Part of the Juna Assistant project.
