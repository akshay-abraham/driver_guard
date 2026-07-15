# Driver Guard

Driver Guard is a local driver-monitoring dashboard that uses a webcam and Google MediaPipe face landmarks to track eye openness, blinking, yawning, and signs of fatigue. The FastAPI backend processes video on the device and streams the annotated feed and live metrics to the browser.

## Prerequisites

Install these tools before continuing:

- Git
- Python 3 with `venv` and `pip`
- A working webcam

### Fedora

```bash
sudo dnf install git python3 python3-pip wget
```

### Windows

Install current versions of Git and Python, then open PowerShell. The Windows commands below use PowerShell's built-in `Invoke-WebRequest`, so `wget` is not required.

## Install

1. Clone the repository and enter it.

Fedora:

```bash
git clone https://github.com/akshay-abraham/driver_guard.git
cd driver_guard
```

Windows PowerShell:

```powershell
git clone https://github.com/akshay-abraham/driver_guard.git
Set-Location .\driver_guard
```

2. Create and activate a virtual environment.

Fedora:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .\venv
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this once in the current window and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

3. Upgrade `pip` and install the Python libraries.

Fedora:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

4. Download the Google MediaPipe Face Landmarker model manually.

Fedora:

```bash
mkdir -p models
wget -O models/face_landmarker.task "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path .\models
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" -OutFile .\models\face_landmarker.task
```

## Run

Start the application from the repository root while the virtual environment is active:

Fedora:

```bash
python -m backend.main
```

Windows PowerShell:

```powershell
python -m backend.main
```

Open [http://localhost:8000](http://localhost:8000) in your browser and allow access to the webcam if prompted.

Press `Ctrl+C` in the terminal to stop the server.

## Notes

- Camera index and server settings are configured in `backend/config.py`.
- Video processing runs locally; camera frames are not sent to an external service.
- This project is an assistance tool and should not replace safe driving practices or proper rest.
