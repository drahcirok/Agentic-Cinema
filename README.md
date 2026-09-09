# FrameFlow

**FrameFlow** is a secure, multi-role post-production workflow platform built for the **Google Cloud Agentic Cinema Hackathon (IBM Bob track)**.

It turns director notes into structured post-production tasks with Gemini on Vertex AI, then guides each task through human review, department assignment, artist delivery, and final quality control.

## Why FrameFlow

Film post-production often loses context as notes move between producers, supervisors, and specialist departments. FrameFlow provides one traceable workspace where every production keeps its own members, roles, tasks, notifications, activity history, and private evidence.

## Workflow

1. A **Producer** creates a production, invites verified team members, manages access, and follows progress metrics.
2. A **Supervisor** submits director notes for Gemini-assisted analysis, reviews the proposed task, and assigns it to the appropriate artist.
3. An **Artist** receives only their assigned department work, starts the task, and can submit an optional delivery link or visual evidence for quality control.
4. The **Supervisor** approves the completed work or returns it with feedback. Completed and rejected tasks remain in the production-specific history.

## Key Features

- Google Sign-In with Firebase Authentication
- Production-scoped roles: Producer, Supervisor, and Artist
- Team invitations that require acceptance before access is granted
- Gemini on Vertex AI for post-production task classification and prioritization
- Separate task boards for decisions, assigned work, quality control, and history
- Live notifications and activity trails
- Firestore persistence scoped to the active production
- Private visual evidence stored in Google Cloud Storage
- Responsive English-first interface deployed on Vercel

## Architecture

| Layer | Technology |
| --- | --- |
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Authentication | Firebase Authentication with Google Sign-In |
| API | FastAPI running on Google Cloud Run |
| AI | Gemini through Vertex AI |
| Data | Cloud Firestore |
| Evidence storage | Google Cloud Storage |
| Frontend hosting | Vercel |

## Local Development

### Prerequisites

- Node.js 20 or newer
- Python 3.11 or newer
- A Firebase project with the Google provider enabled
- A Google Cloud project with Vertex AI, Firestore, and Cloud Storage configured when using cloud integrations

### 1. Start the backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

For local-only development, the default `.env` uses SQLite and does not require cloud credentials. To use Vertex AI locally, authenticate with Application Default Credentials and configure the Google Cloud values in `backend/.env`:

```powershell
gcloud auth application-default login
```

### 2. Start the frontend

Open a second terminal:

```powershell
cd frontend
npm install
```

Create `frontend/.env.local` with your Firebase web application values:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1
NEXT_PUBLIC_FIREBASE_API_KEY=your_firebase_api_key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your_project_id
NEXT_PUBLIC_FIREBASE_APP_ID=your_firebase_app_id
```

Then run:

```powershell
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Deployment

- The FastAPI backend is deployed to **Google Cloud Run** using `backend/Dockerfile` and `backend/cloudrun-env.yaml`.
- The Next.js frontend is deployed to **Vercel** from the `frontend` directory.
- Cloud Run uses a dedicated service account with access to Vertex AI, Firestore, and the private Cloud Storage bucket.
- Firebase ID tokens protect the backend when `AUTH_REQUIRED=true`.

See [docs/deployment.md](docs/deployment.md) for the detailed deployment procedure.

## Security and Privacy

- Users authenticate through Firebase before accessing application data.
- A user can access a production only after accepting its invitation.
- Every ticket query is scoped to the selected production and the member's authorization.
- Uploaded evidence is accessed through authenticated API endpoints rather than public bucket URLs.
- Environment files and credentials are excluded from version control.

## Live Demo

- Application: [agentic-cinema-iota.vercel.app](https://agentic-cinema-iota.vercel.app)
- API health check: [frameflow-backend-581709817852.us-central1.run.app/health](https://frameflow-backend-581709817852.us-central1.run.app/health)

## Hackathon Context

FrameFlow was created for the Google Cloud Agentic Cinema Hackathon and references the **IBM Bob** track context. Its production implementation uses the Google Cloud services listed above for AI, identity-aware workflow orchestration, persistence, and private storage.

## License

FrameFlow is released under the [MIT License](LICENSE).
