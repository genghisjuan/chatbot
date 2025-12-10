import customtkinter as ctk
import tkinter as tk # Fallback for some constants
from tkinter import messagebox
import subprocess
import sys
import os
import time
import threading
import webbrowser
import json
from pathlib import Path

# Get project root (launcher is in scripts/launch/, need to go up 2 levels)
LAUNCHER_DIR = Path(__file__).parent
PROJECT_ROOT = LAUNCHER_DIR.parent.parent

# Enable Windows DPI awareness for crisp rendering on high-DPI displays
if os.name == 'nt':
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)  # System DPI aware
    except Exception:
        pass  # Fallback if this fails on older Windows versions

# Configuration
ctk.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("dark-blue")  # Themes: "blue" (standard), "green", "dark-blue"

class BotManager(ctk.CTk):
    # Class constants
    SERVER_PORT = 8000
    UPDATE_INTERVAL_MS = 1000  # Status update frequency in milliseconds
    def __init__(self):
        super().__init__()
        self.title("Juna Assistant Controller")
        self.geometry("600x650")
        self.minsize(550, 600)  # Prevent window from becoming too small
        
        # Set Windows AppUserModelID to ensure unique taskbar icon
        # This prevents Windows from grouping with pythonw.exe
        if os.name == 'nt':
            try:
                myappid = 'JunaAssistant.Controller.1.0'
                windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception:
                pass  # Not critical if this fails
        
        # Set window and taskbar icon (Windows-specific)
        try:
            icon_path = PROJECT_ROOT / "app" / "static" / "favicon.ico"
            if icon_path.exists():
                self.iconbitmap(str(icon_path))
        except Exception as e:
            self.log(f"[WARNING] Failed to load icon: {e}")
        
        self.process = None
        self.start_time = None
        
        # --- UI Header ---
        self.header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.header_frame.pack(pady=(20, 10))
        
        self.lbl_title = ctk.CTkLabel(self.header_frame, text="JUNA ASSISTANT", font=("Roboto Medium", 24))
        self.lbl_title.pack()
        self.lbl_subtitle = ctk.CTkLabel(self.header_frame, text="System Controller", font=("Roboto", 14), text_color="gray")
        self.lbl_subtitle.pack()
        
        # --- TWO-COLUMN CONTAINER ---
        self.columns_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.columns_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        # LEFT COLUMN: Server Controls
        self.left_column = ctk.CTkFrame(self.columns_frame, fg_color="transparent")
        self.left_column.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        # Status Display
        self.status_frame = ctk.CTkFrame(self.left_column, border_color="gray", border_width=1)
        self.status_frame.pack(fill="x", pady=(0, 10))
        
        self.status_label = ctk.CTkLabel(self.status_frame, text="OFFLINE", text_color="#F44336", font=("Roboto", 20, "bold"))
        self.status_label.pack(pady=(15, 5))
        
        self.info_label = ctk.CTkLabel(self.status_frame, text=f"Port: {self.SERVER_PORT} | PID: -- | Uptime: 0s", font=("Segoe UI", 11))
        self.info_label.pack(pady=(0, 15))
        
        # Button Controls
        self.btn_frame = ctk.CTkFrame(self.left_column, fg_color="transparent")
        self.btn_frame.pack(pady=(0, 10))
        
        self.btn_start = ctk.CTkButton(self.btn_frame, text="START", command=self.start_server, 
                                       fg_color="#4CAF50", hover_color="#388E3C", width=110, height=40, font=("Roboto", 12, "bold"))
        self.btn_start.pack(side="left", padx=5)
        
        self.btn_stop = ctk.CTkButton(self.btn_frame, text="STOP", command=self.stop_server, 
                                      fg_color="#F44336", hover_color="#D32F2F", width=110, height=40, font=("Roboto", 12, "bold"), state="disabled")
        self.btn_stop.pack(side="left", padx=5)
        
        # Quick Actions
        self.btn_open = ctk.CTkButton(self.left_column, text="Open Web Interface ↗", 
                                      command=self.open_web_interface, 
                                      fg_color="transparent", border_width=1, border_color="gray", text_color="white", height=35)
        self.btn_open.pack(fill="x", pady=3)
        
        self.btn_admin = ctk.CTkButton(self.left_column, text="Open Admin Dashboard ↗", 
                                       command=self.open_admin_dashboard, 
                                       fg_color="transparent", border_width=1, border_color="gray", text_color="white", height=35)
        self.btn_admin.pack(fill="x", pady=3)
        
        self.btn_restart = ctk.CTkButton(self.left_column, text="Emergency Restart", command=self.restart_server, 
                                         fg_color="transparent", text_color="orange", hover=False, height=35, font=("Segoe UI", 11))
        self.btn_restart.pack(fill="x", pady=3)

        # RIGHT COLUMN: Knowledge Base
        self.right_column = ctk.CTkFrame(self.columns_frame, fg_color="transparent")
        self.right_column.pack(side="right", fill="both", expand=True, padx=(10, 0))
        
        self.ingest_frame = ctk.CTkFrame(self.right_column, border_color="gray", border_width=1)
        self.ingest_frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(self.ingest_frame, text="KNOWLEDGE BASE", font=("Roboto", 12, "bold")).pack(pady=(15, 10))
        
        self.btn_ingest_folder = ctk.CTkButton(self.ingest_frame, text="ADD FOLDER TO KNOWLEDGE BASE", command=self.start_ingestion,
                                    fg_color="#4C1D95", hover_color="#5B21B6", height=50, font=("Roboto", 11, "bold"))
        self.btn_ingest_folder.pack(pady=(0, 10), padx=20, fill="x")
        
        self.btn_ingest_file = ctk.CTkButton(self.ingest_frame, text="ADD FILE TO KNOWLEDGE BASE", command=self.start_single_file_ingestion,
                                    fg_color="#6D28D9", hover_color="#7C3AED", height=45, font=("Roboto", 11, "bold"))
        self.btn_ingest_file.pack(pady=(0, 15), padx=20, fill="x")

        # --- SYSTEM LOGS ---
        ctk.CTkLabel(self, text="System Console:", font=("Roboto", 12, "bold")).pack(anchor="w", padx=25, pady=(10, 5))
        
        # Single Log Area
        self.log_area = ctk.CTkTextbox(self, font=("Consolas", 11), text_color="#E0E0E0", state="disabled")
        self.log_area.pack(pady=(0, 20), padx=20, fill="both", expand=True)
        
        # Configure color tags
        self.log_area.tag_config("success", foreground="#4CAF50")  # Green
        self.log_area.tag_config("error", foreground="#F44336")    # Red
        self.log_area.tag_config("warning", foreground="#FFA726")  # Orange
        self.log_area.tag_config("info", foreground="#42A5F5")     # Blue

        # Cycle Loops
        self.after(self.UPDATE_INTERVAL_MS, self.update_status)
        # Run cleanup in background thread to avoid startup lag
        threading.Thread(target=self.autoclean_zombies, daemon=True).start()
        
        # Register cleanup on window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def autoclean_zombies(self):
        """Automatically kills any process holding port 8000 on startup."""
        try:
            if os.name == 'nt':
                cmd = f'netstat -ano | findstr :{self.SERVER_PORT}'
                output = subprocess.check_output(cmd, shell=True).decode()
                if output:
                    self.log(f"[Auto-Cleanup] Scanning Port {self.SERVER_PORT}...")
                    lines = output.strip().split('\n')
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 5:  # Ensure netstat output has expected format
                            pid = parts[-1] 
                            if pid.isdigit() and int(pid) > 0:
                                self.log(f"[Auto-Cleanup] Killing Ghost PID: {pid}")
                                subprocess.run(f"taskkill /F /PID {pid}", shell=True, 
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.log(f"[System] Ready. Port {self.SERVER_PORT} is clean.")
        except subprocess.CalledProcessError:
            # No process found on port - this is fine
            self.log("[System] Ready (No previous instance found).")
        except Exception as e:
            self.log(f"[System] Ready (Cleanup check failed: {e})")

    def log(self, message):
        """Log a message safely from any thread."""
        self.after(0, lambda: self._log_ui(message))

    def _log_ui(self, message):
        """Actual UI update running on main thread."""
        self.log_area.configure(state="normal")
        
        # Detect message type and assign color tag (CHECK ERRORS FIRST!)
        tag = None
        lower_msg = message.lower()
        
        # Priority 1: Errors (must be checked first!)
        if any(keyword in lower_msg for keyword in ['error', '[failed]', '[x]', 'critical', 'crash', 'errno']):
            tag = "error"
        # Priority 2: Warnings
        elif any(keyword in lower_msg for keyword in ['[warning]', '[debug]', '⚠', 'failed to']):
            tag = "warning"
        # Priority 3: Success
        elif any(keyword in lower_msg for keyword in ['[ok]', '[skip]', 'complete', '✓', 'success']):
            tag = "success"
        # Priority 4: Info
        elif any(keyword in lower_msg for keyword in ['[system]', '[ingest]', 'starting', '[auto-cleanup]', 'ready']):
            tag = "info"
        
        # Insert with color tag
        if tag:
            self.log_area.insert("end", message + "\n", tag)
        else:
            self.log_area.insert("end", message + "\n")
        
        self.log_area.see("end")
        self.log_area.configure(state="disabled")
    
    def _parse_json_summary(self, line):
        """Extract and parse JSON_SUMMARY from log line."""
        try:
            json_str = line.split("JSON_SUMMARY:")[1].strip()
            return json.loads(json_str)
        except Exception as e:
            self.log(f"[ERROR] JSON Parse Failed: {e}")
            return None

    def _should_show_log(self, line):
        """Filter out verbose HTTP logs and debug JSON output."""
        # Hide uvicorn HTTP request logs
        if 'INFO:' in line and ('"GET' in line or '"POST' in line or '"PUT' in line or '"DELETE' in line):
            return False
        # Hide raw JSON debug output
        if line.startswith('{') or line.startswith('"') or line.startswith('['):
            return False
        # Hide DEBUG: Generating/Payload messages
        if 'DEBUG: Generating' in line or 'DEBUG: Payload' in line:
            return False
        # Hide favicon 404s
        if 'favicon.ico' in line and '404' in line:
            return False
        return True

    def run_server_process(self):
        # Using -u for unbuffered output is CRITICAL for live logs
        python_exe = sys.executable.replace("pythonw.exe", "python.exe")
        
        cmd = [python_exe, "-u", "-m", "uvicorn", "app.main:app", "--port", str(self.SERVER_PORT), "--log-level", "info"]
        
        try:
            # Use local variable for thread safety
            proc = subprocess.Popen(
                cmd, 
                cwd=str(PROJECT_ROOT),  # Always run from project root
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            self.process = proc
            self.start_time = time.time()
            
            # Read stdout in a loop
            while self.process and proc.poll() is None:
                # Use 'proc' (local) to read, but check 'self.process' (global) to know if we should stop
                line = proc.stdout.readline()
                if line:
                    stripped = line.strip()
                    # Filter out verbose HTTP logs and debug JSON
                    if self._should_show_log(stripped):
                        self.log(stripped)
            
            if self.process and proc.returncode != 0:
                err = proc.stderr.read()
                # Check if it's a port-in-use error
                if 'Errno 10048' in err or 'address already in use' in err.lower():
                    self.log(f"[ERROR] Port {self.SERVER_PORT} is already in use!")
                    self.log("[System] Attempting to clean up zombie process...")
                    self.autoclean_zombies()
                    self.log("[System] Please try starting the server again.")
                else:
                    self.log(f"[ERROR] {err}")
                
        except Exception as e:
            self.log(f"[ERROR] Failed to launch: {e}")

    def start_server(self):
        if self.process: return
        self.btn_start.configure(state="disabled", fg_color="gray")
        self.btn_stop.configure(state="normal", fg_color="#F44336")
        self.status_label.configure(text="STARTING...", text_color="orange")
        
        threading.Thread(target=self.run_server_process, daemon=True).start()

    def stop_server(self):
        if self.process:
            try:
                # Force Kill Tree
                subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], 
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (subprocess.SubprocessError, OSError) as e:
                self.log(f"[WARNING] Failed to kill process {self.process.pid}: {e}")
            self.process = None
            self.start_time = None
            self.log("[System] STOPPED.")
        
        # Aggressive Zombie Cleanup (in background)
        self.log("[System] Ensuring Clean Shutdown...")
        threading.Thread(target=self.autoclean_zombies, daemon=True).start()
            
        self.btn_start.configure(state="normal", fg_color="#4CAF50")
        self.btn_stop.configure(state="disabled", fg_color="gray")
        self.status_label.configure(text="OFFLINE", text_color="#F44336")
        self.info_label.configure(text=f"Port: {self.SERVER_PORT} | PID: -- | Uptime: 0s")

    def restart_server(self):
        self.stop_server()
        # Use non-blocking after() instead of blocking sleep()
        self.after(self.UPDATE_INTERVAL_MS, self.start_server)

    def update_status(self):
        if self.process:
            if self.process.poll() is not None:
                self.stop_server()
                self.status_label.configure(text="CRASHED", text_color="red")
            else:
                uptime = int(time.time() - self.start_time)
                self.status_label.configure(text="ONLINE", text_color="#4CAF50")
                self.info_label.configure(text=f"Port: {self.SERVER_PORT} | PID: {self.process.pid} | Uptime: {uptime}s")
        self.after(self.UPDATE_INTERVAL_MS, self.update_status)
    
    def on_closing(self):
        """Clean up subprocess before closing application."""
        if self.process:
            self.stop_server()
        self.destroy()

    def start_ingestion(self):
        self.btn_ingest_folder.configure(state="disabled", text="RUNNING...")
        self.btn_ingest_file.configure(state="disabled")
        self.log("-" * 30)
        self.log(f"[Ingest] Starting Folder Update...")
        threading.Thread(target=self._run_ingest_process, daemon=True).start()
    
    def start_single_file_ingestion(self):
        """Open file picker and ingest single file."""
        from tkinter import filedialog
        
        file_path = filedialog.askopenfilename(
            title="Select file to add to Knowledge Base",
            initialdir=str(PROJECT_ROOT / "data" / "kb_documents"),
            filetypes=[
                ("PDF files", "*.pdf"),
                ("Text files", "*.txt"),
                ("Markdown files", "*.md"),
                ("Word files", "*.docx"),
                ("All supported files", "*.pdf *.txt *.md *.docx"),
            ]
        )
        
        if not file_path:
            return  # User cancelled
        
        self.btn_ingest_file.configure(state="disabled", text="PROCESSING...")
        self.btn_ingest_folder.configure(state="disabled")
        self.log("-" * 30)
        self.log(f"[Ingest] Adding single file: {os.path.basename(file_path)}")
        threading.Thread(target=self._run_single_file_ingest, args=(file_path,), daemon=True).start()


    def _run_ingest_process(self):
        python_exe = sys.executable.replace("pythonw.exe", "python.exe")
        cmd = [python_exe, "-u", "scripts/ingest.py"]
        
        # Track metrics for summary
        start_time = time.time()
        processed_count = 0
        skipped_count = 0
        error_count = 0
        
        try:
            process = subprocess.Popen(
                cmd, 
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            ) 
            
            # Read stdout line by line in real-time
            while process.poll() is None:
                line = process.stdout.readline()  # ← THIS WAS MISSING!
                if line:
                    clean_line = line.strip()
                    self.log(clean_line)
                    
                    # Track metrics from log messages (fallback)
                    if '[SKIP]' in clean_line or 'Skipping' in clean_line:
                        skipped_count += 1
                    elif '[OK]' in clean_line or 'Processing' in clean_line:
                        processed_count += 1
                    elif '[X]' in clean_line or '[ERROR]' in clean_line or 'Error' in clean_line:
                        error_count += 1
                    
                    # Check for JSON Summary (Primary Source)
                    if "JSON_SUMMARY:" in clean_line:
                        stats = self._parse_json_summary(clean_line)
                        if stats:
                            processed_count = stats.get("processed", processed_count)
                            skipped_count = stats.get("skipped", skipped_count)
                            error_count = stats.get("errors", error_count)
                            self.log(f"[System] Stats updated from JSON: {stats}")
            
            # Read any remaining output
            out, err = process.communicate()
            if out: 
                for line in out.strip().split('\n'):
                    if line:
                        clean_line = line.strip()
                        self.log(clean_line)
                        
                        # Final JSON summary check
                        if "JSON_SUMMARY:" in clean_line:
                            stats = self._parse_json_summary(clean_line)
                            if stats:
                                # Override with final stats
                                processed_count = stats.get("processed", processed_count)
                                skipped_count = stats.get("skipped", skipped_count)
                                error_count = stats.get("errors", error_count)
                                self.log(f"[System] Final stats from JSON: {stats}")

            if err: 
                self.log(f"[ERROR] {err.strip()}")
            
            # Calculate duration
            duration = time.time() - start_time
            duration_str = f"{int(duration // 60)}m {int(duration % 60)}s" if duration > 60 else f"{int(duration)}s"
            
            # Display summary card
            self.log("")
            self.log("━" * 40)
            self.log("📊 INGESTION SUMMARY")
            self.log("━" * 40)
            self.log(f"✓ Processed:  {processed_count} files")
            self.log(f"✓ Skipped:    {skipped_count} files (unchanged)")
            self.log(f"✓ Duration:   {duration_str}")
            self.log(f"{'⚠' if error_count > 0 else '✓'} Errors:     {error_count}")
            self.log("━" * 40)
                
        except Exception as e:
            self.log(f"[ERROR] Ingest Failed: {e}")
            
        self.btn_ingest_folder.configure(state="normal", text="ADD FOLDER TO KNOWLEDGE BASE")
        self.btn_ingest_file.configure(state="normal")
        self.log("-" * 30)
    
    def _run_single_file_ingest(self, file_path: str):
        """Run single file ingestion process."""
        python_exe = sys.executable.replace("pythonw.exe", "python.exe")
        cmd = [python_exe, "-u", "scripts/ingest_single_file.py", file_path]
        
        start_time = time.time()
        
        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Read stdout in real-time
            while process.poll() is None:
                line = process.stdout.readline()
                if line:
                    self.log(line.strip())
            
            # Read remaining output
            out, err = process.communicate()
            if out:
                for line in out.strip().split('\n'):
                    if line:
                        self.log(line.strip())
            if err:
                self.log(f"[ERROR] {err.strip()}")
            
            duration = int(time.time() - start_time)
            duration_str = f"{int(duration // 60)}m {int(duration % 60)}s" if duration > 60 else f"{duration}s"
            
            self.log("")
            self.log("━" * 40)
            self.log("✓ FILE UPLOAD COMPLETE")
            self.log(f"✓ Duration: {duration_str}")
            self.log("━" * 40)
            
        except Exception as e:
            self.log(f"[ERROR] Single file ingest failed: {e}")
        
        self.btn_ingest_file.configure(state="normal", text="ADD FILE TO KNOWLEDGE BASE")
        self.btn_ingest_folder.configure(state="normal")
        self.log("-" * 30)
    
    def open_web_interface(self):
        """Open web interface in background thread to avoid UI freeze"""
        threading.Thread(target=lambda: webbrowser.open(f"http://127.0.0.1:{self.SERVER_PORT}"), daemon=True).start()
    
    def open_admin_dashboard(self):
        """Open admin dashboard in background thread to avoid UI freeze"""
        threading.Thread(target=lambda: webbrowser.open(f"http://127.0.0.1:{self.SERVER_PORT}/admin"), daemon=True).start()



if __name__ == "__main__":
    app = BotManager()
    app.mainloop()

