const state = {
  data: null,
  search: "",
  filter: "all",
  loading: false,
};

const el = {
  totalAssessments: document.querySelector("#totalAssessments"),
  totalStudents: document.querySelector("#totalStudents"),
  totalCorrected: document.querySelector("#totalCorrected"),
  totalPending: document.querySelector("#totalPending"),
  assessmentSearch: document.querySelector("#assessmentSearch"),
  statusFilter: document.querySelector("#statusFilter"),
  loadingState: document.querySelector("#loadingState"),
  errorState: document.querySelector("#errorState"),
  errorMessage: document.querySelector("#errorMessage"),
  retryButton: document.querySelector("#retryButton"),
  emptyState: document.querySelector("#emptyState"),
  assessmentsGrid: document.querySelector("#assessmentsGrid"),
  toast: document.querySelector("#toast"),
};

let toastTimer = null;

function showToast(message, type = "") {
  clearTimeout(toastTimer);
  el.toast.textContent = message;
  el.toast.className = `toast visible ${type}`.trim();

  toastTimer = setTimeout(() => {
    el.toast.className = "toast";
  }, 4200);
}

function setView(view) {
  el.loadingState.hidden = view !== "loading";
  el.errorState.hidden = view !== "error";
  el.emptyState.hidden = view !== "empty";
  el.assessmentsGrid.hidden = view !== "list";
}

function formatDate(value) {
  if (!value) return "Data não informada";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return value;

  try {
    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  } catch {
    return date.toLocaleString("pt-BR");
  }
}

function formatNumber(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) return "0";

  return Number.isInteger(number) ? String(number) : number.toFixed(2);
}

function assessmentStatus(assessment) {
  if (assessment.students.corrected === 0) return "empty";
  if (assessment.students.pending === 0) return "completed";
  return "pending";
}

function statusLabel(status) {
  if (status === "completed") return "Concluída";
  if (status === "empty") return "Sem correções";
  return "Em andamento";
}

function filteredAssessments() {
  if (!state.data) return [];

  const search = state.search.trim().toLowerCase();

  return state.data.assessments.filter(assessment => {
    const title = String(assessment.title || "").toLowerCase();
    const id = String(assessment.id || "").toLowerCase();

    const matchesSearch =
      !search
      || title.includes(search)
      || id.includes(search);

    const status = assessmentStatus(assessment);
    const matchesFilter =
      state.filter === "all"
      || state.filter === status;

    return matchesSearch && matchesFilter;
  });
}

function renderSummary() {
  const summary = state.data?.summary || {};

  el.totalAssessments.textContent = summary.total ?? 0;
  el.totalStudents.textContent = summary.total_students ?? 0;
  el.totalCorrected.textContent = summary.corrected ?? 0;
  el.totalPending.textContent = summary.pending ?? 0;
}

function createAssessmentCard(assessment) {
  const card = document.createElement("article");
  card.className = "assessment-card";

  const heading = document.createElement("div");
  heading.className = "card-heading";

  const titleWrap = document.createElement("div");
  titleWrap.className = "card-title";

  const title = document.createElement("h3");
  title.textContent = assessment.title || "Avaliação sem título";

  const date = document.createElement("span");
  date.textContent = formatDate(assessment.created_at);

  titleWrap.append(title, date);

  const status = assessmentStatus(assessment);
  const statusPill = document.createElement("span");
  statusPill.className = `status-pill ${status}`;
  statusPill.textContent = statusLabel(status);

  heading.append(titleWrap, statusPill);

  const metrics = document.createElement("div");
  metrics.className = "card-metrics";

  const metricItems = [
    ["Questões", assessment.question_count ?? 0],
    ["Nota máxima", formatNumber(assessment.maximum_score)],
    ["Média", formatNumber(assessment.average_score)],
  ];

  for (const [label, value] of metricItems) {
    const metric = document.createElement("div");
    metric.className = "metric";

    const metricLabel = document.createElement("span");
    metricLabel.textContent = label;

    const metricValue = document.createElement("strong");
    metricValue.textContent = value;

    metric.append(metricLabel, metricValue);
    metrics.append(metric);
  }

  const progressBlock = document.createElement("div");
  progressBlock.className = "progress-block";

  const progressLabel = document.createElement("div");
  progressLabel.className = "progress-label";

  const totalStudents = Number(assessment.students?.total || 0);
  const correctedStudents = Number(assessment.students?.corrected || 0);

  const progressText = document.createElement("span");
  progressText.textContent =
    `${correctedStudents} de ${totalStudents} corrigidas`;

  const percentage = totalStudents
    ? Math.round((correctedStudents / totalStudents) * 100)
    : 0;

  const percentageLabel = document.createElement("span");
  percentageLabel.textContent = `${percentage}%`;

  progressLabel.append(progressText, percentageLabel);

  const progressTrack = document.createElement("div");
  progressTrack.className = "progress-track";

  const progressBar = document.createElement("div");
  progressBar.className = "progress-bar";
  progressBar.style.width = `${percentage}%`;

  progressTrack.append(progressBar);
  progressBlock.append(progressLabel, progressTrack);

  const actions = document.createElement("div");
  actions.className = "card-actions";

  const openLink = document.createElement("a");
  openLink.className = "open-button";
  openLink.href = assessment.details_url;
  openLink.textContent = "Abrir avaliação";

  const sheetLink = document.createElement("a");
  sheetLink.href = assessment.downloads.answer_sheet;
  sheetLink.target = "_blank";
  sheetLink.rel = "noopener";
  sheetLink.textContent = "Folha";

  const solutionLink = document.createElement("a");
  solutionLink.href = assessment.downloads.solution;
  solutionLink.target = "_blank";
  solutionLink.rel = "noopener";
  solutionLink.textContent = "Solução";

  actions.append(openLink, sheetLink, solutionLink);
  card.append(heading, metrics, progressBlock, actions);

  return card;
}

function renderAssessments() {
  const assessments = filteredAssessments();
  el.assessmentsGrid.replaceChildren();

  if (!state.data.assessments.length) {
    setView("empty");
    return;
  }

  setView("list");

  if (!assessments.length) {
    const message = document.createElement("div");
    message.className = "state-box";
    message.style.gridColumn = "1 / -1";

    const strong = document.createElement("strong");
    strong.textContent = "Nenhuma avaliação encontrada";

    const span = document.createElement("span");
    span.textContent = "Tente alterar a busca ou o filtro selecionado.";

    message.append(strong, span);
    el.assessmentsGrid.append(message);
    return;
  }

  for (const assessment of assessments) {
    el.assessmentsGrid.append(createAssessmentCard(assessment));
  }
}

async function fetchJsonWithTimeout(url, timeoutMs = 12000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      cache: "no-store",
      headers: {
        "Accept": "application/json",
      },
    });

    const text = await response.text();
    let result = {};

    try {
      result = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(
        `O servidor respondeu com conteúdo inválido (${response.status}).`
      );
    }

    if (!response.ok) {
      throw new Error(
        result.detail || `Erro ${response.status} ao carregar avaliações.`
      );
    }

    return result;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(
        "O servidor demorou demais para responder. Reinicie o servidor e tente novamente."
      );
    }

    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function loadAssessments() {
  if (state.loading) return;

  state.loading = true;
  setView("loading");

  try {
    const result = await fetchJsonWithTimeout("/api/avaliacoes");

    if (!Array.isArray(result.assessments) || !result.summary) {
      throw new Error("A resposta da API de avaliações está incompleta.");
    }

    state.data = result;
    renderSummary();
    renderAssessments();
  } catch (error) {
    el.errorMessage.textContent =
      error.message || "Erro desconhecido ao carregar as avaliações.";
    setView("error");
    showToast(el.errorMessage.textContent, "error");
  } finally {
    state.loading = false;
  }
}

el.assessmentSearch.addEventListener("input", event => {
  state.search = event.target.value;
  renderAssessments();
});

el.statusFilter.addEventListener("change", event => {
  state.filter = event.target.value;
  renderAssessments();
});

el.retryButton.addEventListener("click", loadAssessments);

loadAssessments();
