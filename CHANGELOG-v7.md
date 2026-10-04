# v7
- One dark theme everywhere (#0e0e10 / #131315): landing, login (glass skin removed), KARNA, pages. Shared layer: `frontend/opai-shared.css`.
- Mobile: side padding 20 -> 12px, smaller bubbles, compact header, full-width composer (KARNA).
- Guide: header button, `/guide` command, floating "?" on other pages, nav tooltips. Answers "applications kahan hai?" / "exam ela add cheyali?" locally in English, Hinglish, Tenglish (`frontend/guide.js`).
- Language option in KARNA (English / Hinglish / Tenglish): applies to General mode, file analysis, Guide, voice input language. Workspace-mode replies are not yet language-switched (backend change needed).
- Hinglish capture (`backend/agent/capture.py`): "OS ka exam hai 20 Nov ko", "Acme mein ML Intern ke liye apply kar diya", Devanagari basics. 31 tests pass.
- PWA: manifest.json, icons, sw.js (API calls never cached). Backend serves /manifest.json and /sw.js.
