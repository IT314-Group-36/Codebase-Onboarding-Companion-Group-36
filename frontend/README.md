# Codebase Onboarding Companion

A web application designed to help developers understand and explore codebases more easily. The project combines a React frontend with a FastAPI backend to provide an interface for codebase exploration and onboarding.

## Tech Stack

### Frontend
- React
- Vite
- JavaScript
- ESLint

### Backend
- Python
- FastAPI

## Project Structure

The frontend is maintained separately from the backend within the main repository.

```text
Codebase-Onboarding-Companion-Group-36/
│
├── backend/              # FastAPI backend
│
├── frontend/             # React + Vite frontend
│   ├── public/
│   ├── src/
│   │   ├── components/   # Reusable UI components
│   │   ├── context/      # React context and application state
│   │   ├── pages/        # Application pages
│   │   ├── services/     # API and backend communication
│   │   └── utils/        # Utility functions
│   │
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── README.md
│
├── docker-compose.yml
└── README.md
```

## Prerequisites

Make sure you have the following installed:

- Node.js
- npm
- Python
- Git

The backend must also be configured and running for frontend features that require backend APIs.

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/IT314-Group-36/Codebase-Onboarding-Companion-Group-36.git
```

### 2. Navigate to the Frontend

```bash
cd Codebase-Onboarding-Companion-Group-36/frontend
```

### 3. Install Dependencies

```bash
npm install
```

### 4. Configure Environment Variables

Create a local environment file if required:

```bash
cp .env.example .env.local
```

The default API base URL is:

```env
VITE_API_BASE_URL=/api
```

Do not commit `.env.local` or other files containing private credentials.

### 5. Start the Development Server

```bash
npm run dev
```

The Vite development server runs at:

```text
http://localhost:5173
```

## Backend Connection

The frontend communicates with the FastAPI backend through its API service layer.

During local development, Vite is configured to proxy requests beginning with `/api` to:

```text
http://localhost:8000
```

Make sure the backend is running on port `8000` when using features that require backend communication.

## Available Scripts

Run these commands from the `frontend/` directory.

| Command | Description |
|---|---|
| `npm install` | Install project dependencies |
| `npm run dev` | Start the development server |
| `npm run lint` | Run ESLint checks |
| `npm run build` | Build the production frontend |
| `npm run preview` | Preview the production build |

## Development Workflow

1. Start the FastAPI backend using the instructions in the root project README.
2. Open a separate terminal and navigate to the `frontend/` directory.
3. Install dependencies if you have not already done so.
4. Run `npm run dev`.
5. Open the local development URL in your browser.
6. Make frontend changes and validate them using ESLint and the production build.

## Validation

Before submitting frontend changes, run:

```bash
npm run lint
npm run build
```
Both commands should complete successfully.


**IT314 – Group 36**

Codebase Onboarding Companion Project.