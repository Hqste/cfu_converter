let pyodide;
const logEl = document.getElementById("log");
const fileEl = document.getElementById("file");
const runBtn = document.getElementById("run");
const sepEl = document.getElementById("sep");
const dlRaw = document.getElementById("dl_raw");
const dlScdl = document.getElementById("dl_scdl");

function log(msg) {
  logEl.textContent += (logEl.textContent ? "\n" : "") + msg;
}

function setDownloadLink(aEl, filename, content) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  aEl.href = url;
  aEl.download = filename;
  aEl.style.display = "inline-block";
}

async function init() {
  pyodide = await loadPyodide();
  logEl.textContent = "Pyodide prêt ✅";
  runBtn.disabled = false;

  // Charger le code python converter.py dans Pyodide
  const pyCode = await fetch("converter.py").then(r => r.text());
  pyodide.FS.writeFile("converter.py", pyCode);
  await pyodide.runPythonAsync("import converter");
}

fileEl.addEventListener("change", () => {
  dlRaw.style.display = "none";
  dlScdl.style.display = "none";
});

runBtn.addEventListener("click", async () => {
  try {
    const file = fileEl.files?.[0];
    if (!file) {
      log("⚠️ Choisis un fichier XML.");
      return;
    }

    logEl.textContent = "";
    log(`Lecture: ${file.name} (${Math.round(file.size/1024/1024*10)/10} MB)`);

    const sep = sepEl.value;

    // Lire le fichier en ArrayBuffer (robuste pour gros fichiers)
    const buf = await file.arrayBuffer();
    const bytes = new Uint8Array(buf);

    // Passer les bytes au python
    pyodide.globals.set("XML_BYTES", bytes);
    pyodide.globals.set("CSV_SEP", sep);

    log("Conversion en cours…");

    const out = await pyodide.runPythonAsync(`
from converter import convert_cfu_bytes
raw_csv, scdl_csv, stats = convert_cfu_bytes(XML_BYTES.to_py(), CSV_SEP)
(raw_csv, scdl_csv, stats)
    `);

    const rawCsv = out.get(0);
    const scdlCsv = out.get(1);
    const stats = out.get(2);

    setDownloadLink(dlRaw, "budget_raw.csv", rawCsv);
    setDownloadLink(dlScdl, "budget_scdl.csv", scdlCsv);

    log("✅ Terminé");
    log("Stats: " + JSON.stringify(stats, null, 2));

    out.destroy?.();
  } catch (e) {
    console.error(e);
    log("❌ Erreur: " + (e?.message || e));
  }
});

init();
