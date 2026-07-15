# Driver Guard

Driver Guard is a local driver-monitoring dashboard that uses a webcam and Google MediaPipe face landmarks to track eye openness, blinking, yawning, and signs of fatigue. The FastAPI backend processes video on the device and streams the annotated feed and live metrics to the browser.

## How the Project Works

In simple terms, Driver Guard watches the driver's face through a webcam. It measures how open the eyes and mouth are over time, looks for patterns associated with fatigue, and displays the result in a browser dashboard.

The main data flow is:

```text
Webcam frame
    -> OpenCV captures and mirrors the image
    -> MediaPipe finds facial landmark coordinates
    -> Driver Guard measures eye and mouth geometry
    -> The decision engine tracks blinks, yawns, and closure time
    -> FastAPI sends the frame and results to the browser
    -> The dashboard updates its gauges, status, and alerts
```

## What Each Part Does

- **Python** is the main programming language. It connects the camera, MediaPipe, detection rules, and web server.
- **OpenCV** talks to the webcam. It takes a picture many times per second, mirrors it, draws the eye and mouth lines, resizes it, and converts it into a JPEG for the dashboard.
- **Google MediaPipe** examines each picture and finds the position of the face, eyes, eyelids, lips, and other facial features. It supplies coordinates, but it does not decide whether the driver is tired.
- **The metric calculator** selects eye and mouth coordinates from MediaPipe. It turns distances between those points into Eye Aspect Ratio (EAR) and Mouth Aspect Ratio (MAR) numbers.
- **The decision engine** watches EAR and MAR over time. It identifies blinks, long blinks, closed eyes, microsleeps, open-mouth events, yawns, and a missing face.
- **The alert manager** decides when to send a warning. It adds cooldowns so one condition does not start the same sound on every frame.
- **FastAPI** is the backend web application. It provides the page, receives settings and button actions, and sends live results to the browser.
- **Uvicorn** is the program that runs FastAPI at `http://localhost:8000`.
- **WebSocket** is the always-open connection between the backend and dashboard. It delivers new frames and measurements without refreshing the page.
- **HTML** provides the dashboard structure.
- **CSS** controls the dashboard appearance, layout, colors, and speedometers.
- **JavaScript** receives live data, moves the gauges, updates text, plays alerts, saves settings, and handles the **I'm Awake** button.
- **NumPy** stores each camera frame as a numerical image array that OpenCV and MediaPipe can process.

## Input

The main input is a live frame from the computer's webcam. By default, the application requests:

- Camera index `0`, normally the default webcam
- Resolution `640 x 480`
- Target rate of `30 FPS`
- One face at a time

The camera frame is mirrored horizontally so the preview behaves like a mirror. If the computer has multiple cameras, `CAMERA_INDEX` can be changed in `backend/config.py`.

The settings panel is another input. It lets the user change thresholds such as eye sensitivity, yawn sensitivity, blink timing, and alert strictness while the application is running.

## What MediaPipe Does

MediaPipe Face Landmarker is the face-tracking part of the project. It receives each camera image and maps the face using landmarks. A landmark is simply a numbered point with `x`, `y`, and depth coordinates.

It is not around 600 points. The exact count is:

- **468 face landmarks** in the standard face mesh
- **478 landmarks** when the classic Face Mesh iris refinement is enabled: 468 face points plus 10 iris points

The downloaded Face Landmarker Tasks model used by newer MediaPipe installations provides 478 face-landmark coordinates. The code accepts either a 468-point or 478-point result because its required eye and mouth point numbers exist in both.

MediaPipe processes the full landmark model to understand the face. Driver Guard does not use all those points in its mathematical calculations. It selects:

- **6 landmark indices for the left eye**
- **6 landmark indices for the right eye**
- **8 landmark indices for the mouth**
- **16 unique points total**, because some selected points are reused as parts of measurement pairs

The selected calculation points are:

- Left eye: `33`, `133`, `159`, `145`, `158`, `153`
- Right eye: `362`, `263`, `386`, `374`, `385`, `380`
- Mouth: `61`, `291`, `13`, `14`, `81`, `178`, `311`, `402`

Additional points are used only to draw the visible eye and mouth outlines over the camera image. They do not add more fatigue rules.

MediaPipe does not decide whether the driver is tired. It only answers questions such as:

- Is a face visible?
- Where are the eyelids?
- Where are the eye corners?
- Where are the upper and lower lips?

Driver Guard then uses selected landmark points to calculate its own measurements and decisions.

For every point, MediaPipe initially returns a position relative to the image size. For example, `x = 0.5` means halfway across the image. Driver Guard multiplies these values by the frame width and height to obtain pixel positions that can be measured and drawn.

The application supports both MediaPipe interfaces:

- The older Face Mesh `solutions` interface, when available
- The newer Face Landmarker Tasks interface, using `models/face_landmarker.task`

## Measurements

### Eye Aspect Ratio (EAR)

EAR estimates how open the eyes are. Driver Guard measures vertical eyelid distances and divides them by the horizontal eye width.

```text
EAR = combined vertical eye distance / (2 x horizontal eye width)
```

- A higher EAR normally means the eye is open.
- A lower EAR normally means the eye is closed.
- The left and right eyes are measured separately and then averaged.

Using a ratio instead of raw pixels makes the measurement less dependent on camera distance or face size.

### Mouth Aspect Ratio (MAR)

MAR estimates how open the mouth is. It compares three vertical lip distances with the horizontal mouth width.

```text
MAR = combined vertical mouth distance / (3 x horizontal mouth width)
```

- A low MAR normally means the mouth is closed.
- A high MAR means the mouth is open.
- MAR staying above its threshold long enough is counted as a yawn.

## Data Processing

For every camera frame, the backend performs these steps:

1. **Capture:** OpenCV asks the webcam for the newest image.
2. **Mirror:** OpenCV flips the image horizontally so movement feels natural in the preview.
3. **Convert color:** OpenCV supplies BGR images, while MediaPipe expects RGB, so the color-channel order is changed.
4. **Find the face:** MediaPipe checks whether one face is visible.
5. **Map landmarks:** If a face exists, MediaPipe returns 468 or 478 numbered face coordinates.
6. **Convert coordinates:** Driver Guard changes relative coordinates into pixel positions using the image width and height.
7. **Select points:** The metric code takes only the eye and mouth points needed for EAR and MAR.
8. **Measure eyes:** It compares each eye's vertical opening with its horizontal width, then averages the left and right EAR values.
9. **Measure mouth:** It compares three vertical mouth openings with the mouth width to produce MAR.
10. **Track time:** The decision engine remembers when the eyes close or mouth opens. One unusual frame is not automatically treated as fatigue.
11. **Classify events:** Finished eye closures become noise, normal blinks, or long blinks. Long continuous closure becomes a microsleep. A long mouth opening becomes a yawn.
12. **Choose a state:** Recent events are checked against the configured rules to produce Safe, Fatigue, Sleeping, or Face Not Detected.
13. **Prepare the preview:** OpenCV draws selected eye and mouth outlines, reduces the image size, and compresses it as JPEG.
14. **Send results:** FastAPI sends the JPEG, measurements, counters, state, and explanation to the browser through the WebSocket.
15. **Update the screen:** JavaScript moves the speedometer needles, updates the status, and starts an alert when requested.

## Blink and Yawn Detection

An eye closure starts when EAR stays below the configured threshold. When the eye opens again, the closure duration is classified as:

- Noise if it was too short
- A normal blink if it was within the normal blink duration
- A long blink if it exceeded the normal duration
- A microsleep if the eyes remained closed beyond the microsleep threshold

A mouth-opening event starts when MAR rises above its threshold. When MAR falls below the threshold again, the opening is counted as a yawn if it lasted long enough.

The system stores recent event timestamps in rolling time windows. This allows it to calculate blink frequency and count recent long blinks and yawns without keeping every historical frame.

## Driver States

The decision engine produces one of these states:

- **Safe:** No configured combination of fatigue signs has been reached.
- **Fatigue:** Multiple indicators, such as rapid blinking, long blinks, slow eye closure, or repeated yawns, have reached the configured score threshold.
- **Sleeping:** The eyes have stayed closed for at least the microsleep duration. This has priority over the normal fatigue score.
- **Face Not Detected:** The driver's face has been missing longer than the configured warning duration.

The backend also returns plain-language reasons for the current state, such as rapid blinking, recent yawns, or how long the eyes have remained closed.

## Alerts and I'm Awake

The alert manager turns continuous states into controlled alert events. This prevents the browser from restarting the same alarm on every frame.

- Fatigue generates a level 2 warning.
- Sleeping generates a level 3 alarm.
- A missing face generates a face warning.
- Alerts can repeat after configurable cooldown periods if the condition remains active.

Pressing **I'm Awake** sends an `awake` action to the backend. The backend clears current fatigue event windows and eye/mouth state, keeps lifetime blink and yawn counters, and suppresses repeated alerts for 10 seconds. The browser also stops alert audio and hides the active alert.

## Backend and Browser Communication

The backend is a FastAPI application running under Uvicorn.

### REST endpoints

- `GET /api/config` returns current thresholds and the settings description.
- `POST /api/config` updates selected thresholds while the application is running.
- `POST /api/config/reset` restores default thresholds.
- `POST /api/session` handles session actions such as `awake` and `reset`.
- `GET /api/status` reports whether the camera opened successfully.

### WebSocket

The browser connects to `/ws`. The backend repeatedly sends:

- The latest annotated camera frame as a Base64-encoded JPEG
- EAR and MAR measurements
- Driver state and alert level
- Reasons for the current state
- Blink, yawn, eye-closure, face-presence, session-time, and FPS data
- One-shot alert events when necessary

JavaScript updates the dashboard without reloading the page.

## Privacy

All camera processing happens on the same computer running Driver Guard. The application does not upload frames or measurements to an external service. Google MediaPipe runs locally; the downloaded `.task` file contains the face-landmark model, not a cloud connection.

Camera frames are held in memory, processed, and streamed only to the locally served dashboard. This project does not contain code that records video to disk.

## Project Structure

```text
driver_guard/
├── backend/
│   ├── core/
│   │   ├── alert_manager.py      # Alert timing and cooldowns
│   │   └── decision_engine.py    # Blink, yawn, fatigue, and state logic
│   ├── vision/
│   │   ├── camera.py             # Webcam access
│   │   ├── face_processor.py     # MediaPipe processing and overlays
│   │   └── metrics.py            # EAR and MAR calculations
│   ├── config.py                 # Camera and detection thresholds
│   ├── main.py                   # FastAPI server and processing loop
│   └── schemas.py                # API request models
├── frontend/
│   ├── css/style.css             # Dashboard styling
│   ├── js/                       # Live UI, settings, and alert audio
│   └── index.html                # Dashboard page
├── models/
│   └── face_landmarker.task      # Manually downloaded MediaPipe model
├── requirements.txt
└── README.md
```

## Limitations

- Results depend on camera angle, lighting, glasses, face visibility, and individual facial geometry.
- Talking or opening the mouth can sometimes resemble a yawn.
- Thresholds may need adjustment for a particular driver and camera setup.
- The system observes visible facial behavior; it cannot directly measure attention, medical condition, or actual sleepiness.
- This is an assistance and demonstration tool, not a certified automotive safety system.

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
