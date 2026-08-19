const state = {
  questions: [],
  currentQuestion: 0,
};

const el = {
  titleInput: document.querySelector("#titleInput"),
  questionCount: document.querySelector("#questionCount"),
  defaultOptions: document.querySelector("#defaultOptions"),
  pointsPerQuestion: document.querySelector("#pointsPerQuestion"),
  buildQuestions: document.querySelector("#buildQuestions"),
  questionsGrid: document.querySelector("#questionsGrid"),
  currentQuestionLabel: document.querySelector("#currentQuestionLabel"),
  currentOptions: document.querySelector("#currentOptions"),
  previousQuestion: document.querySelector("#previousQuestion"),
  nextQuestion: document.querySelector("#nextQuestion"),
  answeredCount: document.querySelector("#answeredCount"),
  remainingCount: document.querySelector("#remainingCount"),
  saveAssessment: document.querySelector("#saveAssessment"),
  formMessage: document.querySelector("#formMessage"),
  statusBadge: document.querySelector("#statusBadge"),
  resultsPanel: document.querySelector("#resultsPanel"),
  resultId: document.querySelector("#resultId"),
  downloadSheet: document.querySelector("#downloadSheet"),
  downloadSolution: document.querySelector("#downloadSolution"),
  downloadZip: document.querySelector("#downloadZip"),
  downloadKey: document.querySelector("#downloadKey"),
  downloadTemplate: document.querySelector("#downloadTemplate"),
  openAssessment: document.querySelector("#openAssessment"),
  previewTitle: document.querySelector("#previewTitle"),
  previewCount: document.querySelector("#previewCount"),
  sheetQuestions: document.querySelector("#sheetQuestions"),
};

function makeOptions(count) {
  return Array.from({ length: count }, (_, index) =>
    String.fromCharCode("A".charCodeAt(0) + index)
  );
}

function createQuestions() {
  const count = Math.max(1, Math.min(100, Number(el.questionCount.value) || 1));
  const defaultCount = Number(el.defaultOptions.value);
  const previous = state.questions;

  state.questions = Array.from({ length: count }, (_, index) => {
    const existing = previous[index];

    return {
      number: index + 1,
      option_count: existing?.option_count ?? defaultCount,
      answer: existing?.answer ?? "",
    };
  });

  state.currentQuestion = Math.min(state.currentQuestion, count - 1);
  renderAll();
  setMessage("");
  el.resultsPanel.hidden = true;
}

function selectAnswer(questionIndex, answer) {
  const question = state.questions[questionIndex];
  if (!question) return;

  question.answer = answer;
  state.currentQuestion = questionIndex;
  renderAll();
}

function changeOptionCount(questionIndex, optionCount) {
  const question = state.questions[questionIndex];
  if (!question) return;

  question.option_count = optionCount;

  if (!makeOptions(optionCount).includes(question.answer)) {
    question.answer = "";
  }

  state.currentQuestion = questionIndex;
  renderAll();
}

function renderQuestionCard(question, index) {
  const card = document.createElement("article");
  card.className = "question-card";

  if (index === state.currentQuestion) card.classList.add("active");
  if (question.answer) card.classList.add("answered");

  card.addEventListener("click", () => {
    state.currentQuestion = index;
    renderAll();
  });

  const top = document.createElement("div");
  top.className = "question-top";

  const number = document.createElement("span");
  number.className = "question-number";
  number.textContent = `Questão ${question.number}`;

  const select = document.createElement("select");
  select.className = "question-options-select";
  select.setAttribute("aria-label", `Quantidade de alternativas da questão ${question.number}`);

  for (let count = 2; count <= 5; count += 1) {
    const option = document.createElement("option");
    option.value = String(count);
    option.textContent = `${count} opções`;
    option.selected = count === question.option_count;
    select.append(option);
  }

  select.addEventListener("click", event => event.stopPropagation());
  select.addEventListener("change", event => {
    event.stopPropagation();
    changeOptionCount(index, Number(event.target.value));
  });

  top.append(number, select);

  const answerRow = document.createElement("div");
  answerRow.className = "question-answer-row";

  for (const option of makeOptions(question.option_count)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "answer-option";
    button.textContent = option;

    if (question.answer === option) button.classList.add("selected");

    button.addEventListener("click", event => {
      event.stopPropagation();
      selectAnswer(index, option);
    });

    answerRow.append(button);
  }

  card.append(top, answerRow);
  return card;
}

function renderGrid() {
  el.questionsGrid.replaceChildren();

  for (const [index, question] of state.questions.entries()) {
    el.questionsGrid.append(renderQuestionCard(question, index));
  }

  const activeCard = el.questionsGrid.children[state.currentQuestion];
  activeCard?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function renderCurrentToolbar() {
  const question = state.questions[state.currentQuestion];
  el.currentOptions.replaceChildren();

  if (!question) {
    el.currentQuestionLabel.textContent = "Sem questões";
    return;
  }

  el.currentQuestionLabel.textContent = `Questão ${question.number}`;

  for (const option of makeOptions(question.option_count)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "answer-option";
    button.textContent = option;

    if (question.answer === option) button.classList.add("selected");

    button.addEventListener("click", () => {
      selectAnswer(state.currentQuestion, option);
      moveToQuestion(Math.min(state.questions.length - 1, state.currentQuestion + 1));
    });

    el.currentOptions.append(button);
  }

  el.previousQuestion.disabled = state.currentQuestion <= 0;
  el.nextQuestion.disabled = state.currentQuestion >= state.questions.length - 1;
}

function previewColumns(questionCount) {
  if (questionCount <= 25) return 1;
  if (questionCount <= 50) return 2;
  if (questionCount <= 75) return 3;
  return 4;
}

function renderSheetPreview() {
  const title = el.titleInput.value.trim() || "Novo simulado";
  el.previewTitle.textContent = title;
  el.previewCount.textContent = `${state.questions.length} questões`;
  el.sheetQuestions.replaceChildren();

  const columns = previewColumns(state.questions.length);
  el.sheetQuestions.style.setProperty("--sheet-columns", String(columns));

  for (const question of state.questions) {
    const row = document.createElement("div");
    row.className = "sheet-question";

    const number = document.createElement("span");
    number.className = "sheet-number";
    number.textContent = String(question.number);

    row.append(number);

    for (const option of makeOptions(question.option_count)) {
      const optionWrap = document.createElement("span");
      optionWrap.className = "sheet-option";

      const bubble = document.createElement("span");
      bubble.className = "sheet-bubble";

      const letter = document.createElement("span");
      letter.textContent = option;

      optionWrap.append(bubble, letter);
      row.append(optionWrap);
    }

    el.sheetQuestions.append(row);
  }
}

function renderSummary() {
  const answered = state.questions.filter(question => question.answer).length;
  el.answeredCount.textContent = String(answered);
  el.remainingCount.textContent = String(state.questions.length - answered);

  el.statusBadge.textContent =
    answered === state.questions.length && state.questions.length
      ? "Gabarito completo"
      : "Rascunho";
}

function renderAll() {
  renderGrid();
  renderCurrentToolbar();
  renderSummary();
  renderSheetPreview();
}

function moveToQuestion(index) {
  state.currentQuestion = Math.max(0, Math.min(state.questions.length - 1, index));
  renderAll();
}

function setMessage(message, type = "") {
  el.formMessage.textContent = message;
  el.formMessage.className = `form-message ${type}`.trim();
}

function validateForm() {
  if (!el.titleInput.value.trim()) {
    return "Informe o título do simulado.";
  }

  const missing = state.questions
    .filter(question => !question.answer)
    .map(question => question.number);

  if (missing.length) {
    return `Marque o gabarito das questões: ${missing.join(", ")}.`;
  }

  const points = Number(el.pointsPerQuestion.value);

  if (!Number.isFinite(points) || points <= 0) {
    return "Informe um valor positivo por questão.";
  }

  return "";
}

async function saveAssessment() {
  const validationMessage = validateForm();

  if (validationMessage) {
    setMessage(validationMessage, "error");
    return;
  }

  const payload = {
    title: el.titleInput.value.trim(),
    points_per_question: Number(el.pointsPerQuestion.value),
    questions: state.questions.map(question => ({
      option_count: question.option_count,
      answer: question.answer,
    })),
  };

  el.saveAssessment.disabled = true;
  setMessage("Gerando a folha de respostas e os arquivos OMR...");

  try {
    const response = await fetch("/api/avaliacoes", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.detail || "Não foi possível criar o simulado.");
    }

    el.resultId.textContent = `ID: ${result.id}`;
    el.downloadSheet.href = result.downloads.answer_sheet;
    el.downloadSolution.href = result.downloads.solution;
    el.downloadZip.href = result.downloads.zip;
    el.downloadZip.download = `${result.id}.zip`;
    el.downloadKey.href = result.downloads.answer_key;
    el.downloadTemplate.href = result.downloads.template;
    el.openAssessment.href = result.details_url;

    el.resultsPanel.hidden = false;
    el.statusBadge.textContent = "Salva";
    setMessage(result.message, "success");
    el.resultsPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    el.saveAssessment.disabled = false;
  }
}

el.defaultOptions.addEventListener("change", () => {
  const optionCount = Number(el.defaultOptions.value);
  const allowedOptions = makeOptions(optionCount);

  state.questions = state.questions.map(question => ({
    ...question,
    option_count: optionCount,
    answer: allowedOptions.includes(question.answer)
      ? question.answer
      : "",
  }));

  renderAll();
  setMessage("");
  el.resultsPanel.hidden = true;
});

el.titleInput.addEventListener("input", renderSheetPreview);
el.buildQuestions.addEventListener("click", createQuestions);
el.previousQuestion.addEventListener("click", () => moveToQuestion(state.currentQuestion - 1));
el.nextQuestion.addEventListener("click", () => moveToQuestion(state.currentQuestion + 1));
el.saveAssessment.addEventListener("click", saveAssessment);

createQuestions();
