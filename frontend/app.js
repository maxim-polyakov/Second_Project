const form = document.querySelector("#ask-form");
const questionInput = document.querySelector("#question");
const submitButton = form.querySelector("button[type='submit']");
const emptyState = document.querySelector("#empty-state");
const answerCard = document.querySelector("#answer-card");
const answerNode = document.querySelector("#answer");
const traceCard = document.querySelector("#trace-card");
const traceNode = document.querySelector("#trace");
const errorNode = document.querySelector("#error");

document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.question;
    questionInput.focus();
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const question = questionInput.value.trim();
  if (!question) {
    return;
  }

  setLoading(true);
  clearResult();

  try {
    const response = await fetch("/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question }),
    });

    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "Не удалось получить ответ агента.");
    }

    renderAnswer(payload.answer);
    renderTrace(payload.trace || []);
  } catch (error) {
    renderError(error.message);
  } finally {
    setLoading(false);
  }
});

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.classList.toggle("is-loading", isLoading);
  submitButton.querySelector(".button-text").textContent = isLoading
    ? "Агент думает..."
    : "Запустить агента";
}

function clearResult() {
  emptyState.classList.add("hidden");
  errorNode.classList.add("hidden");
  answerCard.classList.add("hidden");
  traceCard.classList.add("hidden");
  answerNode.textContent = "";
  traceNode.replaceChildren();
}

function renderAnswer(answer) {
  answerNode.textContent = answer;
  answerCard.classList.remove("hidden");
}

function renderTrace(trace) {
  traceNode.replaceChildren();

  if (!trace.length) {
    traceNode.appendChild(createTraceEvent("trace", "Трейс не был возвращен."));
  } else {
    trace.forEach((event) => {
      traceNode.appendChild(createTraceEvent(getEventTitle(event), formatEvent(event)));
    });
  }

  traceCard.classList.remove("hidden");
}

function renderError(message) {
  errorNode.textContent = message;
  errorNode.classList.remove("hidden");
}

function createTraceEvent(title, content) {
  const item = document.createElement("div");
  item.className = "trace-event";

  const titleNode = document.createElement("strong");
  titleNode.textContent = title;

  const contentNode = document.createElement("pre");
  contentNode.textContent = content;

  item.append(titleNode, contentNode);
  return item;
}

function getEventTitle(event) {
  if (event.type === "action") {
    return `Action: ${event.tool || "tool"}`;
  }

  return event.type || "event";
}

function formatEvent(event) {
  if (event.type === "action") {
    return event.input || "";
  }

  return event.content || JSON.stringify(event, null, 2);
}
