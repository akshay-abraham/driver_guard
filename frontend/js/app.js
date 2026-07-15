/**
 * app.js — Main frontend controller for the Driver Monitoring System.
 *
 * Connects to the backend WebSocket, receives annotated JPEG frames +
 * live metrics, and drives every DOM element in the cockpit dashboard.
 */

(function () {
  "use strict";

  // ---- DOM refs --------------------------------------------------------- //
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const videoFeed = $("#videoFeed");
  const cameraOverlay = $("#cameraOverlay");
  const cameraOverlayText = $("#cameraOverlayText");
  const connectionPill = $("#connectionPill");
  const connectionLabel = $("#connectionLabel");
  const sessionTimeEl = $("#sessionTime");
  const fpsValueEl = $("#fpsValue");

  const statusPanel = $("#statusPanel");
  const statusValue = $("#statusValue");
  const statusLevelNum = $("#statusLevelNum");
  const reasonList = $("#reasonList");

  const earReadout = $("#earReadout");
  const marReadout = $("#marReadout");
  const earNeedle = $("#earNeedle");
  const marNeedle = $("#marNeedle");

  const blinkCount = $("#blinkCount");
  const blinkFreq = $("#blinkFreq");
  const eyeClosure = $("#eyeClosure");
  const yawnCount = $("#yawnCount");
  const faceStatus = $("#faceStatus");
  const faceChip = $("#faceChip");
  const faceChipLabel = $("#faceChipLabel");

  const alertBanner = $("#alertBanner");
  const alertBannerIcon = $("#alertBannerIcon");
  const alertBannerText = $("#alertBannerText");
  const awakeBtn = $("#awakeBtn");

  // ---- State ------------------------------------------------------------ //
  let ws = null;
  let sessionStartTime = Date.now();
  let alertVisible = false;

  // ---- Helpers ---------------------------------------------------------- //

  function formatDuration(ms) {
    const totalSec = Math.floor(ms / 1000);
    const h = String(Math.floor(totalSec / 3600)).padStart(2, "0");
    const m = String(Math.floor((totalSec % 3600) / 60)).padStart(2, "0");
    const s = String(totalSec % 60).padStart(2, "0");
    return `${h}:${m}:${s}`;
  }

  function setConnectionState(state) {
    connectionPill.classList.remove("is-connected", "is-error");
    if (state === "connected") {
      connectionPill.classList.add("is-connected");
      connectionLabel.textContent = "Live";
    } else if (state === "error") {
      connectionPill.classList.add("is-error");
      connectionLabel.textContent = "Disconnected";
    } else {
      connectionLabel.textContent = "Connecting\u2026";
    }
  }

  function setMeterPosition(indicator, normalized) {
    const clamped = Math.max(0, Math.min(1, normalized));
    indicator.style.transform = `translateX(-50%) rotate(${-90 + clamped * 180}deg)`;
  }

  function showAlert(icon, text, levelClass) {
    alertBanner.className = "alert-banner is-visible " + levelClass;
    alertBannerIcon.textContent = icon;
    alertBannerText.textContent = text;
    alertVisible = true;
    if (window.DriverMonitorAudio) {
      window.DriverMonitorAudio.playAlert(levelClass);
    }
  }

  function hideAlert() {
    alertBanner.classList.remove("is-visible");
    alertVisible = false;
  }

  function showAwakeButton(level) {
    // Show during FATIGUE (2) or SLEEPING (3)
    if (level === 2 || level === 3) {
      awakeBtn.classList.add("is-visible");
      // Red pulse style for Level 3 (sleeping), green for Level 2 (fatigue)
      awakeBtn.classList.toggle("is-urgent", level === 3);
    } else {
      awakeBtn.classList.remove("is-visible", "is-urgent");
    }
  }

  awakeBtn.addEventListener("click", async () => {
    if (awakeBtn.disabled) return;

    awakeBtn.disabled = true;
    try {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "awake" }),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Unable to acknowledge alert");

      hideAlert();
      awakeBtn.classList.remove("is-visible", "is-urgent");
      if (window.DriverMonitorAudio) {
        window.DriverMonitorAudio.stopAll();
      }
    } catch (error) {
      console.error("Failed to confirm awake state:", error);
    } finally {
      awakeBtn.disabled = false;
    }
  });

  // ---- Update dashboard from a metrics snapshot ------------------------- //

  function updateDashboard(metrics) {
    if (!metrics) return;

    // Status hero
    const level = metrics.level ?? 0;
    statusPanel.setAttribute("data-level", level);
    statusValue.textContent = metrics.state || "Initializing";
    statusLevelNum.textContent = level || "\u2013";

    // Show/hide the "I'm awake" button
    showAwakeButton(level);

    // Reasons
    const reasons = metrics.reasons || [];
    if (reasons.length === 0) {
      reasonList.innerHTML =
        '<li class="reason-list__empty">No data yet</li>';
    } else {
      reasonList.innerHTML = reasons
        .map((r) => `<li>${escapeHtml(r)}</li>`)
        .join("");
    }

    // EAR / MAR readouts
    earReadout.textContent = (metrics.ear ?? 0).toFixed(3);
    marReadout.textContent = (metrics.mar ?? 0).toFixed(3);

    // Signal meters (EAR 0-0.5, MAR 0-1.0)
    const earNorm = Math.min(1, (metrics.ear ?? 0) / 0.5);
    const marNorm = Math.min(1, (metrics.mar ?? 0) / 1.0);
    setMeterPosition(earNeedle, earNorm);
    setMeterPosition(marNeedle, marNorm);

    // Metric strip
    blinkCount.textContent = metrics.blink_count_total ?? 0;
    blinkFreq.innerHTML =
      (metrics.blink_frequency_per_min ?? 0).toFixed(1) +
      "<small>/min</small>";
    eyeClosure.innerHTML =
      (metrics.current_eye_closure_s ?? 0).toFixed(1) + "<small>s</small>";
    yawnCount.textContent = metrics.yawn_count_window ?? 0;

    const detected = metrics.face_visible ?? false;
    faceStatus.textContent = detected ? "Yes" : "No";
    faceChip.className = "face-chip " + (detected ? "is-ok" : "is-warn");
    faceChipLabel.textContent = detected ? "Driver visible" : "Locating driver\u2026";

    // Camera overlay
    if (detected) {
      cameraOverlay.classList.add("is-hidden");
    } else {
      cameraOverlay.classList.remove("is-hidden");
      cameraOverlayText.textContent = metrics.state === "FACE_NOT_DETECTED"
        ? "Face not visible \u2014 look at the camera"
        : "Waiting for camera\u2026";
    }
  }

  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  // ---- Session clock ----------------------------------------------------- //

  setInterval(() => {
    sessionTimeEl.textContent = formatDuration(Date.now() - sessionStartTime);
  }, 1000);

  // ---- WebSocket --------------------------------------------------------- //

  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/ws`;
    ws = new WebSocket(url);

    ws.onopen = () => setConnectionState("connected");

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);

        // Frame
        if (msg.frame) {
          videoFeed.src = "data:image/jpeg;base64," + msg.frame;
          videoFeed.style.opacity = "1";
        }

        // Metrics
        if (msg.metrics) {
          updateDashboard(msg.metrics);
          if (msg.metrics.fps !== undefined) {
            fpsValueEl.textContent = msg.metrics.fps;
          }
          if (msg.metrics.session_elapsed_s !== undefined) {
            sessionStartTime =
              Date.now() - msg.metrics.session_elapsed_s * 1000;
          }
        }

        // Camera status
        if (msg.camera_ok === false) {
          cameraOverlay.classList.remove("is-hidden");
          cameraOverlayText.textContent =
            msg.camera_error || "Camera not available";
        }

        // Alert events (one-shot)
        if (msg.alert_event) {
          switch (msg.alert_event) {
            case "LEVEL3_ALARM":
              showAlert("\u{26A0}", "Microsleep detected! Stay awake!", "level-3");
              break;
            case "LEVEL2_ALERT":
              showAlert(
                "\u{26A0}",
                "Fatigue signs detected. Please take a break.",
                "level-2"
              );
              break;
            case "FACE_WARNING":
              showAlert(
                "\u{1F464}",
                "Driver face not visible. Please look at the camera.",
                "level-2"
              );
              break;
          }
        }
      } catch (_) {
        /* ignore malformed messages */
      }
    };

    ws.onclose = () => {
      setConnectionState("error");
      setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      setConnectionState("error");
    };
  }

  connect();
})();
