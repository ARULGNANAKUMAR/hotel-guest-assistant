# Azure Bay Hotel — AI-Powered Hotel Guest Assistant

> A full-stack conversational hotel guest assistant that answers hotel questions, collects missing availability details across multiple turns, checks deterministic mock room availability, and optionally uses an LLM only where conversational phrasing is useful.

<p>
  <strong style="color:#b00020;">⚠️ DEVELOPMENT STATUS / TIME-CONSTRAINED NOTE</strong>
</p>

<p style="color:#b00020;">
This submission was completed under a strict development-time constraint. The core guest-assistant workflow, frontend, backend services, knowledge base, availability engine, conversation context, LLM abstraction, fallback handling, tests, and project documentation were implemented. Some deeper production-oriented development items could not be completed within the available time and are intentionally documented in the <strong>Deferred Development & Future Work</strong> section instead of being presented as completed features.
</p>

---

## 1. Project Overview

The **AI-Powered Hotel Guest Assistant** is designed to reduce repetitive hotel-support questions and make room-availability conversations easier for guests.

Instead of forcing a guest to navigate multiple pages or forms, the guest can simply type natural questions such as:

- "What time is check-in?"
- "Do you have Wi-Fi?"
- "Is breakfast included?"
- "I need a room for 2 adults."
- "2026-10-01 to 2026-10-03"

The assistant responds conversationally and collects only the information that is still missing.

The project intentionally separates **AI-powered conversational phrasing** from **deterministic business logic**. Room availability is calculated by code from structured mock inventory rather than being invented by an LLM.

---

# 2. Customer Problem

Hotel guests repeatedly ask common questions about:

- Check-in and check-out
- Breakfast
- Wi-Fi
- Parking
- Pool
- Cancellation
- Room types
- Room availability

A conventional hotel website can require guests to search through multiple pages before finding this information.

For availability, the guest also needs to provide multiple values:

1. Check-in date
2. Check-out date
3. Number of adults

The assistant turns this into a short multi-turn conversation.

### Example

```text
Guest:
I need a room for 2 adults.

Assistant:
Sure. What are your check-in and check-out dates?

Guest:
2026-10-01 to 2026-10-03

Assistant:
Here are the available room types...
```

---

# 3. Solution

The application provides a conversational interface connected to a backend assistant service.

The backend combines:

- Curated hotel knowledge
- Deterministic intent detection
- Conversation context
- Deterministic room availability
- Optional LLM phrasing
- Safe fallback behaviour

The LLM is deliberately restricted.

It does **not** decide:

- Room availability
- Room capacity
- Number of guests
- Dates
- Business rules
- Hotel facts

Those decisions remain controlled by application code and structured data.

---

# 4. Core Features

## Guest Chat

The React interface provides:

- Conversation view
- User and assistant messages
- Suggestion buttons
- Loading state
- Error state
- Responsive layout
- Availability result cards

## Hotel Knowledge Base

Hotel information is stored in:

```text
backend/app/data/hotel_data.json
```

The assistant can answer supported questions about:

- Check-in
- Check-out
- Breakfast
- Pool
- Wi-Fi
- Parking
- Cancellation
- Room types
- Hotel information

## Availability Conversation

The assistant detects when the guest is trying to check availability.

It collects:

```text
check-in
check-out
adults
```

If one or more values are missing, it asks for only the missing information.

## Conversation Context

The conversation context contains values such as:

```json
{
  "checkIn": "2026-10-01",
  "checkOut": "2026-10-03",
  "adults": 2,
  "last_intent": "availability"
}
```

The frontend sends the returned context back on the next turn.

New explicit values override older values.

## Deterministic Availability

Room inventory is stored in:

```text
backend/app/data/availability_data.json
```

The availability service filters rooms according to guest capacity.

Example mock inventory:

```text
Deluxe Room  → up to 2 adults → 5 rooms
Family Room  → up to 4 adults → 3 rooms
Suite        → up to 3 adults → 2 rooms
```

This is intentionally deterministic.

## Optional LLM Layer

The optional LLM layer is used for conversational phrasing of already-known hotel answers.

The application can still operate without an LLM.

If the LLM:

- is not configured
- times out
- returns an HTTP error
- returns an invalid response
- returns an empty response

the deterministic answer is returned instead.

---

# 5. User Journey

### Step 1 — FAQ

```text
Guest:
What time is check-in?

Assistant:
Check-in is at 2:00 PM.
```

The answer is grounded in the hotel knowledge base.

### Step 2 — Start Availability

```text
Guest:
I need a room for 2 adults.
```

The assistant recognizes an availability request and asks for the missing dates.

### Step 3 — Provide Dates

```text
Guest:
2026-10-01 to 2026-10-03
```

The assistant merges the new dates with the previously collected adult count.

### Step 4 — Deterministic Availability

The availability service checks the mock inventory and returns suitable room types.

### Step 5 — Continue Conversation

The guest can ask:

```text
Is breakfast included?
```

The FAQ answer is returned while the previously collected availability context remains available.

### Step 6 — Unsupported Request

For something outside the supported hotel knowledge base, the assistant uses a safe fallback rather than inventing an answer.

---

# 6. Architecture

```text
                         ┌──────────────────────┐
                         │        Guest         │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    React Chat UI     │
                         │       + Vite         │
                         └──────────┬───────────┘
                                    │
                                    │ POST /api/assistant
                                    │ POST /api/availability
                                    ▼
                         ┌──────────────────────┐
                         │    FastAPI Backend   │
                         └──────────┬───────────┘
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │ Assistant Orchestrator  │
                       │ assistant_service.py    │
                       └────────────┬────────────┘
                                    │
              ┌─────────────────────┼──────────────────────┐
              │                     │                      │
              ▼                     ▼                      ▼
      ┌───────────────┐     ┌──────────────┐     ┌────────────────┐
      │ Knowledge Base│     │   Context    │     │ LLM Phrasing   │
      │ hotel_data    │     │ multi-turn   │     │ optional       │
      └───────────────┘     └──────────────┘     └────────────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Deterministic        │
                         │ Availability Service │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Mock Room Inventory  │
                         │ availability_data    │
                         └──────────────────────┘
```

### Architectural principle

The most important architectural decision is:

```text
LLM = conversational assistance
Business logic = deterministic application code
```

This reduces the risk of an LLM inventing room availability or changing business rules.

---

# 7. Technology Stack

## Frontend

- React 18
- Vite 5
- JavaScript / JSX
- Plain CSS

## Backend

- Python
- FastAPI
- Pydantic
- Uvicorn
- python-dotenv

## Data

- JSON knowledge base
- JSON mock room inventory
- No database in the current version

## AI

- Optional Anthropic Messages API integration
- LLM is used only for controlled conversational phrasing

## Testing

- Python `unittest`
- Flask test client for the service-layer test harness
- Node-based frontend integration tests
- Browser E2E test infrastructure

---

# 8. Project Structure

```text
hotel-guest-assistant/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── assistant.py
│   │   │       └── availability.py
│   │   │
│   │   ├── core/
│   │   │   └── config.py
│   │   │
│   │   ├── data/
│   │   │   ├── hotel_data.json
│   │   │   └── availability_data.json
│   │   │
│   │   ├── schemas/
│   │   │   ├── assistant.py
│   │   │   └── availability.py
│   │   │
│   │   ├── services/
│   │   │   ├── assistant_service.py
│   │   │   ├── availability_service.py
│   │   │   ├── knowledge_service.py
│   │   │   └── llm_service.py
│   │   │
│   │   └── main.py
│   │
│   └── tests/
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── services/
│   │   ├── App.jsx
│   │   └── main.jsx
│   └── tests/
│
├── e2e/
│
├── .env.example
├── .gitignore
├── README.md
└── run_tests.sh
```

---

# 9. Backend API

## `GET /`

Returns the API banner.

## `GET /health`

Health-check endpoint.

Example:

```json
{
  "status": "ok"
}
```

## `POST /api/assistant`

Main conversational endpoint.

Request:

```json
{
  "message": "What time is check-in?",
  "context": {}
}
```

The response contains:

```text
message
type
requires_input
data
context
```

Possible response types include:

```text
text
fallback
error
availability_request
availability_result
availability_error
```

## `POST /api/availability`

Direct deterministic availability check.

Example:

```json
{
  "checkIn": "2026-10-01",
  "checkOut": "2026-10-03",
  "adults": 2
}
```

The endpoint returns room availability based on the structured mock inventory.

---

# 10. Availability Logic

The application validates:

- ISO date format: `YYYY-MM-DD`
- Check-in date
- Check-out date
- Check-out after check-in
- Adults greater than zero
- Room capacity

The room is included only when:

```text
room.max_adults >= requested_adults
```

This makes the result deterministic and testable.

### Important limitation

The current inventory is sample inventory.

It does not connect to a real hotel PMS or booking engine and does not dynamically decrease inventory after a booking.

---

# 11. AI / LLM Design

The LLM is intentionally not treated as the source of truth.

### Deterministic layer

The application first determines:

- supported intent
- hotel fact
- required availability fields
- guest count
- dates
- availability result

### LLM layer

Only after a correct hotel answer is available can the optional LLM make the response sound more natural.

Conceptually:

```text
Hotel Data
    ↓
Correct Deterministic Answer
    ↓
Optional LLM Rephrasing
    ↓
Guest
```

Not:

```text
Guest
 ↓
LLM
 ↓
"Maybe we have 5 rooms"
```

This distinction is important because availability is business-critical information.

---

# 12. Hallucination Prevention

The project uses multiple safeguards.

### 1. Curated knowledge

Hotel answers come from the local knowledge base.

### 2. Deterministic availability

Room availability comes from application code and structured inventory.

### 3. Restricted LLM role

The LLM is not allowed to make availability decisions.

### 4. Safe fallback

Unsupported questions receive a controlled fallback instead of a guessed answer.

### 5. Failure fallback

If the LLM fails, the deterministic response remains available.

---

# 13. Context Handling

The backend itself is stateless for conversation state.

The frontend sends the previous context back to the backend.

Example:

```text
Turn 1:
"I need a room for 2 adults."

Context:
adults = 2
```

Turn 2:

```text
"2026-10-01 to 2026-10-03"
```

Merged context:

```text
adults = 2
checkIn = 2026-10-01
checkOut = 2026-10-03
```

The availability engine can then run.

This design keeps the current prototype simple while making the context contract explicit.

---

# 14. Error and Fallback Behaviour

| Scenario | Current behaviour |
|---|---|
| Supported FAQ | Knowledge-base answer |
| Unsupported question | Safe fallback |
| Missing adults | Ask for adults |
| Missing dates | Ask for dates |
| Invalid date | Availability error |
| Checkout before/equal check-in | Validation error |
| Party exceeds room capacity | No suitable room |
| LLM unavailable | Deterministic response |
| Backend/network failure | Frontend error state |
| Empty input | Validation prevents submission |
| Natural date such as "tomorrow" | Does not guess; asks for ISO dates |

---

# 15. Testing and Evaluation

The project contains backend, frontend integration, and browser-oriented test infrastructure.

The current test environment reported:

- **Backend:** 303 tests passed through the available service/test harness
- **Frontend:** 39 integration tests passed
- **Browser E2E:** 5 browser tests passed in the available E2E environment

The backend service-layer journey was also exercised across:

- FAQ
- availability start
- multi-turn context
- availability completion
- unsupported questions
- invalid dates
- over-capacity requests
- mid-flow FAQ

### Important testing limitation

Because the available submission environment did not have the complete frontend/backend runtime dependencies installed, the final check did not include a complete production-style:

```text
React build
    ↓
real browser
    ↓
real FastAPI server
```

execution.

The existing browser E2E infrastructure uses a lightweight test harness/static frontend path. This is documented honestly rather than presented as a full production E2E setup.

---

# 16. Product Decisions

## Why conversational UI?

Hotel guests naturally ask questions in conversational language.

A chat interface also makes availability collection easier because the assistant can request missing values one at a time.

## Why deterministic availability?

Availability is a factual business operation.

A deterministic service:

- is predictable
- is testable
- can be audited
- cannot invent room counts
- keeps business rules outside the LLM

## Why use an LLM?

An LLM is useful for:

- natural conversational wording
- making responses less robotic
- controlled FAQ rephrasing

It is not necessary for deterministic calculations.

## What happens if the AI dependency fails?

The assistant continues using deterministic responses.

The guest should still be able to receive hotel information and availability-related guidance without the LLM.

---

# 17. Deferred Development & Future Roadmap

<p style="color:#b00020;">
<strong>⚠️ The following items were not fully developed in this submission because of the limited development time available for the assignment.</strong>
</p>

These are intentionally listed as **future development**, not as completed functionality.

## Phase 1 — Production Inventory Integration

Replace the static JSON inventory with a real hotel PMS / booking-engine integration.

Future work:

- date-aware inventory
- live room availability
- rate plans
- room pricing
- occupancy rules
- reservation synchronization

```text
Current:
JSON Inventory
     ↓
Availability Service

Future:
Hotel PMS / Booking Engine
     ↓
Availability API
     ↓
Assistant
```

## Phase 2 — Booking Workflow

Add a complete booking flow:

```text
Availability
    ↓
Room Selection
    ↓
Guest Details
    ↓
Booking Confirmation
    ↓
Payment
    ↓
Reservation
```

The current project intentionally stops at availability.

## Phase 3 — Database

Move persistent data from JSON files into a database.

Potential data models:

- Hotels
- Rooms
- Inventory
- FAQs
- Conversations
- Guests
- Reservations
- Audit logs

## Phase 4 — Persistent Conversation Storage

Currently context lives in the browser session.

Future implementation:

```text
Guest
 ↓
Conversation ID
 ↓
Backend
 ↓
Database / Redis
```

This would allow conversation recovery after page refresh or across devices.

## Phase 5 — Better Natural-Language Date Understanding

Current implementation intentionally expects:

```text
YYYY-MM-DD
```

Future versions could safely support:

- tomorrow
- next Friday
- this weekend
- next month

A date parser should normalize these expressions before deterministic availability is executed.

## Phase 6 — Better Intent Detection

The current intent detection is deterministic and keyword-based.

Future development could introduce:

- classifier model
- embedding-based retrieval
- semantic intent matching
- confidence thresholds
- human-readable intent debugging

The deterministic fallback should remain available.

## Phase 7 — Retrieval-Augmented Knowledge Base

For a larger hotel knowledge base:

```text
Guest Question
      ↓
Retriever
      ↓
Relevant Hotel Documents
      ↓
Grounded LLM Response
```

The model should still be restricted to retrieved hotel information.

## Phase 8 — Real Browser E2E

Build a complete environment where tests start:

```text
React/Vite
    +
FastAPI
```

and Playwright interacts with the actual running application.

Future E2E coverage:

- FAQ
- availability
- multi-turn context
- loading
- backend failure
- malformed API response
- mobile viewport
- unsupported questions

## Phase 9 — Security Hardening

Production deployment should add:

- authentication/authorization where required
- rate limiting
- request-size limits
- structured security logging
- secret management
- CORS restrictions
- abuse protection
- audit logging

## Phase 10 — Observability

Production monitoring should track:

- request latency
- error rate
- fallback rate
- LLM failure rate
- availability query success
- unanswered questions
- conversation completion
- user satisfaction

## Phase 11 — Multilingual Support

Potential future languages:

- English
- Tamil
- Hindi
- other hotel target languages

The knowledge layer should remain the source of truth across languages.

## Phase 12 — Production Deployment

Future deployment could include:

```text
Frontend
   ↓
CDN / Hosting

Backend
   ↓
Cloud API

Database
   ↓
Managed Database

Monitoring
   ↓
Logs + Metrics + Alerts
```

---

# 18. Production-Level AI Improvements

A future production AI architecture could be:

```text
Guest
 ↓
Intent / Safety Layer
 ↓
Conversation State
 ↓
Knowledge Retrieval
 ├── Hotel FAQ
 ├── Room Information
 └── Policies
 ↓
Deterministic Business Tools
 ├── Availability
 ├── Booking
 └── Payment
 ↓
Grounded Response Generator
 ↓
Guest
```

The central principle should remain:

> **AI can assist reasoning and communication, but business-critical hotel operations should remain controlled by deterministic tools and validated data.**

---

# 19. Current Limitations

The current prototype does not include:

- Real hotel PMS integration
- Real-time inventory
- Booking
- Payment
- Authentication
- Database persistence
- Persistent server-side conversations
- Multilingual support
- Production deployment
- Natural-language date normalization
- Production-grade observability
- Complete production React-to-backend browser E2E
- Live LLM provider testing in the submission environment

These limitations are intentional and are documented so the current prototype does not overclaim production readiness.

---

# 20. Running the Project

## Requirements

- Python 3.10+
- Node.js 18+

## Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open:

```text
http://localhost:5173
```

The Vite development server proxies API requests to the backend.

---

# 21. Environment Configuration

Copy:

```text
.env.example
```

to:

```text
.env
```

Only configure the optional LLM credentials if an LLM provider is available.

Never commit real API keys.

The project `.gitignore` is configured to keep local environment secrets out of source control.

---

# 22. Example Conversation

```text
Guest:
What time is check-in?

Assistant:
Check-in is at 2:00 PM.

Guest:
I need a room for 2 adults.

Assistant:
Sure. What are your check-in and check-out dates?

Guest:
2026-10-01 to 2026-10-03

Assistant:
Available rooms:
- Deluxe Room
- Family Room
- Suite

Guest:
Is breakfast included?

Assistant:
[Hotel knowledge-base breakfast answer]
```

The important part of this journey is that the assistant can switch between:

```text
FAQ
  ↕
Availability
  ↕
Follow-up
```

without losing the collected availability context.

---

# 23. Development Approach

The project was developed incrementally rather than as one large implementation.

The development progression was:

```text
Account 1
Foundation
   ↓
Account 2
Backend API structure
   ↓
Account 3
Hotel knowledge base
   ↓
Account 4
Availability engine + intent handling
   ↓
Account 5
Conversation context + multi-turn flow
   ↓
Account 6
React chat UI + API integration + UI polish
   ↓
Account 7
Testing, reliability, AI layer, evaluation
   ↓
Finalization
Documentation + evaluation + future roadmap
```

This incremental approach reduced the risk of breaking previously completed functionality.

---

# 24. AI Tools Used During Development

**Claude** was used throughout development for:

- architecture assistance
- code generation
- debugging
- test creation
- frontend implementation
- backend implementation
- AI/LLM integration
- documentation
- code review and refinement

The runtime assistant can optionally use an Anthropic-compatible LLM configuration.

---

# 25. Final Project Position

This submission should be understood as a **working prototype / assignment implementation**, not a production hotel reservation platform.

The most important implemented workflow is:

```text
Guest Question
      ↓
Conversational Assistant
      ↓
Knowledge / Context
      ↓
Missing Information Collection
      ↓
Deterministic Availability
      ↓
Structured Result
      ↓
Follow-up Conversation
```

The architecture is intentionally designed so that future production capabilities can be added without making the LLM responsible for critical hotel business decisions.

---

## Final Note

<p style="color:#b00020;">
<strong>Development-time constraint:</strong> Due to the limited time available before submission, some production-oriented files and deeper integrations could not be completed. They are explicitly documented above as future development items. The current submission prioritizes the core working guest-assistant journey, deterministic availability, AI-assisted conversational phrasing, fallback safety, frontend experience, and test coverage over unfinished production features.
</p>
