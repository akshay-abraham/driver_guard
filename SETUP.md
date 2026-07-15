# Setup Guide

This guide supports Fedora and Windows PowerShell.

## Requirements

- Git
- Python 3 with `pip` and `venv`
- A working webcam
- `wget` on Fedora

## Fedora

### 1. Install tools

```bash
sudo dnf install git python3 python3-pip wget
```

### 2. Clone the project

```bash
git clone https://github.com/akshay-abraham/driver_guard.git
cd driver_guard
```

### 3. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Python libraries

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 5. Download the MediaPipe model

```bash
mkdir -p models
wget -O models/face_landmarker.task "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
```

### 6. Run Driver Guard

```bash
python -m backend.main
```

Open [http://localhost:8000](http://localhost:8000).

## Windows PowerShell

Install current versions of Git and Python before continuing. Run all commands from PowerShell.

### 1. Clone the project

```powershell
git clone https://github.com/akshay-abraham/driver_guard.git
Set-Location .\driver_guard
```

### 2. Create and activate a virtual environment

```powershell
python -m venv .\venv
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, allow it for the current window and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

### 3. Install Python libraries

```powershell
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

### 4. Download the MediaPipe model

These commands use paths relative to the project directory:

```powershell
New-Item -ItemType Directory -Force -Path .\models
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" -OutFile .\models\face_landmarker.task
```

### 5. Run Driver Guard

```powershell
python -m backend.main
```

Open [http://localhost:8000](http://localhost:8000).

## Stop the Application

Press `Ctrl+C` in the terminal.

## Common Settings

- Change the webcam with `CAMERA_INDEX` in `backend/config.py`.
- Detection thresholds are also stored in `backend/config.py`.
