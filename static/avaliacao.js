const pathParts = location.pathname.split("/").filter(Boolean);

const state = {
  assessmentId: pathParts.length ? pathParts[pathParts.length - 1] : "",
  data: null,
  selectedStudentId: null,
  search: "",
  loading: false,
};

const el = {
  assessmentTitle: document.querySelector("#assessmentTitle"),
  questionCount: document.querySelector("#questionCount"),
  studentCount: document.querySelector("#studentCount"),
  correctedCount: document.querySelector("#correctedCount"),
  pendingCount: document.querySelector("#pendingCount"),
  averageScore: document.querySelector("#averageScore"),
  studentsTable: document.querySelector("#studentsTable"),
  studentSearch: document.querySelector("#studentSearch"),
  downloadSheet: document.querySelector("#downloadSheet"),
  downloadSolution: document.querySelector("#downloadSolution"),
  emptyResult: document.querySelector("#emptyResult"),
  resultContent: document.querySelector("#resultContent"),
  resultSubtitle: document.querySelector("#resultSubtitle"),
  resultStudentId: document.querySelector("#resultStudentId"),
  resultStudentName: document.querySelector("#resultStudentName"),
  resultScore: document.querySelector("#resultScore"),
  resultPercentage: document.querySelector("#resultPercentage"),
  resultCorrect: document.querySelector("#resultCorrect"),
  resultErrors: document.querySelector("#resultErrors"),
  resultBlank: document.querySelector("#resultBlank"),
  questionResults: document.querySelector("#questionResults"),
  pageLoading: document.querySelector("#pageLoading"),
  pageError: document.querySelector("#pageError"),
  pageErrorMessage: document.querySelector("#pageErrorMessage"),
  pageContent: document.querySelector("#pageContent"),
  retryButton: document.querySelector("#retryButton"),
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

function setPageState(view) {
  el.pageLoading.hidden = view !== "loading";
  el.pageError.hidden = view !== "error";
  el.pageContent.hidden = view !== "content";
}

function initials(name) {
  return String(name || "Aluno")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join("")
    .toUpperCase();
}

function formatScore(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "0";
  return Number.isInteger(number) ? String(number) : number.toFixed(2);
}

function filteredStudents() {
  if (!state.data || !Array.isArray(state.data.students)) return [];

  const search = state.search.trim().toLowerCase();

  if (!search) return state.data.students;

  return state.data.students.filter(student =>
    String(student.name || "").toLowerCase().includes(search)
    || String(student.id || "").toLowerCase().includes(search)
  );
}

function renderSummary() {
  const { assessment, summary } = state.data;

  el.assessmentTitle.textContent = assessment.title || "Avaliação";
  document.title = `${assessment.title || "Avaliação"} — Avaliação`;

  el.questionCount.textContent = assessment.question_count ?? 0;
  el.studentCount.textContent = summary.total_students ?? 0;
  el.correctedCount.textContent = summary.corrected ?? 0;
  el.pendingCount.textContent = summary.pending ?? 0;
  el.averageScore.textContent =
    `${formatScore(summary.average_score)} / ${formatScore(assessment.maximum_score)}`;

  el.downloadSheet.href = state.data.downloads.answer_sheet;
  el.downloadSolution.href = state.data.downloads.solution;
}

function createStudentRow(student) {
  const row = document.createElement("tr");

  if (student.id === state.selectedStudentId) {
    row.classList.add("selected");
  }

  const studentCell = document.createElement("td");
  const studentWrap = document.createElement("div");
  studentWrap.className = "student-name";

  const avatar = document.createElement("span");
  avatar.className = "avatar";
  avatar.textContent = initials(student.name);

  const identity = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = student.name || "Aluno";
  const id = document.createElement("span");
  id.textContent = student.id || "Sem matrícula";
  identity.append(name, id);
  studentWrap.append(avatar, identity);
  studentCell.append(studentWrap);

  const isCorrected =
    student.status === "corrected"
    && student.result
    && typeof student.result === "object";

  const statusCell = document.createElement("td");
  const status = document.createElement("span");
  status.className = `status-pill ${isCorrected ? "corrected" : "pending"}`;
  status.textContent = isCorrected ? "Corrigida" : "Pendente";
  statusCell.append(status);

  const resultCell = document.createElement("td");

  if (isCorrected) {
    const resultButton = document.createElement("button");
    resultButton.type = "button";
    resultButton.className = "result-mini";
    resultButton.textContent =
      `${student.result.correct ?? 0}/${student.result.total ?? 0} · `
      + `${formatScore(student.result.score)}`;
    resultButton.addEventListener("click", () => selectStudent(student.id));
    resultCell.append(resultButton);
  } else {
    resultCell.textContent = "—";
  }

  const uploadCell = document.createElement("td");
  const uploadLabel = document.createElement("label");
  uploadLabel.className = "upload-label";

  const labelText = document.createElement("span");
  labelText.textContent = isCorrected ? "Substituir folha" : "Anexar folha";

  const uploadInput = document.createElement("input");
  uploadInput.type = "file";
  uploadInput.accept = "application/pdf,image/png,image/jpeg,.pdf,.png,.jpg,.jpeg";
  uploadInput.addEventListener("change", event => {
    const [file] = event.target.files;
    if (file) uploadSheet(student, file, uploadLabel, labelText);
    event.target.value = "";
  });

  uploadLabel.append(labelText, uploadInput);
  uploadCell.append(uploadLabel);

  row.addEventListener("click", event => {
    if (event.target.closest(".upload-label")) return;
    if (isCorrected) selectStudent(student.id);
  });

  row.append(studentCell, statusCell, resultCell, uploadCell);
  return row;
}

function renderStudents() {
  el.studentsTable.replaceChildren();
  const students = filteredStudents();

  if (!students.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.textContent = "Nenhum aluno encontrado.";
    cell.style.textAlign = "center";
    cell.style.color = "#667085";
    row.append(cell);
    el.studentsTable.append(row);
    return;
  }

  for (const student of students) {
    el.studentsTable.append(createStudentRow(student));
  }
}

function selectStudent(studentId) {
  const student = state.data.students.find(item => item.id === studentId);

  if (!student || !student.result) return;

  state.selectedStudentId = studentId;
  renderStudents();
  renderResult(student);
}

function renderResult(student) {
  const result = student.result || {};

  el.emptyResult.hidden = true;
  el.resultContent.hidden = false;
  el.resultSubtitle.textContent = "Detalhamento da correção automática.";
  el.resultStudentId.textContent = student.id || "";
  el.resultStudentName.textContent = student.name || "Aluno";
  el.resultScore.textContent =
    `${formatScore(result.score)} / ${formatScore(result.maximum_score)}`;
  el.resultPercentage.textContent = `${formatScore(result.percentage)}%`;
  el.resultCorrect.textContent = result.correct ?? 0;
  el.resultErrors.textContent = result.errors ?? 0;
  el.resultBlank.textContent = result.blank ?? 0;

  el.questionResults.replaceChildren();
  const details = Array.isArray(result.details) ? result.details : [];

  for (const detail of details) {
    const chip = document.createElement("article");
    chip.className = "question-chip";

    if (detail.is_correct) {
      chip.classList.add("correct");
    } else if (detail.is_blank) {
      chip.classList.add("blank");
    } else {
      chip.classList.add("incorrect");
    }

    const title = document.createElement("strong");
    title.textContent = `Q${detail.question}`;

    const text = document.createElement("span");

    if (detail.is_correct) {
      text.textContent = `${detail.selected} · correta`;
    } else if (detail.is_blank) {
      text.textContent = `Em branco · correta ${detail.correct_answer}`;
    } else {
      text.textContent = `${detail.selected || "—"} · correta ${detail.correct_answer}`;
    }

    chip.append(title, text);
    el.questionResults.append(chip);
  }
}

async function fetchJsonWithTimeout(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      cache: "no-store",
      headers: {
        "Accept": "application/json",
        ...(options.headers || {}),
      },
    });

    const text = await response.text();
    let result = {};

    try {
      result = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(
        `O servidor retornou uma resposta inválida (${response.status}).`
      );
    }

    if (!response.ok) {
      throw new Error(
        result.detail || `Erro ${response.status} ao acessar a avaliação.`
      );
    }

    return result;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("O servidor demorou demais para responder.");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function uploadSheet(student, file, label, labelText) {
  const data = new FormData();
  data.append("file", file);

  label.classList.add("busy");
  const previousText = labelText.textContent;
  labelText.textContent = "Processando...";

  try {
    const result = await fetchJsonWithTimeout(
      `/api/avaliacoes/${encodeURIComponent(state.assessmentId)}`
      + `/alunos/${encodeURIComponent(student.id)}/upload`,
      {
        method: "POST",
        body: data,
      },
      190000
    );

    await refreshData(false);
    state.selectedStudentId = student.id;
    renderStudents();

    const updatedStudent = state.data.students.find(
      item => item.id === student.id
    );

    if (updatedStudent && updatedStudent.result) {
      renderResult(updatedStudent);
    }

    showToast(result.message || "Folha corrigida.");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    label.classList.remove("busy");
    labelText.textContent = previousText;
  }
}

async function refreshData(renderCurrent = true) {
  if (!state.assessmentId) {
    throw new Error("Identificador da avaliação não encontrado no endereço.");
  }

  const result = await fetchJsonWithTimeout(
    `/api/avaliacoes/${encodeURIComponent(state.assessmentId)}`
  );

  if (
    !result.assessment
    || !Array.isArray(result.students)
    || !result.summary
    || !result.downloads
  ) {
    throw new Error("Os dados retornados pela avaliação estão incompletos.");
  }

  state.data = result;
  renderSummary();
  renderStudents();

  if (renderCurrent && state.selectedStudentId) {
    const selected = state.data.students.find(
      student => student.id === state.selectedStudentId
    );

    if (selected && selected.result) {
      renderResult(selected);
    }
  }
}

async function loadPage() {
  if (state.loading) return;

  state.loading = true;
  setPageState("loading");

  try {
    await refreshData();
    setPageState("content");
  } catch (error) {
    el.assessmentTitle.textContent = "Erro ao carregar avaliação";
    el.pageErrorMessage.textContent =
      error.message || "Erro desconhecido ao carregar a avaliação.";
    setPageState("error");
    showToast(el.pageErrorMessage.textContent, "error");
  } finally {
    state.loading = false;
  }
}

el.studentSearch.addEventListener("input", event => {
  state.search = event.target.value;
  renderStudents();
});

el.retryButton.addEventListener("click", loadPage);

loadPage();
