
document.addEventListener("DOMContentLoaded", () => {
  const documentSelect = document.getElementById("documentSelect");
  const progressPanel = document.getElementById("progressPanel");
  const progressActions = progressPanel?.querySelector(".progress-actions");

  if (!documentSelect || !progressPanel || !progressActions) return;

  const allowedLabs = ["ansible", "bash", "linux", "jenkins"];
  const pathParts = location.pathname.split("/").filter(Boolean);
  const lab = pathParts.find(part => allowedLabs.includes(part));

  if (!lab) return;

  const style = document.createElement("style");

  style.textContent = `
    .df-rating-control {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 3px;
      margin-left: auto;
      padding: 0 8px;
    }

    .df-rating-label {
      color: #cbd5e1;
      font-size: 11px;
      white-space: nowrap;
    }

    .df-rating-stars-row {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .df-star {
      border: 0;
      background: transparent;
      color: #64748b;
      cursor: pointer;
      font-size: 25px;
      line-height: 1;
      padding: 2px;
    }

    .df-star.active,
    .df-star:hover {
      color: #facc15;
    }

    .df-rating-popup {
      display: none;
      position: absolute;
      z-index: 1000;
      top: 195px;
      right: 15px;
      width: 300px;
      padding: 15px;
      background: #172333;
      border: 1px solid #40516a;
      border-radius: 8px;
      box-shadow: 0 8px 25px rgba(0,0,0,.4);
    }

    .df-rating-popup.open {
      display: block;
    }

    .df-rating-popup h4 {
      margin: 0 0 10px;
      color: #fff;
    }

    .df-rating-popup textarea {
      width: 100%;
      min-height: 85px;
      box-sizing: border-box;
      padding: 9px;
      resize: vertical;
      color: #e2e8f0;
      background: #0b1420;
      border: 1px solid #40516a;
      border-radius: 6px;
    }

    .df-rating-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-top: 10px;
    }

    .df-rating-status {
      color: #94a3b8;
      font-size: 11px;
    }

    .df-rating-submit {
      padding: 7px 13px;
      color: #fff;
      background: #2563eb;
      border: 0;
      border-radius: 5px;
      cursor: pointer;
    }

    .df-rating-submit:disabled {
      opacity: .6;
      cursor: not-allowed;
    }
  `;

  document.head.appendChild(style);

  const ratingControl = document.createElement("div");
  ratingControl.className = "df-rating-control";

  ratingControl.innerHTML = `
    <span class="df-rating-label">Rate this lab</span>

    <div class="df-rating-stars-row">
      ${[1, 2, 3, 4, 5].map(value => `
        <button type="button"
                class="df-star"
                data-rating="${value}"
                aria-label="${value} stars">★</button>
      `).join("")}
    </div>
  `;

  progressActions.appendChild(ratingControl);

  const popup = document.createElement("div");
  popup.className = "df-rating-popup";

  popup.innerHTML = `
    <h4>Share your feedback</h4>

    <textarea id="dfRatingComment"
              maxlength="2000"
              placeholder="Share your feedback..."></textarea>

    <div class="df-rating-footer">
      <span class="df-rating-status" id="dfRatingStatus"></span>

      <button type="button"
              class="df-rating-submit"
              id="dfRatingSubmit">Submit</button>
    </div>
  `;

  progressPanel.appendChild(popup);

  const commentInput = document.getElementById("dfRatingComment");
  const submitButton = document.getElementById("dfRatingSubmit");
  const statusText = document.getElementById("dfRatingStatus");

  let selectedRating = 0;
  let currentDocument = "";
  let requestInProgress = false;

  function renderStars(rating) {
    ratingControl.querySelectorAll(".df-star").forEach(button => {
      button.classList.toggle(
        "active",
        Number(button.dataset.rating) <= rating
      );
    });
  }

  function setStatus(message, error = false) {
    statusText.textContent = message;
    statusText.style.color = error ? "#f87171" : "#94a3b8";
  }

  function resetRating() {
    selectedRating = 0;
    renderStars(0);
    commentInput.value = "";
    setStatus("");
    popup.classList.remove("open");
    submitButton.textContent = "Submit";
  }

  async function loadFeedback() {
    const name = documentSelect.value || "";

    currentDocument = name;
    resetRating();

    ratingControl.querySelectorAll(".df-star").forEach(button => {
      button.disabled = !name;
    });

    submitButton.disabled = !name;

    if (!name) return;

    try {
      const params = new URLSearchParams({ lab, name });

      const response = await fetch(
        `/api/documents/feedback?${params}`,
        { credentials: "same-origin" }
      );

      if (!response.ok) {
        throw new Error("Unable to load feedback");
      }

      const data = await response.json();

      if (currentDocument !== name) return;

      selectedRating = Number(data.rating || 0);
      commentInput.value = data.feedback || "";

      renderStars(selectedRating);

      if (selectedRating > 0) {
        submitButton.textContent = "Update";
      }
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  ratingControl.addEventListener("click", event => {
    const button = event.target.closest(".df-star");

    if (!button || button.disabled) return;

    selectedRating = Number(button.dataset.rating);

    renderStars(selectedRating);
    popup.classList.add("open");
    setStatus("");
  });

  submitButton.addEventListener("click", async () => {
    const name = documentSelect.value || "";

    if (!name || name !== currentDocument || requestInProgress) return;

    if (selectedRating < 1 || selectedRating > 5) {
      setStatus("Select a rating first.", true);
      return;
    }

    requestInProgress = true;
    submitButton.disabled = true;
    submitButton.textContent = "Saving...";

    try {
      const response = await fetch("/api/documents/feedback", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          lab,
          name,
          rating: selectedRating,
          feedback: commentInput.value.trim()
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Unable to save feedback");
      }

      setStatus("Feedback saved.");
      submitButton.textContent = "Update";
    } catch (error) {
      setStatus(error.message, true);
      submitButton.textContent = "Submit";
    } finally {
      requestInProgress = false;
      submitButton.disabled = false;
    }
  });

  document.addEventListener("click", event => {
    if (
      !popup.contains(event.target) &&
      !ratingControl.contains(event.target)
    ) {
      popup.classList.remove("open");
    }
  });

  documentSelect.addEventListener("change", loadFeedback);

  const observer = new MutationObserver(() => {
    const name = documentSelect.value || "";

    if (name !== currentDocument) {
      loadFeedback();
    }
  });

  observer.observe(documentSelect, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["selected"]
  });

  loadFeedback();
});
