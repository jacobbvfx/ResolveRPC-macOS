import time
import sys
import psutil

# Add Resolve API path if needed
resolve_path = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
if resolve_path not in sys.path:
    sys.path.append(resolve_path)

import DaVinciResolveScript as dvr
from pypresence import Presence

# Discord Application ID (Create a Discord App: https://discord.com/developers/applications)
DISCORD_CLIENT_ID = "1004088618857549844"

def is_process_running(process_name):
    for proc in psutil.process_iter(['pid', 'name']):
        if process_name.lower() in proc.info['name'].lower():
            return True
    return False

def wait_for_process(process_name):
    print(f"Waiting for {process_name} to start...")
    while not is_process_running(process_name):
        time.sleep(5)
    print(f"{process_name} has started.")

def get_resolve():
    wait_for_process("resolve")
    while True:
        try:
            resolve = dvr.scriptapp("Resolve")
            if resolve:
                return resolve
        except:
            print("Could not connect to DaVinci Resolve. Retrying...")
            time.sleep(5)

def get_project_info(resolve):
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject()
    if not project:
        return None, None, None
    project_name = project.GetName()
    timeline = project.GetCurrentTimeline()
    timeline_name = timeline.GetName() if timeline else None
    return project, project_name, timeline_name

def update_presence(rpc, resolve):
    start_time = int(time.time())
    while True:
        if not is_process_running("discord"):
            print("Discord is not running.")
            rpc.clear()
            wait_for_process("discord")
            rpc.connect()

        if not is_process_running("resolve"):
            print("DaVinci Resolve is not running.")
            rpc.clear()
            wait_for_process("resolve")
            resolve = get_resolve()

        try:
            project, project_name, timeline_name = get_project_info(resolve)
        except AttributeError:
            print("Failed to get project info. Retrying...")
            resolve = get_resolve()
            continue

        if not project:
            rpc.clear()
            print("No active project. Waiting...")
            time.sleep(10)
            continue

        if timeline_name:
            state = f"Editing: {timeline_name}"
            details = f"Project: {project_name}"
        else:
            state = "Editing: No active Timeline"
            details = "In: Project Manager"

        rpc.update(
            state=state,
            details=details,
            start=start_time,
            large_image="davinci",  # You can upload an image to your Discord app
            large_text="DaVinci Resolve Studio"
        )
        print(f"Updated presence: {state} {details}")
        time.sleep(15)  # Update every 15 seconds

if __name__ == "__main__":
    resolve = get_resolve()
    rpc = Presence(DISCORD_CLIENT_ID)
    rpc.connect()
    
    try:
        update_presence(rpc, resolve)
    except KeyboardInterrupt:
        print("Stopping Rich Presence...")
        rpc.clear()
        rpc.close()
