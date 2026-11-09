# AeroScribe — Hackathon Prototype

Offline Edge AI Maintenance Documentation Copilot for Aircraft MRO.
Workflow: **Capture → Detect → Retrieve (offline RAG) → Verify → Generate NRF report (PDF)**

This prototype proves the full workflow end-to-end on a laptop. It's built so you
can swap in real components (fine-tuned YOLO weights, a bigger AMM corpus, a
local quantized LLM) later without changing the architecture.

---

## 1. Backend setup (Flask)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Backend runs at `http://localhost:5000`.

**First run notes:**
- `ultralytics` will auto-download `yolov8n.pt` (~6MB) on first detection call — needs internet once, then it's cached. After that the demo can run fully offline.
- `sentence-transformers` will auto-download the `all-MiniLM-L6-v2` model (~80MB) on first retrieval call — same deal, one-time download, then offline.
- **Do this download step the night before the demo**, not on stage, in case venue wifi is bad.

### Detection mode
Right now there's no fine-tuned defect model, so `defect_detection.py` runs
pretrained YOLOv8 (COCO weights) and maps detections to a defect class so the
rest of the pipeline (retrieval + report) is honestly demoable while you
label a real dataset. To plug in a real trained model later:
1. Train/fine-tune YOLOv8 on labeled crack/corrosion/rivet/dent images
   (Roboflow is the fastest way to label a small set).
2. Save weights to `backend/models/defect_yolov8.pt`.
3. Update `DEFECT_CLASSES` in `defect_detection.py` to match your label order.
4. It will auto-detect the file and switch out of demo mode.

### RAG / AMM database
`amm_data.py` has 5 sample AMM-style procedures (crack, corrosion,
missing_rivet, dent, paint_damage). `rag_retrieval.py` embeds these locally
with sentence-transformers and retrieves by cosine similarity — this is a
legitimate offline RAG pipeline, just with a small corpus. Add more entries
to `AMM_DATABASE` to make the demo richer.

---

## 2. Frontend setup (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`. Make sure the backend is already running
on port 5000 (CORS is enabled, frontend calls `http://localhost:5000/api/...`).

---

## 3. Demo script (suggested)

1. Open the app, upload a sample aircraft panel image (crack/corrosion/rivet photo).
2. Detection runs → bounding box + label appears on the image.
3. Click the detected defect → AMM procedure is retrieved offline, shown with
   severity classification and required tooling.
4. Fill in aircraft ID + inspector notes (or use the defaults) → click
   "Verify & Generate NRF Report".
5. Download the generated PDF — show the judges it's a real compliance-style
   report, generated in seconds, fully offline.

Mention out loud: "the detection model and retrieval corpus shown here are
the prototype scaffolding — production version uses a fine-tuned edge model
quantized via TensorRT, and a full AMM corpus indexed for the aircraft fleet,
matching our Phase 2/3 roadmap."

---

## 4. What's mocked vs real (be transparent with judges if asked)

| Component | Status |
|---|---|
| Workflow orchestration (Detect→Retrieve→Verify→Generate) | Real, fully working |
| Offline RAG retrieval (local embeddings, cosine similarity) | Real, fully working, small corpus |
| NRF PDF report generation | Real, fully working |
| Defect detection | Real YOLOv8 inference, pretrained weights (not yet fine-tuned on aircraft defects) |
| Edge optimization (quantization/TensorRT) | Roadmap item, not yet implemented in prototype |

This is exactly the kind of honesty that plays well in hackathon Q&A — you're
not claiming a finished product, you're demoing a working architecture.

---

## 5. Next steps if you have more time after the hackathon

- Label a small aircraft defect image set (50-100 images) on Roboflow, fine-tune YOLOv8n.
- Expand the AMM database to 30-50 entries across more ATA chapters.
- Add a local quantized LLM (Ollama + a small model) to vary report narrative phrasing while keeping AMM procedure text exact.
- Package backend for actual edge hardware (Jetson Orin Nano is a common aerospace-relevant target) and test TensorRT export.
