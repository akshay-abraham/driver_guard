# How Driver Guard Works

## Simple Overview

Driver Guard repeatedly takes a picture from the webcam and checks the driver's face.

```text
Webcam
  -> find face points
  -> measure eyes and mouth
  -> track changes over time
  -> decide driver state
  -> update dashboard and alerts
```

It watches for closed eyes, long blinks, frequent blinking, yawns, microsleeps, and a missing face.

## What Goes Into the System

The main input is the webcam image. By default, the project uses:

- The first webcam, camera index `0`
- A `640 x 480` image
- A target of 30 frames per second
- One face

The settings page is another input. It changes values such as eye sensitivity, yawn sensitivity, and alert strictness.

## What Each Part Does

### OpenCV

OpenCV controls the webcam. For each frame, it:

- Reads the latest image
- Mirrors the image like a normal camera preview
- Converts its colors for MediaPipe
- Draws eye and mouth outlines
- Shrinks and compresses the image for the browser

### Google MediaPipe

MediaPipe finds points on the face. A point is a numbered location such as an eye corner, eyelid, or lip edge.

The face model returns:

- 468 points for the standard face mesh
- 478 points when 10 extra iris points are included

It is not around 600 points. This project accepts either 468 or 478 points.

MediaPipe examines the full face, but Driver Guard only needs 16 unique points for its calculations:

- 6 points around the left eye
- 6 points around the right eye
- 8 points around the mouth

Some points are shared between measurements, which is why the final unique total is 16.

MediaPipe only locates the face. It does not decide whether the driver is tired. Driver Guard makes that decision from the point positions and timing.

### Eye Measurement

Driver Guard calculates Eye Aspect Ratio, or EAR.

It compares the eye's height with its width:

- Open eye: larger EAR
- Closed eye: smaller EAR

Both eyes are measured and averaged. Using a ratio helps the measurement remain useful when the driver moves closer to or farther from the camera.

### Mouth Measurement

Driver Guard calculates Mouth Aspect Ratio, or MAR.

It compares the mouth's opening height with its width:

- Closed mouth: smaller MAR
- Open mouth: larger MAR

If MAR stays high long enough, the opening is counted as a yawn.

### Decision Engine

The decision engine watches EAR and MAR over time. This is important because one unusual camera frame should not cause an alert.

For the eyes, it remembers when they close and measures how long they remain closed. The completed event can become:

- Noise if it was extremely short
- A normal blink
- A long blink
- A microsleep if closure continues beyond the configured limit

For the mouth, it remembers when the mouth opens. It counts a yawn only when the mouth stays open long enough.

It also keeps recent event times to calculate:

- Blinks per minute
- Recent long blinks
- Recent yawns
- Current eye-closure time

### Driver States

The final state is one of these:

- **Safe:** Fatigue rules have not been reached.
- **Fatigue:** Multiple fatigue signs are active, such as rapid blinking, long blinks, or repeated yawns.
- **Sleeping:** The eyes remain closed beyond the microsleep limit.
- **Face Not Detected:** The face has been missing longer than the allowed time.

Sleeping has higher priority than the normal fatigue rules.

### Alert Manager

The alert manager sends warning events to the browser. It prevents the same alert from restarting on every camera frame.

- Fatigue starts a level 2 warning.
- Sleeping starts a level 3 alarm.
- A missing face starts a face warning.

The **I'm Awake** button clears current fatigue events, stops the browser sound, and pauses repeated alerts for 10 seconds. It keeps the session's total blink and yawn counters.

### FastAPI and Uvicorn

FastAPI is the Python backend. Uvicorn runs it at `http://localhost:8000`.

The backend:

- Starts and stops the camera
- Runs face processing in a background thread
- Serves the dashboard files
- Receives settings changes
- Handles the **I'm Awake** action
- Sends live data to the browser

### WebSocket

A WebSocket is a connection that stays open between the backend and browser. It sends new information without reloading the page.

Each update can contain:

- The latest camera image
- EAR and MAR values
- Driver state and reasons
- Blink and yawn counters
- Eye-closure time
- Face visibility
- FPS and session time
- Alert events

### Browser Dashboard

The frontend uses HTML, CSS, and JavaScript:

- HTML defines the controls and information cards.
- CSS creates the layout, colors, and speedometer design.
- JavaScript receives WebSocket data, moves the needles, changes status text, plays sounds, and sends settings to the backend.

## Complete Frame Flow

For every webcam frame:

1. OpenCV captures and mirrors the image.
2. MediaPipe finds the face landmarks.
3. Driver Guard selects eye and mouth points.
4. EAR and MAR are calculated.
5. The decision engine updates its timers and counters.
6. A driver state and explanation are produced.
7. OpenCV prepares the annotated preview image.
8. FastAPI sends everything through the WebSocket.
9. JavaScript updates the dashboard.

## Privacy

Processing happens on the computer running Driver Guard. MediaPipe runs locally from the downloaded model file.

The project does not upload camera images to Google or another cloud service. It does not contain video-recording code. Frames are kept in memory and sent only to the locally hosted dashboard.

## Project Files

```text
backend/main.py                    Starts FastAPI and the processing loop
backend/config.py                  Camera settings and detection limits
backend/vision/camera.py           Reads the webcam
backend/vision/face_processor.py   Runs MediaPipe and draws outlines
backend/vision/metrics.py          Calculates EAR and MAR
backend/core/decision_engine.py    Detects events and driver state
backend/core/alert_manager.py      Controls alert timing
frontend/index.html                Dashboard structure
frontend/css/style.css             Dashboard design
frontend/js/app.js                 Live dashboard updates
frontend/js/settings.js            Settings controls
frontend/js/audio.js               Browser alert sounds
```

## Limitations

- Poor lighting, glasses, camera angle, and face position can reduce accuracy.
- Talking can sometimes look like a yawn.
- Different drivers may need different thresholds.
- The system estimates visible behavior; it cannot medically determine tiredness.
- This is not a certified automotive safety system.
