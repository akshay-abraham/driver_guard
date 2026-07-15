/**
 * settings.js — Settings modal controller for the Driver Monitoring System.
 *
 * Two modes:
 *   - Beginner: three big "Scratch-style" dials that map to groups of thresholds.
 *   - Advanced: individual sliders/number inputs for every threshold.
 *
 * Changes are pushed live to the backend via POST /api/config.
 */

(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);

  // ---- DOM refs --------------------------------------------------------- //
  const settingsBtn = $("#settingsBtn");
  const backdrop = $("#settingsBackdrop");
  const closeBtn = $("#closeSettings");

  const beginnerBtn = $("#beginnerModeBtn");
  const advancedBtn = $("#advancedModeBtn");
  const beginnerBody = $("#beginnerBody");
  const advancedBody = $("#advancedBody");

  const eyeSlider = $("#beginnerEyeSensitivity");
  const yawnSlider = $("#beginnerYawnSensitivity");
  const strictnessGroup = $("#beginnerStrictness");
  const resetDefaultsBeginner = $("#resetDefaultsBeginner");
  const resetDefaultsAdvanced = $("#resetDefaultsAdvanced");

  const advancedBlocks = $("#advancedBlocks");

  let currentValues = {};
  let settingsSchema = [];

  // ---- Modal open/close ------------------------------------------------- //

  settingsBtn.addEventListener("click", () => {
    backdrop.classList.add("is-open");
    fetchConfig();
  });

  closeBtn.addEventListener("click", () => backdrop.classList.remove("is-open"));
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.classList.remove("is-open");
  });

  // ---- Mode toggle ------------------------------------------------------ //

  beginnerBtn.addEventListener("click", () => {
    beginnerBtn.classList.add("is-active");
    advancedBtn.classList.remove("is-active");
    beginnerBody.hidden = false;
    advancedBody.hidden = true;
  });

  advancedBtn.addEventListener("click", () => {
    advancedBtn.classList.add("is-active");
    beginnerBtn.classList.remove("is-active");
    advancedBody.hidden = false;
    beginnerBody.hidden = true;
  });

  // ---- Fetch / Push config ---------------------------------------------- //

  function fetchConfig() {
    fetch("/api/config")
      .then((r) => r.json())
      .then((data) => {
        currentValues = data.values || {};
        settingsSchema = data.schema || [];
        renderBeginner();
        renderAdvanced();
      })
      .catch(console.error);
  }

  function pushConfig(values) {
    fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    })
      .then((r) => r.json())
      .then((data) => {
        currentValues = data.values || currentValues;
      })
      .catch(console.error);
  }

  // ---- Beginner mode ---------------------------------------------------- //

  function renderBeginner() {
    // Eye sensitivity maps inversely to ear_threshold (higher slider = lower threshold = more sensitive)
    if (eyeSlider) {
      const ear = currentValues.ear_threshold ?? 0.21;
      // Map ear_threshold 0.14..0.28 -> slider 0..1 (inverted)
      eyeSlider.value = 1 - (ear - 0.14) / (0.28 - 0.14);
    }
    if (yawnSlider) {
      yawnSlider.value = currentValues.mar_threshold ?? 0.6;
    }
    // Strictness = fatigue_score_threshold
    if (strictnessGroup) {
      const fs = currentValues.fatigue_score_threshold ?? 2;
      strictnessGroup.querySelectorAll("button").forEach((btn) => {
        btn.classList.toggle("is-active", parseInt(btn.dataset.value) === fs);
      });
    }
  }

  if (eyeSlider) {
    eyeSlider.addEventListener("input", () => {
      const v = parseFloat(eyeSlider.value);
      const ear = 0.28 - v * (0.28 - 0.14);
      pushConfig({ ear_threshold: Math.round(ear * 100) / 100 });
    });
  }

  if (yawnSlider) {
    yawnSlider.addEventListener("input", () => {
      pushConfig({ mar_threshold: parseFloat(yawnSlider.value) });
    });
  }

  if (strictnessGroup) {
    strictnessGroup.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      strictnessGroup.querySelectorAll("button").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      pushConfig({ fatigue_score_threshold: parseInt(btn.dataset.value) });
    });
  }

  if (resetDefaultsBeginner) {
    resetDefaultsBeginner.addEventListener("click", () => {
      fetch("/api/config/reset", { method: "POST" })
        .then((r) => r.json())
        .then((data) => {
          currentValues = data.values || {};
          renderBeginner();
        });
    });
  }

  // ---- Advanced mode ---------------------------------------------------- //

  function renderAdvanced() {
    if (!advancedBlocks) return;
    advancedBlocks.innerHTML = "";

    let lastGroup = "";
    settingsSchema.forEach((entry) => {
      if (entry.group !== lastGroup) {
        lastGroup = entry.group;
        const title = document.createElement("div");
        title.className = "settings-group-title";
        title.textContent = entry.group;
        advancedBlocks.appendChild(title);
      }

      const block = document.createElement("div");
      block.className = "scratch-block scratch-block--" + entry.group.toLowerCase().replace(/\s+/g, "-");

      const label = document.createElement("div");
      label.className = "scratch-block__label";
      label.textContent = entry.label;
      block.appendChild(label);

      const desc = document.createElement("p");
      desc.className = "scratch-block__desc";
      desc.textContent = entry.description;
      block.appendChild(desc);

      const val = currentValues[entry.key] ?? 0;

      if (entry.kind === "slider") {
        const row = document.createElement("div");
        row.className = "slider-value-row";
        const minLabel = document.createElement("span");
        minLabel.textContent = entry.min + (entry.unit ? " " + entry.unit : "");
        const maxLabel = document.createElement("span");
        maxLabel.textContent = entry.max + (entry.unit ? " " + entry.unit : "");
        const curLabel = document.createElement("span");
        curLabel.className = "current";
        curLabel.textContent = val + (entry.unit ? " " + entry.unit : "");
        row.appendChild(minLabel);
        row.appendChild(curLabel);
        row.appendChild(maxLabel);

        const slider = document.createElement("input");
        slider.type = "range";
        slider.className = "slider";
        slider.min = entry.min;
        slider.max = entry.max;
        slider.step = entry.step;
        slider.value = val;
        slider.addEventListener("input", () => {
          const v = parseFloat(slider.value);
          curLabel.textContent = v + (entry.unit ? " " + entry.unit : "");
          const update = {};
          update[entry.key] = v;
          pushConfig(update);
        });

        block.appendChild(slider);
        block.appendChild(row);
      } else if (entry.kind === "number") {
        const input = document.createElement("input");
        input.type = "number";
        input.className = "num-input";
        input.min = entry.min;
        input.max = entry.max;
        input.step = entry.step;
        input.value = val;
        input.addEventListener("change", () => {
          const update = {};
          update[entry.key] = parseInt(input.value);
          pushConfig(update);
        });
        block.appendChild(input);
      }

      advancedBlocks.appendChild(block);
    });
  }

  if (resetDefaultsAdvanced) {
    resetDefaultsAdvanced.addEventListener("click", () => {
      fetch("/api/config/reset", { method: "POST" })
        .then((r) => r.json())
        .then((data) => {
          currentValues = data.values || {};
          renderBeginner();
          renderAdvanced();
        });
    });
  }
})();
