# Driver Guard

Driver Guard is a local driver-monitoring dashboard. It uses a webcam to measure eye and mouth movement, detect fatigue signs, and warn the driver.

The application uses Python, OpenCV, Google MediaPipe, and FastAPI. Camera processing happens locally on the computer.

## Documentation

- [Setup Guide](SETUP.md): Install and run Driver Guard on Fedora or Windows.
- [Project Details](DETAILS.md): Learn how the camera, MediaPipe, detection logic, backend, and dashboard work.
- [Version Comparison](COMPARISON.md): Compare the original dlib script with the current application.

## Quick Start

After completing the setup guide, run:

```bash
python -m backend.main
```

Then open [http://localhost:8000](http://localhost:8000).

> Driver Guard is an assistance and demonstration tool. It is not a certified automotive safety system and does not replace proper rest or safe driving.
