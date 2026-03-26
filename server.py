import os
import sys
import time
import json
import uuid
import threading
from typing import List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path

# Ensure gelab-zero is in the path
if "." not in sys.path:
    sys.path.append(".")

from copilot_agent_client.pu_client import evaluate_task_on_device
from copilot_front_end.mobile_action_helper import list_devices, get_device_wm_size
from copilot_agent_server.local_server import LocalServer
from copilot_agent_server.local_server_logger import LocalServerLogger

app = FastAPI(title="gelab-zero Web UI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
LOG_DIR = Path("running_log/server_log/os-copilot-local-eval-logs/traces")
IMAGE_DIR = Path("running_log/server_log/os-copilot-local-eval-logs/images")

SERVER_CONFIG = {
    "log_dir": str(LOG_DIR),
    "image_dir": str(IMAGE_DIR),
    "debug": False
}

MODEL_CONFIG = {
    "task_type": "parser_0922_summary",
    "model_config": {
        "model_name": "gelab-zero-4b-preview",
        "model_provider": "local",
        "args": {
            "temperature": 0.1,
            "top_p": 0.95,
            "frequency_penalty": 0.0,
            "max_tokens": 4096,
        },
    },
    "max_steps": 400,
    "delay_after_capture": 2,
    "debug": False
}

# Global state for current running task
current_task = {
    "session_id": None,
    "status": "idle",
    "task_name": None,
    "error": None,
    "start_time": None
}

stop_event = threading.Event()

class TaskRequest(BaseModel):
    task: str

@app.get("/api/sessions")
def list_sessions():
    sessions = []
    if not LOG_DIR.exists():
        return sessions
    
    for log_file in LOG_DIR.glob("*.jsonl"):
        session_id = log_file.stem
        # Read the first line of the log file to get task info
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                first_line = f.readline()
                if first_line:
                    log_entry = json.loads(first_line)
                    msg = log_entry.get("message", {})
                    sessions.append({
                        "session_id": session_id,
                        "task": msg.get("task", "Unknown"),
                        "timestamp": log_entry.get("timestamp"),
                        "status": "completed" # For historical logs
                    })
        except Exception as e:
            print(f"Error reading {log_file}: {e}")
            
    # Sort by timestamp descending
    sessions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return sessions

@app.get("/api/sessions/{session_id}")
def get_session_details(session_id: str):
    logger = LocalServerLogger({
        "log_dir": str(LOG_DIR),
        "image_dir": str(IMAGE_DIR),
        "session_id": session_id
    })
    logs = logger.read_logs()
    if not logs:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Clean up logs for frontend (e.g., convert image paths to served URLs)
    cleaned_logs = []
    for log in logs:
        msg = log.get("message", {})
        if "environment" in msg and "image" in msg["environment"]:
            image_path = msg["environment"]["image"]
            try:
                rel_path = Path(image_path).name
                msg["environment"]["image_url"] = f"/api/images/{rel_path}"
            except:
                pass
        if "after_image" in msg:
            after_image_path = msg["after_image"]
            try:
                after_rel_path = Path(after_image_path).name
                msg["after_image_url"] = f"/api/images/{after_rel_path}"
            except:
                pass
        cleaned_logs.append(log)
        
    return cleaned_logs

@app.post("/api/execute")
def execute_task(request: TaskRequest, background_tasks: BackgroundTasks):
    global current_task
    
    if current_task["status"] == "running":
        raise HTTPException(status_code=400, detail="A task is already running")

    # Initialize current task state
    session_id = str(uuid.uuid4())
    current_task = {
        "session_id": session_id,
        "status": "running",
        "task_name": request.task,
        "error": None,
        "start_time": time.time()
    }

    stop_event.clear() # Reset stop event
    background_tasks.add_task(run_task_background, request.task, session_id)
    return {"session_id": session_id, "status": "started"}

@app.post("/api/stop")
def stop_task():
    global current_task
    if current_task["status"] == "running":
        stop_event.set()
        return {"status": "stopping"}
    return {"status": "not running"}

@app.get("/api/status")
def get_status():
    return current_task

@app.get("/api/images/{filename}")
def get_image(filename: str):
    image_path = IMAGE_DIR / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    from fastapi.responses import FileResponse
    return FileResponse(image_path)

def run_task_background(task_str: str, session_id: str):
    global current_task
    try:
        # Prepare device info
        devices = list_devices()
        if not devices:
            current_task["status"] = "failed"
            current_task["error"] = "No devices connected"
            return
        
        device_id = devices[0]
        device_wm_size = get_device_wm_size(device_id)
        device_info = {
            "device_id": device_id,
            "device_wm_size": device_wm_size
        }

        # Setup server
        l2_server = LocalServer(SERVER_CONFIG)
        
        # Monkeypatch get_session to use our pre-generated session_id
        original_get_session = l2_server.get_session
        def forced_get_session(payload):
            # Still call original to trigger logging, but we want to control the ID
            # Actually, the original generates it randomly. Let's just do the logging here ourselves or override properly.
            
            from copilot_agent_server.local_server_logger import LocalServerLogger
            logger = LocalServerLogger({
                "log_dir": SERVER_CONFIG["log_dir"],
                "image_dir": SERVER_CONFIG["image_dir"],
                "session_id": session_id
            })
            
            extra_info = payload.get('extra_info', {})
            message_to_log = {
                "log_type": "session_start",
                "task": payload["task"],
                "task_type": payload["task_type"],
                "model_config": payload["model_config"],
                "extra_info": extra_info
            }
            logger.log_str(message_to_log, is_print=l2_server.debug)
            return session_id

        l2_server.get_session = forced_get_session

        # Monkeypatch automate_step to check for stop_event
        original_automate_step = l2_server.automate_step
        def checked_automate_step(payload):
            if stop_event.is_set():
                raise InterruptedError("Task stopped by user")
            return original_automate_step(payload)
        
        l2_server.automate_step = checked_automate_step

        evaluate_task_on_device(
            l2_server, 
            device_info, 
            task_str, 
            MODEL_CONFIG, 
            reflush_app=True
        )
        
        if not stop_event.is_set():
            current_task["status"] = "completed"
    except InterruptedError:
        current_task["status"] = "stopped"
    except Exception as e:
        if not stop_event.is_set():
            current_task["status"] = "failed"
            current_task["error"] = str(e)
        else:
            current_task["status"] = "stopped"
        import traceback
        traceback.print_exc()

# Serve frontend static files
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    # Create required directories
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    if not os.path.exists("frontend"):
        os.makedirs("frontend")
    import webbrowser
    from threading import Timer
    def open_browser():
        webbrowser.open("http://127.0.0.1:8000")
    
    Timer(1.5, open_browser).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
