"""
Aircraft Maintenance Manual (AMM) knowledge base.

In the real product this would be a locally-indexed vector store built from
the full AMM PDF set. For this prototype, this is a curated set of realistic
AMM-style procedure entries that the RAG pipeline retrieves from using local
sentence-embedding similarity (fully offline, no API calls).

Fields per entry:
  id                  – Unique AMM directive reference code
  defect_type         – Primary defect class label (matches YOLO output)
  title               – Human-readable directive title
  chapter             – ATA chapter reference
  procedure           – Step-by-step maintenance work instructions
  severity_class      – Category label and repair schedule description
  risk_level          – Numeric risk (1 = highest, 4 = lowest)
  tooling             – Required tools and equipment
  estimated_duration  – Expected labor time window
  parts_required      – Consumables and replacement parts list
  regulatory_reference – Governing regulatory AD / SB reference
"""

AMM_DATABASE = [
    {
        "id": "AMM-53-10-01",
        "defect_type": "crack",
        "title": "Skin Crack Inspection and Repair — Fuselage Panel",
        "chapter": "ATA 53-10 Fuselage Structure",
        "procedure": (
            "Step 1. Clean inspection area with approved solvent (ref. SOPM 20-30-03). Allow full evaporation before proceeding.\n"
            "Step 2. Perform dye-penetrant inspection per NDT-04 to determine crack length and depth. Document all findings with photographic evidence.\n"
            "Step 3. If crack length exceeds 0.5 inch, stop-drill both ends per AMM 53-10-01 fig. 3 using calibrated drill bit (ref. SOPM 51-00-10).\n"
            "Step 4. Apply doubler patch per repair scheme RS-220 if defect is within allowable damage limits defined in SRM 53-10.\n"
            "Step 5. Install fasteners, torque to 35–40 in-lb and reseal with PR-1422 Class B sealant. Apply fillet bead along all edges.\n"
            "Step 6. Re-inspect completed repair using NDT-04. Record all findings, measurements, and repair disposition on Form 8130-3."
        ),
        "severity_class": "Category 2 — Schedule repair within 10 flight cycles",
        "risk_level": 2,
        "tooling": "Dye-penetrant kit (Ardrox 970P2), stop-drill bit set, calibrated torque wrench, PR-1422 sealant applicator",
        "estimated_duration": "3–5 hours",
        "parts_required": "Doubler patch (P/N: RS220-FSK), PR-1422 sealant (200ml), Hi-Lok fasteners HL10V6-6 (×8)",
        "regulatory_reference": "FAA AC 43.13-1B Ch.2 §2-9; EASA AMC 20-20 Appendix A",
    },
    {
        "id": "AMM-51-21-04",
        "defect_type": "corrosion",
        "title": "Surface Corrosion Treatment — Aluminum Skin",
        "chapter": "ATA 51-21 Standard Practices — Corrosion Control",
        "procedure": (
            "Step 1. Identify corrosion type (filiform / pitting / exfoliation) and grade per AMM 51-21-04 corrosion level chart. Photograph before treatment.\n"
            "Step 2. Remove corrosion by mechanical abrasion (ScotchBrite A/O pad, 120-grit) not exceeding 10% material thickness loss per SRM 51-21.\n"
            "Step 3. Verify remaining material thickness with calibrated ultrasonic thickness gauge. Record minimum measured thickness and location.\n"
            "Step 4. Apply corrosion-inhibiting compound (Alodine 1200S) per SOPM 20-41-00. Allow 5-minute contact time; rinse and dry thoroughly.\n"
            "Step 5. Re-prime with epoxy primer (MIL-PRF-23377 Type I) to 0.6–0.9 mil DFT. Apply topcoat per finish specification FS-12.\n"
            "Step 6. Document corrosion grade, location (station/stringer ref.), treatment method, and final thickness in aircraft log."
        ),
        "severity_class": "Category 3 — Monitor; repair within 30 days",
        "risk_level": 3,
        "tooling": "Ultrasonic thickness gauge (Olympus 38DL Plus), abrasive pads (120-grit), Alodine 1200S applicator, spray primer equipment",
        "estimated_duration": "2–4 hours",
        "parts_required": "Alodine 1200S (250ml), MIL-PRF-23377 epoxy primer (500ml), matching topcoat (ref. aircraft color code)",
        "regulatory_reference": "FAA Advisory Circular AC 43-4B; Boeing D6-17487 Rev H; EASA Part-M M.A.304",
    },
    {
        "id": "AMM-57-50-12",
        "defect_type": "missing_rivet",
        "title": "Rivet Replacement — Wing Skin Panel",
        "chapter": "ATA 57-50 Wing Structure — Fasteners",
        "procedure": (
            "Step 1. Confirm hole size, fastener grade, and grip length per IPC 57-50-12-01. Verify edge distance and pitch compliance with SRM 57-10.\n"
            "Step 2. Deburr and clean rivet hole using appropriate reamer. Inspect hole for elongation, cracks, or damage exceeding 5% oversize.\n"
            "Step 3. Install replacement rivet of identical type, material, and grip length. Do NOT substitute with a different fastener grade.\n"
            "Step 4. Set rivet using pneumatic rivet gun (Sioux SG04) with correct rivet set die. Maintain gun angle perpendicular to skin surface ±2°.\n"
            "Step 5. Inspect rivet head for proper formation: shop-head diameter ≥1.5× shank diameter; no cracks, splits, or tilting.\n"
            "Step 6. Apply PR-1422 sealant fillet if panel is in a fuel-tight or pressurized zone. Log replacement on Engineering Order and aircraft records."
        ),
        "severity_class": "Category 1 — AOG: Repair before next flight",
        "risk_level": 1,
        "tooling": "Pneumatic rivet gun (Sioux SG04), rivet sets MS20470-AD/DD, hole gauge set, calibrated drill press",
        "estimated_duration": "1–2 hours per fastener cluster",
        "parts_required": "Solid rivet AN470-AD4 or equivalent (per IPC), PR-1422 Class B sealant (if fuel zone)",
        "regulatory_reference": "FAA AC 43.13-1B Ch.4 §4-59; EASA Part-66 Module 7.4; MIL-R-47196A",
    },
    {
        "id": "AMM-51-23-08",
        "defect_type": "dent",
        "title": "Skin Dent Assessment and Repair Limits",
        "chapter": "ATA 51-23 Standard Practices — Sheet Metal",
        "procedure": (
            "Step 1. Measure dent depth and width at maximum extent using a precision contour gauge and depth micrometer. Record both dimensions.\n"
            "Step 2. Cross-reference depth-to-width ratio with AMM dent repair limit chart 51-23-08 fig. 5. Assess for stress-riser geometry.\n"
            "Step 3. If depth/width ratio is within limits and no cracks are present, perform blend-out inspection; no structural repair required.\n"
            "Step 4. If outside allowable limits, perform smooth-out using approved dolly and hammer technique per SRM 51-23. Do not exceed two rework attempts.\n"
            "Step 5. Re-inspect blended area for stress cracks using dye-penetrant inspection per NDT-04 before returning to service.\n"
            "Step 6. Record dent dimensions (depth, width, location by station/frame), repair disposition, and post-repair inspection findings in maintenance log."
        ),
        "severity_class": "Category 3 — Monitor; repair within 30 days",
        "risk_level": 3,
        "tooling": "Contour gauge, depth micrometer, dolly set, ball-peen hammer (8 oz), dye-penetrant kit",
        "estimated_duration": "1–3 hours",
        "parts_required": "Dye-penetrant consumables (Ardrox 970P2 kit); filler material (if cosmetic blend required)",
        "regulatory_reference": "FAA AC 43.13-1B Ch.3 §3-38; SRM 51-10-04; EASA AMC Part-M M.A.301",
    },
    {
        "id": "AMM-51-71-02",
        "defect_type": "paint_damage",
        "title": "Paint and Coating Damage — Touch-Up Procedure",
        "chapter": "ATA 51-71 Standard Practices — Finishes",
        "procedure": (
            "Step 1. Assess exposed area visually and tactilely for underlying corrosion, blistering, or adhesion failure before initiating cosmetic repair.\n"
            "Step 2. Sand damaged area lightly using 220-grit paper to remove loose and delaminated coating. Feather edges for smooth blend.\n"
            "Step 3. Clean surface with approved surface cleaner (Turco 5580) per SOPM 20-30-03. Ensure surface is fully dry before priming.\n"
            "Step 4. Apply one coat of epoxy primer (MIL-PRF-23377 Type I) and allow to cure 30–60 minutes at ambient temperature (≥18°C).\n"
            "Step 5. Apply topcoat matching aircraft livery color code using HVLP spray equipment. Apply two thin coats with 15-minute flash-off between.\n"
            "Step 6. Inspect finish for uniform coverage, correct gloss level, and proper cure. No runs, sags, or holidays permitted in pressurized zones."
        ),
        "severity_class": "Category 4 — Cosmetic; no flight restriction",
        "risk_level": 4,
        "tooling": "Sanding kit (180/220/400-grit), HVLP spray gun, mixing cups, masking tape",
        "estimated_duration": "1–2 hours (excluding cure time)",
        "parts_required": "MIL-PRF-23377 epoxy primer (200ml), aircraft livery topcoat (ref. color code), Turco 5580 surface cleaner",
        "regulatory_reference": "FAA AC 43.13-1B Ch.8; Boeing D6-17487 Finish Spec FS-12; MIL-PRF-85285D",
    },
]
