/**
 * audio.js — Lightweight alert audio for the Driver Monitoring System.
 *
 * Uses the Web Audio API to generate simple tones (no external audio files
 * needed). Level 2 is a mid-pitch chime; Level 3 is a harsh, repeating
 * alarm. Audio is only permitted after a user gesture (browser policy),
 * which is handled by a one-time unlock on the first click/tap.
 */

(function () {
  "use strict";

  let ctx = null;
  let unlocked = false;
  let activeOscillators = [];

  function ensureContext() {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (ctx.state === "suspended") {
      ctx.resume();
    }
    return ctx;
  }

  /** Unlock audio context on first user interaction. */
  function unlock() {
    if (unlocked) return;
    ensureContext();
    unlocked = true;
    document.removeEventListener("click", unlock);
    document.removeEventListener("touchstart", unlock);
  }
  document.addEventListener("click", unlock);
  document.addEventListener("touchstart", unlock);

  // ---- Tone generators -------------------------------------------------- //

  function playTone(freq, duration, type, gainVal) {
    const ac = ensureContext();
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.type = type || "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(gainVal || 0.15, ac.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + duration);
    osc.connect(gain);
    gain.connect(ac.destination);
    osc.start(ac.currentTime);
    osc.stop(ac.currentTime + duration);
    activeOscillators.push(osc);
    osc.onended = () => {
      activeOscillators = activeOscillators.filter((o) => o !== osc);
    };
  }

  function playLevel2Chime() {
    playTone(880, 0.25, "sine", 0.1);
    setTimeout(() => playTone(660, 0.25, "sine", 0.1), 280);
  }

  function playLevel3Alarm() {
    // Deliberately harsh alternating square/sawtooth pattern for sleep only.
    for (let i = 0; i < 16; i++) {
      const delay = i * 145;
      const high = i % 2 === 0;
      setTimeout(() => playTone(high ? 1380 : 720, 0.13, "square", 0.42), delay);
      setTimeout(() => playTone(high ? 1030 : 540, 0.13, "sawtooth", 0.32), delay);
    }
  }

  function stopAll() {
    activeOscillators.forEach((osc) => {
      try { osc.stop(); } catch (_) { /* already stopped */ }
    });
    activeOscillators = [];
  }

  // ---- Public API ------------------------------------------------------- //

  window.DriverMonitorAudio = {
    playAlert: function (levelClass) {
      if (!unlocked) return;
      if (levelClass === "level-3") {
        playLevel3Alarm();
      } else if (levelClass === "level-2") {
        playLevel2Chime();
      }
    },
    stopAll: stopAll,
  };
})();
