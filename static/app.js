const ipEl = document.getElementById("ip");
const qEl = document.getElementById("questions");
const scoreEl = document.getElementById("score");
const correctionEl = document.getElementById("correction");
const explicationEl = document.getElementById("explication");
const btnCheck = document.getElementById("btnCheck");
const btnNew = document.getElementById("btnNew");
const btnReset = document.getElementById("btnReset");

let inputs = [];

function renderQuestions(labels) {
  qEl.innerHTML = "";
  inputs = [];

  labels.forEach((label, i) => {
    const row = document.createElement("div");
    row.className = "row";

    const lab = document.createElement("label");
    lab.textContent = label + " :";

    const inp = document.createElement("input");
    inp.placeholder = (label.toLowerCase().includes("adresse")) ? "ex: 192.168.1.0" : "ex: 62";
    inp.autocomplete = "off";
    inp.spellcheck = false;

    const res = document.createElement("div");
    res.className = "badge";
    res.id = `res-${i}`;

    row.appendChild(lab);
    row.appendChild(inp);
    row.appendChild(res);

    qEl.appendChild(row);
    inputs.push(inp);
  });
}

async function resetScore() {
  const r = await fetch("/api/reset", { method: "POST" });
  const data = await r.json();

  scoreEl.textContent = `Score total : ${data.score_total}/${data.total_possible}`;
  correctionEl.textContent = "";
  explicationEl.textContent = "";

  // On relance un quiz propre derrière, comme ça l'élève repart sur une nouvelle série.
  await newQuiz();
}

btnReset.addEventListener("click", resetScore);

async function newQuiz() {
  correctionEl.textContent = "";
  explicationEl.textContent = "";
  for (let i = 0; i < 4; i++) {
    const r = document.getElementById(`res-${i}`);
    if (r) r.textContent = "";
  }

  const r = await fetch("/api/new", { method: "POST" });
  const data = await r.json();

  ipEl.textContent = "IP : " + data.ip;
  renderQuestions(data.questions);
  scoreEl.textContent = `Score total : ${data.score_total}/${data.total_possible}`;

  btnCheck.disabled = false;
}

async function checkQuiz() {
  const answers = inputs.map(i => i.value.trim());
  const r = await fetch("/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers })
  });
  const data = await r.json();

  if (data.error) {
    correctionEl.textContent = data.error;
    return;
  }

  data.results.forEach((it, idx) => {
    const res = document.getElementById(`res-${idx}`);
    if (it.correct) {
      res.textContent = "✔ Correct";
      res.className = "badge ok";
    } else {
      res.textContent = "✖ Faux";
      res.className = "badge ko";
    }
  });

  scoreEl.textContent = `Score total : ${data.score_total}/${data.total_possible}`;
  correctionEl.textContent = `Score de la série : ${data.points}/1\n\n` + data.correction_text;
  explicationEl.textContent = data.explanation;

  btnCheck.disabled = true;
}

btnNew.addEventListener("click", newQuiz);
btnCheck.addEventListener("click", checkQuiz);

// Démarrage
newQuiz();
