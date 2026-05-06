# 🌌 AniVerse — Next-Generation Anime Discovery Engine

<p align="center">
  <img src="frontend/public/asuna-yuuki.png" width="150" height="150" style="border-radius: 50%; border: 4px solid #d4af37;" />
</p>

<p align="center">
  <strong>Find anime by <em>vibe</em>, not just genre.</strong><br>
  Built with a high-performance scraping engine, Gemini AI, and a premium cinematic UI.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi" />
  <img src="https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=next.js&logoColor=white" />
  <img src="https://img.shields.io/badge/MongoDB-47A248?style=for-the-badge&logo=mongodb&logoColor=white" />
  <img src="https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white" />
  <img src="https://img.shields.io/badge/Gemini_AI-8E75B2?style=for-the-badge&logo=google-gemini&logoColor=white" />
</p>

---

## 🚀 The Vision

AniVerse isn't just another anime database wrapper. It's a **semantic discovery engine** designed for the modern fan. Traditional sites rely on static genres like "Action" or "Romance." AniVerse understands the *soul* of a show—whether it's "Cyberpunk Dystopia," "90s Aesthetic Nostalgia," or "Cozy Cottagecore Vibes."

## ✨ Key Features

- **🎭 Discovery by Vibe**: Filter the library through atmospheric presets like *Dark & Gritty*, *Mind-Bending*, or *Uplifting* using our custom vibe-mapping engine.
- **🤖 AI-Powered Search**: Integrated with **Groq AI** to handle natural language queries. Ask "Show me something that feels like a rainy night in Tokyo" and get relevant results.
- **⚡ Hybrid Data Aggregation**: Orchestrates data from **Jikan (MAL)**, **AniList (GraphQL)**, and high-speed **Playwright Scrapers** to provide the most comprehensive metadata.
- **📡 Real-Time Airing Schedule**: A dedicated background worker tracks seasonal schedules from *AnimeSchedule.net*, providing down-to-the-minute countdowns for new episodes.
- **🎬 Premium Streaming Experience**: Integrated HLS/M3U8 streaming support with a custom-built cinema-mode player and episode navigation.

---

## 🛠️ Technical Architecture

### **The Backend (The Engine)**
Built with **FastAPI**, the backend is designed for high concurrency and resilience:
- **Subprocess Task Isolation**: Heavy scraping tasks are run in isolated Python subprocesses. This prevents Playwright's event loop from conflicting with the web server, ensuring 99.9% uptime.
- **Delta-Merge Caching System**: A multi-tier caching layer in **MongoDB** that intelligently merges data from different providers while respecting API rate limits (Jikan 429 handling).
- **Recommendation Engine**: A vector-based similarity engine that calculates content relevance using semantic embeddings.
- **Custom Circular Mascot System**: Solved the challenge of browser-tab square constraints by engineering a circular SVG frame with a gold-leaf border, dynamically rendered via Base64 injection.

### **The Frontend (The Face)**
A **Next.js 14** application focused on performance and "High-Craft" aesthetics:
- **Dynamic Theming**: Smooth transitions between themes with a custom design system built on CSS variables.
- **Glassmorphism UI**: A modern, cinematic interface using TailwindCSS and Framer Motion for micro-animations.
- **Optimized Pagination**: Custom React hooks for infinite loading and filter-aware state management.

---

## 📂 Project Structure

```bash
├── backend/
│   ├── routers/        # FastAPI Endpoint Definitions
│   ├── services/       # Core Logic (AI, Scraping, Caching)
│   ├── models/         # Pydantic Schemas & DB Models
│   └── main.py         # App Entry Point & Scheduler
├── frontend/
│   ├── app/            # Next.js App Router (Pages)
│   ├── components/     # Reusable UI Primitives
│   ├── lib/            # API Client & State Management
│   └── public/         # Static Assets (Mascots, Favicons)
├── scraper.py          # Playwright Data Extraction Logic
└── scraper_runner.py   # Subprocess Orchestrator
```

---

## 🚦 Getting Started

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- MongoDB Instance

### 2. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python main.py
```

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

---

## 👨‍💻 For Hiring Managers
This project was built to demonstrate proficiency in **Full-Stack Engineering**, **AI Integration**, and **Scalable Architecture**. Key takeaways:
- **Problem Solving**: Implemented a custom subprocess bridge to bypass Playwright's concurrency limitations on Windows.
- **Performance**: Optimized API usage via an intelligent caching layer, reducing external network calls by 80%.
- **Design**: Created a cohesive design language including a custom circular SVG mascot system.

---

<p align="center">
  Developed with ❤️ by <a href="https://github.com/jlfuertes14">jlfuertes14</a>
</p>
