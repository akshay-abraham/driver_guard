# Original and Current Version Comparison

## Summary

The original version is a small desktop script that checks only whether the eyes stay closed for a fixed number of frames.

The current version is a complete local web application. It measures eyes and mouth movement over time, detects several fatigue signs, provides configurable alerts, and shows everything in a browser dashboard.

## Side-by-Side Comparison

| Area | Original version | Current version |
|---|---|---|
| Main file | One Python script | Separate backend, vision, decision, and frontend files |
| Face library | dlib | Google MediaPipe |
| Face landmarks | 68 points | 468 or 478 points |
| Points used for eye calculation | 6 per eye | 6 per eye |
| Mouth tracking | No | Yes |
| Blink tracking | No blink history | Normal, long, and rapid blink tracking |
| Yawn tracking | No | Yes |
| Microsleep detection | Based on 20 closed-eye frames | Based on actual eye-closure time |
| Missing-face warning | No | Yes |
| User interface | OpenCV desktop window | Browser dashboard |
| Settings | Two fixed constants in code | Live beginner and advanced settings |
| Alerts | Terminal message | Browser sound, banner, status levels, and cooldowns |
| I'm Awake action | No | Clears current fatigue state and suppresses alerts briefly |
| Backend | None | FastAPI and Uvicorn |
| Live communication | None | WebSocket and REST API |
| Model file | dlib 68-point predictor | MediaPipe Face Landmarker model |
| Privacy | Local | Local |

## Original Version

The original `Drivers Alert System.py` follows this process:

1. OpenCV reads a webcam frame.
2. The frame is resized and changed to grayscale.
3. dlib finds every visible face.
4. The dlib 68-point predictor places landmarks on each face.
5. Six points from each eye are selected.
6. Eye Aspect Ratio (EAR) is calculated for both eyes and averaged.
7. If EAR stays below `0.25`, a frame counter increases.
8. After 20 consecutive low-EAR frames, the image displays a warning.
9. `sound_alarm()` prints a terminal message once.
10. Opening the eyes resets the counter and alarm flag.

### Original Strengths

- Short and easy to understand
- Good demonstration of the EAR formula
- Few moving parts
- Runs directly in an OpenCV window

### Original Limitations

- Only checks eye closure
- Does not detect yawns
- Does not count normal or long blinks
- Does not calculate blink frequency
- Does not warn when the face disappears
- Uses frame count instead of real elapsed time
- Twenty frames mean different durations on fast and slow computers
- The alarm function only prints text; it does not play a beep
- Thresholds must be changed in the source code
- Requires `dlib`, SciPy, imutils, and a separate 68-landmark model
- All capture, detection, decisions, drawing, and UI code are in one file

## Current Version

The current application follows this process:

1. OpenCV continuously reads and mirrors webcam frames.
2. MediaPipe locates 468 or 478 detailed face points.
3. Driver Guard selects points around both eyes and the mouth.
4. It calculates Eye Aspect Ratio (EAR) and Mouth Aspect Ratio (MAR).
5. A decision engine tracks how the values change over real time.
6. It classifies blinks, long blinks, microsleeps, and yawns.
7. It checks recent event patterns and face visibility.
8. It produces a driver state with a plain-language reason.
9. FastAPI sends the image and measurements to the browser.
10. JavaScript updates the dashboard and plays alerts.

### Current Strengths

- Uses real elapsed time instead of relying only on frame count
- Detects several fatigue signals instead of one
- Separates camera, measurements, decisions, alerts, API, and UI code
- Provides live threshold settings
- Gives reasons for each warning
- Provides visual gauges, counters, audio, and alert levels
- Works through a local browser on Fedora and Windows
- Keeps all camera processing on the local computer

### Current Tradeoffs

- Has more files and concepts to understand
- Requires a Python environment, web server, and MediaPipe model
- Sends compressed frames from the backend to the local browser, which uses more processing than a basic OpenCV window
- Still depends on good lighting, camera position, and suitable thresholds

## dlib vs MediaPipe

The original dlib predictor returns 68 landmarks. This is enough to outline major face areas and calculate EAR.

MediaPipe returns a much denser map of 468 or 478 landmarks. The current project still uses only a small set of eye and mouth points for its calculations, but the denser map provides more choices and supports detailed mouth and iris regions.

Neither library decides that a driver is tired. Both libraries only locate facial points. The project must calculate ratios, track time, and apply fatigue rules itself.

## Most Important Logic Improvement

The largest improvement is the move from frame-based detection to time-based detection.

The original rule is:

```text
EAR below threshold for 20 frames -> alert
```

At 30 FPS, 20 frames are about 0.67 seconds. At 10 FPS, they are about 2 seconds. The meaning changes with camera and computer speed.

The current rule records timestamps:

```text
eyes close -> start timer -> compare elapsed seconds with configured limits
```

This makes blink and microsleep durations more consistent when FPS changes.

## Final Difference

The original version answers one question:

> Have the eyes remained below the EAR threshold for 20 frames?

The current version answers a broader question:

> What is the driver's current visible state based on eye closure time, blink patterns, yawns, and face visibility?

The original is useful as a learning prototype. The current version turns that idea into a structured monitoring application.
