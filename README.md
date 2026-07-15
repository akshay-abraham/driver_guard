# Driver Guard

Driver Guard is a local driver-monitoring dashboard that uses a webcam and Google MediaPipe face landmarks to track eye openness, blinking, yawning, and signs of fatigue. The FastAPI backend processes video on the device and streams the annotated feed and live metrics to the browser.

## Prerequisites

Install these tools before continuing:

- Git
- Python 3 with `venv` and `pip`
- `wget`
- A working webcam

On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install git python3 python3-venv python3-pip wget
```

## Install

1. Clone the repository and enter it:

```bash
git clone https://github.com/akshay-abraham/driver_guard.git
cd driver_guard
```

2. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

On Windows PowerShell, activate it with:

```powershell
venv\Scripts\Activate.ps1
```

3. Upgrade `pip` and install the Python libraries:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4. Download the Google MediaPipe Face Landmarker model manually:

```bash
mkdir -p "$HOME/.cache/dms"
wget -O "$HOME/.cache/dms/face_landmarker.task" "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
```

## Run

Start the application from the repository root while the virtual environment is active:

```bash
python -m backend.main
```

Open [http://localhost:8000](http://localhost:8000) in your browser and allow access to the webcam if prompted.

Press `Ctrl+C` in the terminal to stop the server.

## Notes

- Camera index and server settings are configured in `backend/config.py`.
- Video processing runs locally; camera frames are not sent to an external service.
- This project is an assistance tool and should not replace safe driving practices or proper rest.
