import { useState, useRef, useEffect, useCallback } from "react";
import "./App.css";

const API_BASE = "http://localhost:5000/api";

/* ── Severity Helpers ──────────────────────────────────────── */
function getRiskLevel(defect) {
  const risk = defect?.risk_level;
  if (risk === 1) return 1;
  if (risk === 2) return 2;
  if (risk === 4) return 4;
  return 3;
}

function getSevFromDefectType(type = "") {
  const t = type.toLowerCase();
  if (t.includes("rivet")) return 1;
  if (t.includes("crack")) return 2;
  if (t.includes("corrosion") || t.includes("dent")) return 3;
  return 4;
}

function getSevClass(level) {
  return `sev-${level}`;
}

/* ── Clock ─────────────────────────────────────────────────── */
function useClock() {
  const [time, setTime] = useState("");
  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString("en-GB", { hour12: false }));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return time;
}

/* ═══════════════════════════════════════════════════════════ */
export default function App() {
  const [stage, setStage] = useState("upload");
  const [imagePreview, setImagePreview] = useState(null);
  const [detections, setDetections] = useState([]);
  const [selectedDefect, setSelectedDefect] = useState(null);
  const [procedure, setProcedure] = useState(null);
  const [aircraftId, setAircraftId] = useState("VT-AXM-7741");
  const [inspectorName, setInspectorName] = useState("");
  const [notes, setNotes] = useState("");
  const [reportUrl, setReportUrl] = useState(null);
  const [reportId, setReportId] = useState(null);
  const [modelMode, setModelMode] = useState(null);
  const [activeTab, setActiveTab] = useState("procedure");
  const [historyList, setHistoryList] = useState([]);
  const [historyFilter, setHistoryFilter] = useState("all");
  const [stats, setStats] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [backendOnline, setBackendOnline] = useState(null);
  const [loaderStep, setLoaderStep] = useState(0);

  const imageRef = useRef(null);
  const fileInputRef = useRef(null);
  const [scale, setScale] = useState({ x: 1, y: 1 });

  const clock = useClock();

  /* ── Scale ──────────────────────────────────────────────── */
  const updateBBoxScale = useCallback(() => {
    if (!imageRef.current) return;
    const { width, height, naturalWidth, naturalHeight } = imageRef.current;
    if (naturalWidth && naturalHeight) {
      setScale({ x: width / naturalWidth, y: height / naturalHeight });
    }
  }, []);

  /* ── Backend health check ───────────────────────────────── */
  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((r) => r.ok ? setBackendOnline(true) : setBackendOnline(false))
      .catch(() => setBackendOnline(false));
  }, []);

  /* ── Fetch history + stats ──────────────────────────────── */
  const fetchData = useCallback(async () => {
    try {
      const [hRes, sRes] = await Promise.all([
        fetch(`${API_BASE}/history?per_page=50`),
        fetch(`${API_BASE}/stats`),
      ]);
      const hData = await hRes.json();
      const sData = await sRes.json();
      if (hData.status === "success") setHistoryList(hData.history || []);
      if (sData.status === "success") setStats(sData);
    } catch (_) {}
  }, []);

  useEffect(() => {
    window.addEventListener("resize", updateBBoxScale);
    fetchData();
    return () => window.removeEventListener("resize", updateBBoxScale);
  }, [imagePreview, stage, updateBBoxScale, fetchData]);

  /* ── File processing ────────────────────────────────────── */
  async function processFile(file) {
    if (!file) return;
    setImagePreview(URL.createObjectURL(file));
    setStage("detecting");
    setLoaderStep(0);

    const stepInterval = setInterval(() => setLoaderStep((p) => Math.min(p + 1, 2)), 900);
    const formData = new FormData();
    formData.append("image", file);

    try {
      const res = await fetch(`${API_BASE}/scan`, { method: "POST", body: formData });
      clearInterval(stepInterval);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Scan failed");

      const found = data.detections || [];
      setDetections(found);
      setModelMode(data.model_mode);
      setStage("detected");
      if (found.length > 0) handleSelectDefect(found[0]);
    } catch (err) {
      clearInterval(stepInterval);
      console.error(err);
      setStage("upload");
      alert("Could not reach AeroScribe backend. Is Flask running on port 5000?");
    }
  }

  function handleFileChange(e) { processFile(e.target.files[0]); }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) processFile(file);
  }

  /* ── Defect select → RAG retrieve ──────────────────────── */
  async function handleSelectDefect(defect) {
    setSelectedDefect(defect);
    setStage("retrieving");
    try {
      const res = await fetch(`${API_BASE}/retrieve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ defect_type: defect.label }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Retrieval failed");
      setProcedure(data.procedure);
      setStage("verify");
      setActiveTab("procedure");
    } catch (err) {
      console.error(err);
      setStage("detected");
    }
  }

  /* ── Generate report ────────────────────────────────────── */
  async function handleGenerateReport() {
    setStage("generating");
    try {
      const res = await fetch(`${API_BASE}/generate-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          defect: selectedDefect,
          amm_id: procedure.id,
          inspector_notes: notes || "Inspector verified AI recommendation. No discrepancies noted.",
          inspector_name: inspectorName,
          aircraft_id: aircraftId,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Report generation failed");
      setReportUrl(`http://localhost:5000${data.download_url}`);
      setReportId(data.report_id);
      setStage("done");
      fetchData();
    } catch (err) {
      console.error(err);
      setStage("verify");
      alert("Report generation failed.");
    }
  }

  /* ── Reset ──────────────────────────────────────────────── */
  function resetFlow() {
    setStage("upload");
    setImagePreview(null);
    setDetections([]);
    setSelectedDefect(null);
    setProcedure(null);
    setReportUrl(null);
    setReportId(null);
    setNotes("");
    setInspectorName("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  /* ── Filtered history ───────────────────────────────────── */
  const filteredHistory = historyFilter === "all"
    ? historyList
    : historyList.filter((h) => h.defect_type === historyFilter);

  const defectTypes = [...new Set(historyList.map((h) => h.defect_type))];

  /* ── Aircraft ID validation ─────────────────────────────── */
  const aircraftIdValid = /^[A-Z0-9\-]{3,12}$/i.test(aircraftId);

  /* ── Stage order for progress bar ──────────────────────── */
  const stageOrder = ["upload", "detecting", "detected", "retrieving", "verify", "generating", "done"];
  const stageIdx = stageOrder.indexOf(stage);

  const progressSteps = [
    { key: "upload",    label: "Capture",   desc: "Image Ingestion" },
    { key: "detected",  label: "Detect",    desc: "AI Inference" },
    { key: "verify",    label: "Reference", desc: "AMM Retrieval" },
    { key: "done",      label: "Document",  desc: "NRF Report" },
  ];

  /* ═════════════════ RENDER ══════════════════════════════ */
  return (
    <div className="app">

      {/* ── Header ───────────────────────────────────────── */}
      <header className="header">
        <div className="header-brand">
          <div className="brand-icon-wrap">
            <PlaneIcon size={22} />
          </div>
          <div className="brand-text">
            <div className="brand-name">AEROSCRIBE</div>
            <div className="brand-sub">MRO Maintenance Control System</div>
          </div>
        </div>

        <div className="header-right">
          <div className={`header-chip ${backendOnline === false ? "chip-stat" : "chip-online"}`}>
            <div className="chip-dot" />
            {backendOnline === null ? "CONNECTING…" : backendOnline ? "BACKEND ONLINE" : "BACKEND OFFLINE"}
          </div>
          <div className="header-chip chip-stat">
            <DatabaseIcon size={12} />
            {historyList.length} INSPECTIONS
          </div>
          <div className="header-clock">{clock}</div>
        </div>
      </header>

      {/* ── Progress Timeline ────────────────────────────── */}
      <div className="progress-track">
        {progressSteps.map((s) => (
          <div
            key={s.key}
            className={`progress-step ${stageIdx >= stageOrder.indexOf(s.key) ? "active" : ""}`}
          >
            <div className="step-num">{progressSteps.indexOf(s) + 1}</div>
            <div className="step-info">
              <div className="step-label">{s.label}</div>
              <div className="step-desc">{s.desc}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Dashboard Grid ───────────────────────────────── */}
      <div className="dashboard-layout">

        {/* ── LEFT: Visualizer HUD ──────────────────────── */}
        <div className="visualizer-card">
          {/* Topbar */}
          <div className="visualizer-topbar">
            <div className="visualizer-label">
              <ScanIcon size={14} />
              SURFACE SCAN FEED
            </div>
            <div className="visualizer-meta">
              {imagePreview && (
                <>
                  <span className="vis-meta-item">
                    {modelMode === "custom_trained" ? "CUSTOM MODEL" : "DEMO MODE"}
                  </span>
                  <span className="vis-meta-item">
                    {new Date().toLocaleDateString("en-GB")}
                  </span>
                </>
              )}
              <span className="vis-meta-item">AEROSCRIBE/1.0</span>
            </div>
          </div>

          {/* HUD corner brackets */}
          <div className="hud-overlay">
            <div className="hud-corner hud-tl" />
            <div className="hud-corner hud-tr" />
            <div className="hud-corner hud-bl" />
            <div className="hud-corner hud-br" />
          </div>

          {/* Detection count badge */}
          {detections.length > 0 && (
            <div className="detection-badge">
              <span className="detection-badge-count">{detections.length}</span>
              ANOMALY{detections.length !== 1 ? "S" : ""} DETECTED
            </div>
          )}

          {/* Image Viewport */}
          <div className="image-viewport">
            {imagePreview ? (
              <div style={{ position: "relative", width: "100%", height: "100%",
                            display: "flex", justifyContent: "center", alignItems: "center" }}>
                <img
                  ref={imageRef}
                  src={imagePreview}
                  alt="Inspection surface scan"
                  onLoad={updateBBoxScale}
                />

                {/* Scanner animation */}
                {["detecting", "retrieving", "generating"].includes(stage) && (
                  <>
                    <div className="scanner-overlay" />
                    <div className="scanner-line" />
                  </>
                )}

                {/* Severity-coded bounding boxes */}
                {["detected", "retrieving", "verify", "generating", "done"].includes(stage) &&
                  detections.map((d, i) => {
                    const risk = d.risk_level || getSevFromDefectType(d.label);
                    const isSelected = selectedDefect === d;
                    return (
                      <div
                        key={i}
                        className={`bbox bbox-sev${risk} ${isSelected ? "selected" : ""}`}
                        onClick={() => handleSelectDefect(d)}
                        style={{
                          left: `${d.bbox[0] * scale.x}px`,
                          top: `${d.bbox[1] * scale.y}px`,
                          width: `${(d.bbox[2] - d.bbox[0]) * scale.x}px`,
                          height: `${(d.bbox[3] - d.bbox[1]) * scale.y}px`,
                          animationDelay: `${i * 0.08}s`,
                        }}
                      >
                        <span className={`bbox-label bbox-label-sev${risk}`}>
                          {d.label.replace(/_/g, " ")}
                        </span>
                      </div>
                    );
                  })}
              </div>
            ) : (
              /* Idle state */
              <div className="idle-vis">
                <div className="idle-radar">
                  <div className="idle-scan-ring" />
                  <RadarSchematic />
                </div>
                <div className="idle-text">
                  AWAITING SCANNER FEED<br />
                  <span style={{ opacity: 0.5, fontSize: "0.62rem" }}>
                    UPLOAD AN AIRCRAFT SURFACE IMAGE TO BEGIN INSPECTION
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Severity Legend */}
          <div className="severity-legend">
            <span style={{ fontSize: "0.62rem", color: "var(--text-muted)", marginRight: 4, letterSpacing: "0.07em" }}>
              SEVERITY:
            </span>
            {[
              { sev: 1, label: "CAT 1 — AOG" },
              { sev: 2, label: "CAT 2 — 10 Cycles" },
              { sev: 3, label: "CAT 3 — 30 Days" },
              { sev: 4, label: "CAT 4 — Cosmetic" },
            ].map(({ sev, label }) => (
              <div key={sev} className="legend-item">
                <div className="legend-dot" style={{
                  background: `var(--sev-${sev})`,
                  boxShadow: `0 0 6px var(--sev-${sev})`,
                }} />
                {label}
              </div>
            ))}
          </div>
        </div>

        {/* ── RIGHT: Workspace Panel ────────────────────── */}
        <div className="workspace-panel">

          {/* ── UPLOAD STAGE ──────────────────────────── */}
          {stage === "upload" && (
            <>
              {/* Stats row */}
              {stats && (
                <div className="stats-row">
                  <div className="stat-card">
                    <div className="stat-label">Total Inspections</div>
                    <div className="stat-value">{stats.total_inspections}</div>
                    <div className="stat-sub">All time</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Avg Confidence</div>
                    <div className="stat-value">
                      {stats.total_inspections > 0
                        ? `${(stats.avg_confidence * 100).toFixed(0)}%`
                        : "—"}
                    </div>
                    <div className="stat-sub">Model accuracy</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Top Defect</div>
                    <div className="stat-value" style={{ fontSize: "1rem", textTransform: "uppercase" }}>
                      {stats.by_defect_type?.[0]?.defect_type?.replace(/_/g, " ") || "—"}
                    </div>
                    <div className="stat-sub">
                      {stats.by_defect_type?.[0]
                        ? `${stats.by_defect_type[0].count}× recorded`
                        : "No data"}
                    </div>
                  </div>
                </div>
              )}

              {/* Upload card */}
              <div className="card">
                <div className="card-header">
                  <div className="card-title">
                    <UploadIcon size={16} />
                    Surface Image Ingestion
                  </div>
                  <span className="card-badge">STEP 1</span>
                </div>
                <div className="card-body">
                  <p style={{ fontSize: "0.82rem", color: "var(--text-body)", lineHeight: 1.6 }}>
                    Upload an aircraft structure panel photograph to run AI defect scanning and cross-reference AMM directive libraries.
                  </p>
                  <div
                    className={`upload-zone ${dragOver ? "drag-over" : ""}`}
                    onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                  >
                    <div className="upload-icon-ring">
                      <CloudUploadIcon size={28} />
                    </div>
                    <div className="upload-title">
                      {dragOver ? "Drop to scan" : "Drag & Drop or Click to Browse"}
                    </div>
                    <div className="upload-sub">Supports PNG, JPG, JPEG, WEBP — max 10 MB</div>
                    <div className="format-chips">
                      {["PNG", "JPG", "JPEG", "WEBP"].map((f) => (
                        <span key={f} className="format-chip">{f}</span>
                      ))}
                    </div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      className="file-input"
                      onChange={handleFileChange}
                    />
                  </div>
                </div>
              </div>

              {/* Audit history card */}
              <div className="card">
                <div className="card-header">
                  <div className="card-title">
                    <HistoryIcon size={16} />
                    Inspection Audit Trail
                  </div>
                  <span className="card-badge">{historyList.length} RECORDS</span>
                </div>
                <div className="card-body">
                  {/* Filter buttons */}
                  {defectTypes.length > 0 && (
                    <div className="filter-row">
                      <button
                        className={`filter-btn ${historyFilter === "all" ? "active" : ""}`}
                        onClick={() => setHistoryFilter("all")}
                      >
                        ALL
                      </button>
                      {defectTypes.map((t) => (
                        <button
                          key={t}
                          className={`filter-btn ${historyFilter === t ? "active" : ""}`}
                          onClick={() => setHistoryFilter(t)}
                        >
                          {t.replace(/_/g, " ").toUpperCase()}
                        </button>
                      ))}
                    </div>
                  )}

                  <div className="history-scroll">
                    {filteredHistory.length === 0 ? (
                      <div className="empty-state">
                        <DatabaseIcon size={28} />
                        <span>No signed-off inspections in database.</span>
                      </div>
                    ) : (
                      filteredHistory.map((h, i) => {
                        const risk = getSevFromDefectType(h.defect_type);
                        return (
                          <div key={h.id || i} className="history-item">
                            <div className="history-item-left">
                              <div className="history-item-title">
                                <div
                                  className="history-dot"
                                  style={{ background: `var(--sev-${risk})` }}
                                />
                                {h.aircraft_id} — {h.defect_type.replace(/_/g, " ").toUpperCase()}
                              </div>
                              <div className="history-item-sub">
                                {h.report_id}  ·  {h.amm_id}
                                {h.inspector_name ? `  ·  ${h.inspector_name}` : ""}
                              </div>
                              <div className="history-item-ts">{h.timestamp}</div>
                            </div>
                            <a
                              className="history-download-btn"
                              href={`http://localhost:5000/api/report/${h.report_id}`}
                              target="_blank"
                              rel="noreferrer"
                              title="Download PDF"
                            >
                              <DownloadIcon size={14} />
                            </a>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>
            </>
          )}

          {/* ── DETECTING LOADER ────────────────────────── */}
          {stage === "detecting" && (
            <div className="card">
              <div className="loader-card">
                <div className="loader-spinner">
                  <div className="spinner-ring spinner-ring-1" />
                  <div className="spinner-ring spinner-ring-2" />
                  <div className="spinner-ring spinner-ring-3" />
                </div>
                <div className="loader-stage-label">Scanning Surface Anomalies…</div>
                <div className="loader-sub">
                  YOLOv8 model is analyzing the uploaded image for structural defects.
                </div>
                <div className="loader-steps">
                  {["Preprocessing", "Model Inference", "Post-processing"].map((s, i) => (
                    <span key={s} className={`loader-step-chip ${loaderStep >= i ? "active" : ""}`}>
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── RETRIEVING LOADER ───────────────────────── */}
          {stage === "retrieving" && (
            <div className="card">
              <div className="loader-card">
                <div className="loader-spinner">
                  <div className="spinner-ring spinner-ring-1" />
                  <div className="spinner-ring spinner-ring-2" />
                  <div className="spinner-ring spinner-ring-3" />
                </div>
                <div className="loader-stage-label">Querying AMM Library…</div>
                <div className="loader-sub">
                  Matching defect to regulatory maintenance manual via offline RAG.
                </div>
                <div className="loader-steps">
                  {["Embedding Query", "Cosine Similarity", "Retrieving Directive"].map((s, i) => (
                    <span key={s} className={`loader-step-chip ${i <= 1 ? "active" : ""}`}>
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── GENERATING LOADER ───────────────────────── */}
          {stage === "generating" && (
            <div className="card">
              <div className="loader-card">
                <div className="loader-spinner">
                  <div className="spinner-ring spinner-ring-1" />
                  <div className="spinner-ring spinner-ring-2" />
                  <div className="spinner-ring spinner-ring-3" />
                </div>
                <div className="loader-stage-label">Compiling NRF Report…</div>
                <div className="loader-sub">
                  Building compliance PDF with audit trail and sign-off blocks.
                </div>
                <div className="loader-steps">
                  {["Building Layout", "Rendering PDF", "Logging Audit"].map((s, i) => (
                    <span key={s} className={`loader-step-chip ${i <= 1 ? "active" : ""}`}>{s}</span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── DETECTED + VERIFY + DONE ─────────────────── */}
          {["detected", "verify", "done"].includes(stage) && (
            <>
              {/* ── Scan Results Card ───────────────────── */}
              <div className="card">
                <div className="card-header">
                  <div className="card-title">
                    <ScanIcon size={16} />
                    Detected Anomalies
                  </div>
                  <span className="card-badge">{detections.length} FOUND</span>
                </div>
                <div className="card-body">
                  {modelMode === "demo_fallback" && (
                    <div className="demo-notice">
                      <AlertIcon size={14} />
                      Demo fallback model active — results are illustrative, not calibrated.
                    </div>
                  )}

                  {detections.length === 0 ? (
                    <div className="empty-state">No structural anomalies detected.</div>
                  ) : (
                    <div className="defect-list">
                      {detections.map((d, i) => {
                        const risk = d.risk_level || getSevFromDefectType(d.label);
                        const conf = d.confidence;
                        const confClass = conf >= 0.8 ? "high" : conf >= 0.5 ? "med" : "low";
                        return (
                          <button
                            key={i}
                            className={`defect-item ${selectedDefect === d ? "selected" : ""}`}
                            onClick={() => handleSelectDefect(d)}
                            disabled={stage === "retrieving"}
                          >
                            <div className="defect-left">
                              <div className={`sev-indicator sev-ind-${risk}`} />
                              <div className="defect-info">
                                <div className="defect-name">{d.label.replace(/_/g, " ")}</div>
                                <div className="defect-conf-row">
                                  <span className="conf-pct">{(conf * 100).toFixed(0)}%</span>
                                  <div className="conf-track">
                                    <div
                                      className={`conf-fill conf-fill-${confClass}`}
                                      style={{ width: `${conf * 100}%` }}
                                    />
                                  </div>
                                  <span className={`sev-tag sev-tag-${risk}`}>
                                    {d.severity_class?.split("—")[0]?.trim() || `Cat ${risk}`}
                                  </span>
                                </div>
                              </div>
                            </div>
                            <ChevronRightIcon size={16} />
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* ── AMM Reference Card ──────────────────── */}
              {stage === "verify" && procedure && (
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">
                      <BookIcon size={16} />
                      AMM Directive Reference
                    </div>
                    <span className={`sev-tag sev-tag-${procedure.risk_level || 3}`}>
                      {procedure.severity_class?.split("—")[0]?.trim() || "CAT 3"}
                    </span>
                  </div>

                  <div className="procedure-panel">
                    {/* Header row */}
                    <div>
                      <div className="procedure-header-row">
                        <span className="procedure-id">{procedure.id}</span>
                      </div>
                      <div className="procedure-title">{procedure.title}</div>
                      <div className="procedure-chapter">{procedure.chapter}</div>
                    </div>

                    {/* Severity pill */}
                    <div className={`sev-pill-lg sev-pill-${procedure.risk_level || 3}`}>
                      <AlertIcon size={14} />
                      {procedure.severity_class}
                    </div>

                    {/* AMM meta grid */}
                    <div className="amm-meta-grid">
                      <div className="amm-meta-card">
                        <div className="amm-meta-label">Est. Duration</div>
                        <div className="amm-meta-value">{procedure.estimated_duration || "N/A"}</div>
                      </div>
                      <div className="amm-meta-card">
                        <div className="amm-meta-label">Regulatory Ref.</div>
                        <div className="amm-meta-value" style={{ fontSize: "0.7rem" }}>
                          {procedure.regulatory_reference?.split(";")[0] || "N/A"}
                        </div>
                      </div>
                    </div>

                    {/* Procedure Tabs */}
                    <div className="proc-tabs">
                      {[
                        { id: "procedure", label: "Work Instructions" },
                        { id: "tooling",   label: "Tooling & Parts" },
                        { id: "info",      label: "Regulation" },
                      ].map((t) => (
                        <button
                          key={t.id}
                          className={`proc-tab ${activeTab === t.id ? "active" : ""}`}
                          onClick={() => setActiveTab(t.id)}
                        >
                          {t.label}
                        </button>
                      ))}
                    </div>

                    {/* Tab Content */}
                    {activeTab === "procedure" && (
                      <div className="steps-list">
                        {procedure.procedure
                          .split("\n")
                          .filter((l) => l.trim())
                          .map((line, i) => {
                            let text = line.trim();
                            const stepPrefix = /^Step\s*\d+\.\s*/i;
                            const numPrefix = /^\d+\.\s*/;
                            text = text.replace(stepPrefix, "").replace(numPrefix, "");
                            return (
                              <div key={i} className="step-row">
                                <span className="step-num-badge">{String(i + 1).padStart(2, "0")}</span>
                                <span className="step-text">{text}</span>
                              </div>
                            );
                          })}
                      </div>
                    )}

                    {activeTab === "tooling" && (
                      <div className="info-grid">
                        <div className="info-card">
                          <div className="info-label">Required Tooling & Equipment</div>
                          <div className="info-value">{procedure.tooling}</div>
                        </div>
                        <div className="info-card">
                          <div className="info-label">Parts & Consumables</div>
                          <div className="info-value">{procedure.parts_required || "N/A"}</div>
                        </div>
                        <div className="info-card">
                          <div className="info-label">Estimated Labor Duration</div>
                          <div className="info-value">{procedure.estimated_duration || "N/A"}</div>
                        </div>
                      </div>
                    )}

                    {activeTab === "info" && (
                      <div className="info-grid">
                        <div className="info-card">
                          <div className="info-label">Regulatory Reference</div>
                          <div className="info-value">{procedure.regulatory_reference || "N/A"}</div>
                        </div>
                        <div className="info-card">
                          <div className="info-label">Severity Classification</div>
                          <div className="info-value">{procedure.severity_class}</div>
                        </div>
                      </div>
                    )}

                    {/* Inspector Verification Form */}
                    <hr className="form-divider" />
                    <div className="form-section-title">Inspector Verification & Signoff</div>

                    <div className="field">
                      <label className="field-label">Aircraft Registration ID</label>
                      <input
                        type="text"
                        value={aircraftId}
                        onChange={(e) => setAircraftId(e.target.value.toUpperCase())}
                        placeholder="e.g. VT-INS-1102"
                        className={!aircraftIdValid ? "invalid" : ""}
                      />
                    </div>

                    <div className="field">
                      <label className="field-label">Inspector Name</label>
                      <input
                        type="text"
                        value={inspectorName}
                        onChange={(e) => setInspectorName(e.target.value)}
                        placeholder="e.g. J. Ramsay — AME Lic. 7741"
                      />
                    </div>

                    <div className="field">
                      <label className="field-label">
                        Inspector Remarks & Debris Log
                        <span className="char-count" style={{ marginLeft: "auto" }}>
                          {notes.length}/500
                        </span>
                      </label>
                      <textarea
                        rows={3}
                        maxLength={500}
                        placeholder="e.g. Cleaned area, stop-drilling verified. Doubler applied per RS-220. Ready for patching."
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                      />
                    </div>

                    <button
                      className="btn-primary"
                      onClick={handleGenerateReport}
                      disabled={!aircraftIdValid}
                    >
                      <DocumentIcon size={16} />
                      Approve & Generate NRF Report
                    </button>
                  </div>
                </div>
              )}

              {/* ── DONE: Success Card ───────────────────── */}
              {stage === "done" && reportUrl && (
                <div className="card">
                  <div className="success-panel">
                    <div className="success-icon-ring">
                      <CheckIcon size={32} />
                    </div>
                    <div>
                      <div className="success-title">NRF Report Compiled</div>
                      <div className="success-sub" style={{ marginTop: 4 }}>
                        Compliance report logged to audit database.
                      </div>
                    </div>

                    <div className="success-meta">
                      {[
                        { label: "Report ID",      val: reportId },
                        { label: "Aircraft",       val: aircraftId },
                        { label: "Anomaly",        val: selectedDefect?.label?.replace(/_/g, " ").toUpperCase() },
                        { label: "AMM Directive",  val: procedure?.id },
                        { label: "Inspector",      val: inspectorName || "—" },
                      ].map(({ label, val }) => (
                        <div key={label} className="success-row">
                          <span className="success-row-label">{label}</span>
                          <span className="success-row-val">{val}</span>
                        </div>
                      ))}
                    </div>

                    <div className="success-actions">
                      <a className="btn-primary" href={reportUrl} target="_blank" rel="noreferrer">
                        <DownloadIcon size={16} />
                        Download Signed NRF PDF
                      </a>
                      <button className="btn-secondary" onClick={resetFlow}>
                        New Surface Inspection
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>{/* end workspace-panel */}
      </div>{/* end dashboard-layout */}
    </div>
  );
}

/* ═══════════════════ ICON LIBRARY ══════════════════════════ */

function PlaneIcon({ size = 22 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 16V8a2 2 0 0 0-2-2h-3L9 12H3a2 2 0 0 0-2 2v0a2 2 0 0 0 2 2h6l7 6h3a2 2 0 0 0 2-2z"/>
      <path d="M2 10V6a2 2 0 0 1 2-2h3"/>
      <path d="m13 12 4-8"/>
    </svg>
  );
}

function ScanIcon({ size = 18 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 7V5a2 2 0 0 1 2-2h2"/>
      <path d="M17 3h2a2 2 0 0 1 2 2v2"/>
      <path d="M21 17v2a2 2 0 0 1-2 2h-2"/>
      <path d="M7 21H5a2 2 0 0 1-2-2v-2"/>
      <line x1="4" y1="12" x2="20" y2="12"/>
    </svg>
  );
}

function UploadIcon({ size = 18 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2v8M17 5l-5-5-5 5"/>
      <path d="M2 17v4a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-4"/>
    </svg>
  );
}

function CloudUploadIcon({ size = 30 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/>
      <path d="M12 12v9M16 16l-4-4-4 4"/>
    </svg>
  );
}

function BookIcon({ size = 18 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
    </svg>
  );
}

function DocumentIcon({ size = 18 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/>
      <line x1="16" y1="17" x2="8" y2="17"/>
    </svg>
  );
}

function CheckIcon({ size = 32 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  );
}

function DownloadIcon({ size = 16 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="7 10 12 15 17 10"/>
      <line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  );
}

function HistoryIcon({ size = 16 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 8v4l3 3"/>
      <path d="M3.05 11a9 9 0 1 1 .5 4M3 12h-3v-3"/>
    </svg>
  );
}

function DatabaseIcon({ size = 16 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3"/>
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
    </svg>
  );
}

function AlertIcon({ size = 14 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/>
      <line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  );
}

function ChevronRightIcon({ size = 16 }) {
  return (
    <svg className="chevron-icon" xmlns="http://www.w3.org/2000/svg"
         width={size} height={size}
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  );
}

function RadarSchematic() {
  return (
    <svg viewBox="0 0 100 100" width="160" height="160"
         stroke="currentColor" strokeWidth="0.5" fill="none">
      <circle cx="50" cy="50" r="45" strokeDasharray="1 3"
              stroke="rgba(37,99,235,0.2)"/>
      <circle cx="50" cy="50" r="30" strokeDasharray="2 2"
              stroke="rgba(37,99,235,0.35)"/>
      <circle cx="50" cy="50" r="15" stroke="rgba(37,99,235,0.15)"/>
      <line x1="5"  y1="50" x2="95" y2="50" stroke="rgba(37,99,235,0.15)"/>
      <line x1="50" y1="5"  x2="50" y2="95" stroke="rgba(37,99,235,0.15)"/>
      <path
        d="M50,15 L53,38 L85,45 L85,49 L53,48 L53,73 L63,78 L63,81 L50,79 L37,81 L37,78 L47,73 L47,48 L15,49 L15,45 L47,38 Z"
        stroke="rgba(37,99,235,0.85)" strokeWidth="1.2" strokeLinejoin="round"
        fill="rgba(37,99,235,0.05)"
      />
    </svg>
  );
}
