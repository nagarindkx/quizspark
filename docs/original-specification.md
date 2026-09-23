# Master Prompt: QuizSpark - Open-Source Kahoot Alternative

Copy and paste the following prompt into an AI code generator to build the **QuizSpark** application from scratch.

---

### System Role & Objective
You are an expert full-stack web developer and UI/UX designer. Your task is to build a complete, self-contained, single-file HTML application named **QuizSpark**—a modern, interactive, real-time multiplayer trivia platform inspired by Kahoot.

The entire application must be contained in a **single `index.html` file** with inline CSS and JavaScript, requiring no external server build steps, Node packages, or backend APIs.

---

### Key Requirements & Core Technologies

1. **Tech Stack & External Libraries (via CDN):**
   - **HTML5 & Vanilla JavaScript (ES6+)**
   - **Tailwind CSS (CDN):** Custom theme with Kahoot-inspired color palette (`purple: #46178f`, `dark: #250850`, `red: #e21b3c`, `blue: #1368ce`, `yellow: #d89e00`, `green: #26890c`).
   - **Font Awesome v6 (CDN):** Modern icon library.
   - **Canvas Confetti (CDN):** Visual celebrations on victory podium.
   - **Web Audio API:** Native synthesizer for sound effects (no external audio assets required).

2. **Real-Time Synchronisation (Serverless):**
   - Use the native browser **`BroadcastChannel` API** to synchronize game states across tabs, windows, or iframes in real time.
   - Game rooms are identified by a 6-digit Game PIN.

3. **Internationalization (i18n):**
   - Built-in live toggle between **Thai (TH)** and **English (EN)**.
   - All UI titles, descriptions, buttons, tooltips, and dynamic view labels must reactively update upon language selection.

4. **Web Audio Synthesizer (`SoundEngine`):**
   - Built using native Web Audio API oscillators.
   - Sounds required: Countdown tick, Correct answer chime, Incorrect answer buzz, Final victory fanfare.
   - Audio Mute/Unmute toggle in the global header bar.

---

### Views & User Journey Requirements

The application must seamlessly switch between 13 distinct views inside `#app-container`:

1. **Header Bar (Global):**
   - QuizSpark logo with version badge (`v3.0`).
   - Sound toggle button (`Sound On` / `Muted`).
   - Language toggle button (`TH / EN`).
   - Home button.

2. **Home View (`view-home`):**
   - Hero banner with interactive quick-join PIN input.
   - 4 Action Cards:
     - **Host Game:** Starts a session on a presentation screen.
     - **Join Game:** Opens mobile player answer interface.
     - **Quiz Manager:** Create/Edit custom quizzes with images and open-ended options.
     - **Dual Simulator:** Split-screen mode to test Host and Player side-by-side.

3. **Host Select Quiz View (`view-host-select`):**
   - Displays all quizzes saved in `localStorage` alongside default preset quizzes.
   - Buttons to **Host**, **Edit**, or **Create New Quiz**.

4. **Host Lobby View (`view-host-lobby`):**
   - Generates a random 6-digit Game PIN.
   - Displays QR Code placeholder and "Copy Game Link" button.
   - **"+ Add Bot"** button to simulate automated players with random names and avatars.
   - Live grid displaying joined players with click-to-kick functionality.
   - "Start Game" button (disabled until at least 1 player joins).

5. **Host Game Screen (`view-host-game`):**
   - Visual timer bar counting down with numeric seconds display.
   - Displays question number, total questions, and question type badge (`MCQ` or `OPEN-ENDED`).
   - Supports Question Image URL/Uploaded Base64 image, with fallback emoji.
   - Real-time "Answers Received" counter.
   - Shows answer shape buttons (MCQ) or typing indicator (Open-Ended).

6. **Host Answer Breakdown / Reveal (`view-host-results`):**
   - **MCQ Questions:** Dynamic bar chart showing response distribution for ▲ Red, ◆ Blue, ● Yellow, ■ Green options.
   - **Open-Ended Questions:** Interactive response pills showing submitted text answers colored green (correct) or red (incorrect).
   - Shows correct answer indicator and an **Explanation Card** (supports explanation text and explanation image).
   - "Next Scoreboard" button.

7. **Host Scoreboard (`view-host-leaderboard`):**
   - Animated top 5 ranked players with rank, avatar, nickname, current total score, and active win streak badge (`🔥`).
   - Progression button ("Next Question" or "Show Final Podium").

8. **Host Victory Podium (`view-host-podium`):**
   - 3D-styled animated podium for 1st (Gold), 2nd (Silver), and 3rd (Bronze) place.
   - Triggers Canvas Confetti particles and victory fanfare sound.

9. **Player Join View (`view-player-join`):**
   - Form requesting 6-digit PIN, Nickname, and Avatar Emoji selector grid.

10. **Player Waiting Screen (`view-player-waiting`):**
    - Animated confirmation screen with player avatar and status indicator.

11. **Player Answer Screen (`view-player-answer`):**
    - **MCQ Mode:** 4 large colored touch buttons matching the host shape icons.
    - **Open-Ended Mode:** Clean text input field with "Submit Answer" button.

12. **Player Feedback Screen (`view-player-feedback`):**
    - Fullscreen color feedback (Green for Correct / Red for Incorrect).
    - Displays points earned (calculated based on response speed), streak, current leaderboard position, and explanation box.

13. **Quiz Manager / Editor View (`view-editor`):**
    - Quiz title and category fields.
    - Question builder supporting:
      - Question type toggle (MCQ vs Open-Ended).
      - Multiple choice option text inputs & correct option selector.
      - Open-ended accepted answer list (comma-separated, case-insensitive matching).
      - Question Image URL input or local file upload (converts to Base64).
      - Explanation text and Explanation Image upload.
    - Full **Export JSON** and **Import JSON** file functionality.

14. **Dual Simulator View (`view-simulator`):**
    - Split-screen layout loading two `iframe` instances (Host on left, Player on right) to test full game loops in a single browser window.

---

### Data Models & Logic Specifications

#### Quiz Schema:
```json
{
  "id": "quiz-101",
  "title": "Sample Quiz Title",
  "category": "General Knowledge",
  "questions": [
    {
      "type": "mcq", // or "open"
      "text": "What is the capital of Thailand?",
      "image": "https://example.com/image.jpg",
      "options": ["Chiang Mai", "Bangkok", "Phuket", "Pattaya"],
      "correct": 1,
      "time": 20,
      "emoji": "🇹🇭",
      "explanationText": "Bangkok (Krung Thep Maha Nakhon) has been the capital since 1782.",
      "explanationImage": ""
    },
    {
      "type": "open",
      "text": "What is the chemical symbol for Gold?",
      "openAnswers": ["Au", "AU", "au"],
      "time": 20,
      "emoji": "🪙",
      "explanationText": "Au comes from the Latin word 'Aurum'.",
      "explanationImage": ""
    }
  ]
}
```

#### Scoring System:
- **Base Score:** 1,000 points max for a correct answer.
- **Speed Multiplier:** $\text{Points} = \text{Round}\left(1000 \times \left(1 - \frac{\text{Time Taken}}{\text{Time Limit} \times 2}\right)\right)$.
- **Streak Tracking:** Consecutive correct answers increase streak count. Incorrect answers reset streak to 0.

#### Data Persistence:
- Store custom quizzes in `localStorage` key `QuizSpark_quizzes_v3`. Load default sample quizzes if empty.

---

### UI / Styling Guidelines
- **Background:** Deep radial purple gradient (`radial-gradient(circle at center, #46178f 0%, #250850 100%)`).
- **Glassmorphic Containers:** White transparent backgrounds (`bg-white/10 backdrop-blur-md border border-white/15`).
- **Animations:** Subtle CSS pop animations (`@keyframes pop`), smooth transitions, pulse and bounce effects for icons.
- **Responsive Design:** Mobile-first layout for player view; high-density desktop presentation layout for host view.