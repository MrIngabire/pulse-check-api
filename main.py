import asyncio
import time
import json
from typing import Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ==========================================
# 1. DATA MODELS & IN-MEMORY STORE
# ==========================================

# In-memory database to store monitors
# Structure: { "device_id": { "timeout": int, "alert_email": str, "last_heartbeat": float, "status": str } }
monitors: Dict[str, Any] = {}

class MonitorCreate(BaseModel):
    id: str
    timeout: int
    alert_email: str

# ==========================================
# 2. BACKGROUND WORKER PROCESS
# ==========================================

async def watchdog_worker():
    """
    Runs continuously in the background to check for expired timers.
    Checks all active devices every 1 second.
    """
    while True:
        await asyncio.sleep(1) 
        current_time = time.time()
        
        for device_id, data in monitors.items():
            if data["status"] == "active":
                elapsed_time = current_time - data["last_heartbeat"]
                
                # User Story 3: The Alert (Failure State)
                if elapsed_time >= data["timeout"]:
                    # Change status so we don't spam alerts
                    monitors[device_id]["status"] = "down"
                    
                    alert_payload = {
                        "ALERT": f"Device {device_id} is down!",
                        "time": current_time,
                        "email_to": data["alert_email"]
                    }
                    # Simulate firing the alert (console.log equivalent)
                    print(json.dumps(alert_payload))

# ==========================================
# 3. APP INITIALIZATION & LIFESPAN
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Modern lifespan manager. Replaces the deprecated @app.on_event("startup").
    Starts the watchdog worker when the server boots and cancels it on shutdown.
    """
    worker_task = asyncio.create_task(watchdog_worker())
    yield
    worker_task.cancel()

# Initialize the application with the lifespan context manager
app = FastAPI(title="CritMon Pulse-Check API", lifespan=lifespan)

# ==========================================
# 4. API ENDPOINTS
# ==========================================

# User Story 1: Registering a Monitor
@app.post("/monitors", status_code=201)
def create_monitor(monitor: MonitorCreate):
    monitors[monitor.id] = {
        "timeout": monitor.timeout,
        "alert_email": monitor.alert_email,
        "last_heartbeat": time.time(),
        "status": "active"
    }
    return {"message": f"Monitor created for {monitor.id}. Timer started."}

# User Story 2: The Heartbeat (Reset) & Bonus Story: Un-pause
@app.post("/monitors/{device_id}/heartbeat")
def heartbeat(device_id: str):
    if device_id not in monitors:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    # Reset the timer and ensure it is set back to active
    monitors[device_id]["last_heartbeat"] = time.time()
    monitors[device_id]["status"] = "active"
    
    return {"status": "OK", "message": f"Timer reset for {device_id}"}

# Bonus User Story: The "Snooze" Button
@app.post("/monitors/{device_id}/pause")
def pause_monitor(device_id: str):
    if device_id not in monitors:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    # Stop monitoring this device
    monitors[device_id]["status"] = "paused"
    return {"status": "Paused", "message": f"Monitoring paused for {device_id}"}

# Developer's Choice: Global Status Dashboard
@app.get("/monitors")
def get_all_monitors():
    """
    Returns the current state of all monitored devices, 
    calculating the remaining time on the fly.
    """
    current_time = time.time()
    dashboard = {}
    
    for device_id, data in monitors.items():
        # Calculate time left, ensuring it doesn't drop below 0
        time_left = max(0, data["timeout"] - (current_time - data["last_heartbeat"]))
        
        # If the device isn't active, time left is not applicable
        if data["status"] != "active":
            time_left = 0
            
        dashboard[device_id] = {
            "status": data["status"],
            "seconds_remaining": round(time_left, 1) if data["status"] == "active" else "N/A",
            "alert_email": data["alert_email"]
        }
    return dashboard