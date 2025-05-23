import time
import sys
import psutil
import rumps  # For macOS menu bar app
import threading  # For background tasks

# Add Resolve API path if needed
resolve_path = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
if resolve_path not in sys.path:
    sys.path.append(resolve_path)

import DaVinciResolveScript as dvr
from pypresence import Presence  # Ensure this is installed: pip3 install pypresence

# Discord Application ID
DISCORD_CLIENT_ID = "1004088618857549844"

# --- Helper Functions ---
def is_process_running(process_name):
    for proc in psutil.process_iter(['pid', 'name']):
        if process_name.lower() in proc.info['name'].lower():
            return True
    return False

def _wait_for_process_blocking(process_name, status_callback=None, app_running_flag=None):
    """
    Waits for a process to start.
    status_callback: Function to update GUI status.
    app_running_flag: threading.Event or similar to check if app should still be running.
    Returns True if process started, False if waiting was interrupted by app_running_flag.
    """
    if status_callback:
        status_callback(f"Waiting for {process_name}...")
    print(f"Waiting for {process_name} to start...")
    while not is_process_running(process_name):
        if app_running_flag and not app_running_flag.is_set(): # Check if we should stop waiting
            print(f"Stopped waiting for {process_name} as application is shutting down.")
            return False
        time.sleep(5)
    if status_callback:
        status_callback(f"{process_name} started.")
    print(f"{process_name} has started.")
    return True

def get_resolve_connection(status_callback=None, app_running_flag=None):
    """
    Connects to DaVinci Resolve, waiting if necessary.
    Returns resolve object or None if connection fails or interrupted.
    """
    if not _wait_for_process_blocking("resolve", status_callback, app_running_flag):
        return None # Waiting was interrupted

    while app_running_flag is None or app_running_flag.is_set():
        try:
            resolve = dvr.scriptapp("Resolve")
            if resolve:
                if status_callback:
                    status_callback("Resolve: Connected.")
                print("Connected to DaVinci Resolve.")
                return resolve
        except Exception as e:
            msg = f"Resolve: Connection failed: {str(e)[:50]}. Retrying..."
            if status_callback:
                status_callback(msg)
            print(msg)
            # Check flag before sleeping
            for _ in range(5): # Sleep for 5 seconds, but check flag every second
                if app_running_flag and not app_running_flag.is_set():
                    return None
                time.sleep(1)
        if app_running_flag and not app_running_flag.is_set():
            break # Exit loop if app is shutting down
    return None


def get_project_info(resolve_api_object):
    if not resolve_api_object:
        # This case should ideally be caught before calling get_project_info
        # by checking self.resolve in the main loop.
        return None, None, None
    try:
        project_manager = resolve_api_object.GetProjectManager()
        if not project_manager:
            # If GetProjectManager returns None, the connection is likely stale or Resolve is not ready.
            raise ConnectionError("GetProjectManager() returned None, connection likely stale.")

        project = project_manager.GetCurrentProject()
        if not project:
            # This is a valid state: Resolve is open, but no project is currently open.
            return None, None, None

        project_name = project.GetName()
        # If a project object exists, its name should ideally not be None.
        if project_name is None:
            raise ConnectionError(f"project.GetName() returned None for an existing project object.")

        timeline = project.GetCurrentTimeline()
        timeline_name = timeline.GetName() if timeline else None
        return project, project_name, timeline_name
    except Exception as e:
        # Wrap other potential API errors in ConnectionError if they are not already.
        if isinstance(e, ConnectionError):
            raise  # Re-raise if it's already the type we want
        # This will catch other errors if resolve_api_object is stale or calls fail
        # print(f"get_project_info: Exception during Resolve API call: {type(e).__name__} - {e}")
        raise ConnectionError(f"Resolve API call failed within get_project_info: {type(e).__name__} - {e}") from e


class ResolveApp(rumps.App):
    def __init__(self):
        super(ResolveApp, self).__init__("DRPC", quit_button=None)  # Short name for menu bar
        self.icon = "topicon.png"  # Set the menu bar icon
        
        self.short_status_menu_item = rumps.MenuItem("DRPC...") # For the icon-like status
        self.detailed_status_menu_item = rumps.MenuItem("Status: Initializing...") # For detailed messages
        
        self.menu = [
            self.short_status_menu_item,
            self.detailed_status_menu_item,
            None,  # Separator
            rumps.MenuItem("Reconnect to Discord", callback=self.reconnect_discord_manually),
            rumps.MenuItem("Reconnect to Resolve", callback=self.reconnect_resolve_manually),
            None,
            rumps.MenuItem("Quit ResolveRPC", callback=self.quit_app_action)
        ]
        self.rpc = None
        self.resolve = None
        self.discord_client_id = DISCORD_CLIENT_ID
        
        self._app_running_flag = threading.Event() # Used to signal background thread to stop
        self._app_running_flag.set() # Set the flag to True initially

        self.start_time = int(time.time())
        self.resolve_connected = False
        self.discord_connected = False

        self.main_thread = threading.Thread(target=self._main_loop_thread, daemon=True)
        self.main_thread.start()

    def update_menu_status(self, message):
        # Update the detailed status message
        self.detailed_status_menu_item.title = f"Status: {message}"

        # Determine and update the short status for the menu
        short_status = "DRPC..." # Default short status

        if not self.resolve_connected and not self.discord_connected:
            short_status = "DRPC (Offline)"
        elif not self.resolve_connected:
            short_status = "DRPC (No Resolve)"
        elif not self.discord_connected:
            short_status = "DRPC (No Discord)"
        elif "No active project" in message or "(Manager)" in message or "No Project" in message:
            short_status = "DRPC (Idle)"
        elif "Initializing" in message or "Connecting" in message or "Waiting" in message:
            short_status = "DRPC..."
        elif self.resolve_connected and self.discord_connected:
            # Check if we are actively editing or just in manager
            if "Project:" in message and ("Timeline" in message or "Editing:" in message):
                 short_status = "DRPC ✓ (Active)"
            elif "Project:" in message and "(Manager)" in message:
                 short_status = "DRPC ✓ (Project Manager)"
            elif "No active project" in message:
                 short_status = "DRPC ✓ (Idle)"
            else: # General connected state
                 short_status = "DRPC ✓"


        self.short_status_menu_item.title = short_status
        # self.title remains None or empty to keep only icon in menu bar

    def _connect_discord(self):
        if not self._app_running_flag.is_set(): return False
        self.update_menu_status("Discord: Connecting...")
        if not is_process_running("discord"):
            self.update_menu_status("Discord: Not running. Waiting...")
            if not _wait_for_process_blocking("discord", self.update_menu_status, self._app_running_flag):
                return False # Interrupted
        
        if not self._app_running_flag.is_set(): return False

        try:
            if self.rpc:
                try: self.rpc.close()
                except Exception: pass
            self.rpc = Presence(self.discord_client_id)
            self.rpc.connect()
            self.discord_connected = True
            self.update_menu_status("Discord: Connected")
            print("Connected to Discord.")
            return True
        except Exception as e:
            self.discord_connected = False
            error_msg = f"Discord: Connection failed: {str(e)[:50]}..."
            self.update_menu_status(error_msg)
            print(f"Could not connect to Discord: {e}")
            return False

    def _connect_resolve(self):
        if not self._app_running_flag.is_set(): return False
        self.update_menu_status("Resolve: Connecting...")
        # Pass the app_running_flag to get_resolve_connection
        self.resolve = get_resolve_connection(self.update_menu_status, self._app_running_flag)
        if self.resolve:
            self.resolve_connected = True
            self.start_time = int(time.time())
            # Status already updated by get_resolve_connection
            return True
        else:
            # If get_resolve_connection returns None, it might be due to shutdown or persistent failure
            self.resolve_connected = False
            if self._app_running_flag.is_set(): # Only update status if not shutting down
                 self.update_menu_status("Resolve: Connection failed.")
            return False

    def reconnect_discord_manually(self, _):
        if not self.discord_connected:
            threading.Thread(target=self._connect_discord, daemon=True).start()
        else:
            self.update_menu_status("Discord: Already connected.")


    def reconnect_resolve_manually(self, _):
        if not self.resolve_connected:
            threading.Thread(target=self._connect_resolve, daemon=True).start()
        else:
            self.update_menu_status("Resolve: Already connected.")


    def _main_loop_thread(self):
        # Initial connections
        if self._app_running_flag.is_set(): self._connect_resolve()
        if self._app_running_flag.is_set(): self._connect_discord()

        while self._app_running_flag.is_set():
            try:
                # 1. Check Discord Process & Connection
                if not is_process_running("discord"):
                    if self.discord_connected:
                        print("Discord process not found. Clearing presence.")
                        if self.rpc:
                            try:
                                self.rpc.clear()
                            except Exception:
                                pass
                    self.discord_connected = False
                    self.update_menu_status("Discord: Not running. Waiting...")
                    if not _wait_for_process_blocking("discord", self.update_menu_status, self._app_running_flag): break
                    if self._app_running_flag.is_set(): self._connect_discord()
                    continue
                elif not self.discord_connected:
                    self.update_menu_status("Discord: Disconnected. Reconnecting...")
                    if self._app_running_flag.is_set(): self._connect_discord()
                    if not self.discord_connected: time.sleep(10); continue

                # 2. Check Resolve Process & Connection
                if not is_process_running("resolve"):
                    if self.resolve_connected:
                        print("Resolve process not found. Clearing presence.")
                        if self.rpc and self.discord_connected:
                            try:
                                self.rpc.clear()
                            except Exception:
                                pass
                    self.resolve_connected = False
                    self.resolve = None # Explicitly set to None
                    self.update_menu_status("Resolve: Not running. Waiting...")
                    if not _wait_for_process_blocking("resolve", self.update_menu_status, self._app_running_flag): break
                    if self._app_running_flag.is_set(): self._connect_resolve()
                    continue
                # If Resolve process is running, but we're not connected (or self.resolve is None)
                elif not self.resolve_connected or self.resolve is None:
                    self.update_menu_status("Resolve: Disconnected. Reconnecting...")
                    if self._app_running_flag.is_set(): self._connect_resolve()
                    # If still not connected after attempt, wait and retry loop
                    if not self.resolve_connected: time.sleep(10); continue

                # 3. Get Project Info
                project, project_name, timeline_name = None, None, None
                try:
                    # At this point, self.resolve should be a non-None object if self.resolve_connected is True
                    project, project_name, timeline_name = get_project_info(self.resolve)
                except ConnectionError as e:
                    # This catches errors from get_project_info indicating the Resolve connection is bad/stale
                    self.update_menu_status(f"Resolve: API Error. Reconnecting.")
                    print(f"Resolve API connection error: {e}. Marking for full reconnect.")
                    self.resolve_connected = False # CRITICAL: Mark connection as bad
                    self.resolve = None            # CRITICAL: Clear the stale object
                    if self.rpc and self.discord_connected:
                        try:
                            self.rpc.clear()
                        except Exception as rpc_e:
                            print(f"Error clearing RPC: {rpc_e}")
                    # No long sleep here, loop will continue and attempt to reconnect Resolve due to resolve_connected being False
                    continue

                # 4. Handle Project Info Results & Update RPC
                # project_name being None also covers GetName() returning None if get_project_info didn't raise ConnectionError for it
                if not project or project_name is None:
                    if self.rpc and self.discord_connected:
                        try:
                            self.rpc.clear()
                        except Exception as rpc_e:
                            print(f"Error clearing RPC (no project/name): {rpc_e}")

                    current_error_status = "Resolve: No active project."
                    # This specific check is if get_project_info returned a project object but GetName() failed
                    # and was handled by get_project_info returning project_name as None instead of raising error.
                    # However, the modified get_project_info now raises ConnectionError for this.
                    if project and project_name is None:
                        current_error_status = "Resolve: Error reading project name."

                    self.update_menu_status(current_error_status)
                    print(f"{current_error_status} (Waiting 30s before retry if Resolve still running).")

                    for _ in range(30): # Sleep for 30 seconds
                        if not self._app_running_flag.is_set(): break
                        time.sleep(1)
                    if not self._app_running_flag.is_set(): break # Exit main loop if app is shutting down
                    
                    # After the wait, just continue. The main loop will re-evaluate everything,
                    # including Resolve process status and connection.
                    continue

                else: # Valid project and project_name
                    if timeline_name:
                        state = f"Editing: {timeline_name}"
                        details = f"Project: {project_name}"
                        menu_bar_status_detail = f"{project_name} - {timeline_name}"
                    else:
                        state = "Editing: No active Timeline"
                        details = f"Project: {project_name} (Manager)"
                        menu_bar_status_detail = f"{project_name} (Manager)"
                    self.update_menu_status(menu_bar_status_detail)

                    try:
                        if self.rpc and self.discord_connected:
                            self.rpc.update(
                                state=state, details=details, start=self.start_time,
                                large_image="davinci", large_text="DaVinci Resolve Studio"
                            )
                    except Exception as e:
                        self.discord_connected = False
                        error_msg = f"Discord: Update failed: {str(e)[:30]}..."
                        self.update_menu_status(error_msg)
                        print(f"Failed to update Discord presence: {e}")
                        # Reconnect attempt for Discord will happen at the start of the next loop.

                # 5. Loop Sleep
                for _ in range(15):
                    if not self._app_running_flag.is_set(): break
                    time.sleep(1)

            except Exception as e: # General catch-all for unexpected errors in the loop
                if not self._app_running_flag.is_set(): break
                error_msg = f"Main loop error: {type(e).__name__} - {str(e)[:100]}..." # Increased length
                self.update_menu_status(error_msg)
                print(f"An error occurred in the main loop: {e}")
                if self.rpc and self.discord_connected:
                    try:
                        self.rpc.clear()
                    except Exception as rpc_e:
                        print(f"Error clearing RPC on main loop error: {rpc_e}")
                time.sleep(10)

        print("Main loop thread finished.")


    def quit_app_action(self, _=None): # Can be called by menu item or programmatically
        print("Quit action initiated. Shutting down...")
        self.update_menu_status("Shutting down...")
        self._app_running_flag.clear()  # Signal the main loop to stop

        if self.main_thread.is_alive():
            print("Waiting for main thread to exit...")
            self.main_thread.join(timeout=7.0) # Increased timeout
            if self.main_thread.is_alive():
                print("Main thread did not exit in time.")
        
        if self.rpc:
            try:
                self.rpc.clear()
                self.rpc.close()
                print("Discord RPC cleared and closed.")
            except Exception as e:
                print(f"Error closing Discord RPC: {e}")
        
        rumps.quit_application()

if __name__ == "__main__":
    print("Starting Resolve Rich Presence for macOS...")
    print("Ensure DaVinci Resolve's 'External scripting' is set to 'Local' in Preferences > System > General.")
    print("You might need to install 'rumps': pip3 install rumps")
    
    # Check if another instance is already running (simple check, not foolproof)
    # For a more robust check, you might use a lock file or check process names more specifically.
    app_name = "ResolveRPC" 
    # A more specific check could be `if len([p for p in psutil.process_iter(['name', 'cmdline']) if app_name in p.info['name']]) > 1:`
    # but this is complex due to Python interpreter names. For now, we'll skip this.

    app = ResolveApp()
    try:
        app.run()
    except Exception as e:
        print(f"Unhandled exception in rumps app: {e}")
    finally:
        print("ResolveRPC application has exited.")