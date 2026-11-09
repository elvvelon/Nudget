# Nudget — AI-Powered Kanban & Anti-Procrastination Hub

## Overview

**The Problem:**
Student teams and indie developers often struggle with two major bottlenecks when starting a new project: **initial task paralysis** (spending hours manually breaking down raw assignment requirements or specs into actionable tickets) and **silent procrastination** (tasks sitting idle in "In Progress" for days while deadlines quietly approach). Traditional tools act as passive storage for cards—they don't help you decompose unstructured requirements, nor do they actively hold team members accountable in a fun, engaging way.

**Who It’s For:**

Student project groups, hackathon squads, and small development teams looking for a lightweight, developer-friendly Kanban workspace that actively assists in planning and keeps momentum going through smart Discord integrations.

---

## Our Team

* [Danylo Maister](https://github.com/elvvelon)
* [Anastasiia Yermak](https://github.com/nastyaermak)

---

## Core Functionality

* **JWT Authentication & User Profiles:** Secure sign-up, login, token refresh, and personal profile management.

* **Workspace & Board Management:** Create and customize project boards with configurable columns (e.g., `Backlog`, `To Do`, `In Progress`, `Code Review`, `Done`).

* **Rich Task Cards:** Create, edit, and reorder cards featuring descriptions, priority levels (`Low`, `Medium`, `High`, `Critical`), due dates, and team member assignments.

* **Actionable Subtasks (Checklists):** Break individual cards down into trackable checklist items to monitor granular progress.

* **Activity & Stagnation Tracking:** Automatic tracking of card state transitions and `updated_at` timestamps to detect idle or blocked tasks.

---

## User Roles & Permissions

Roles are assigned **per board** (`BoardMembership`), allowing a user to be a Team Lead on one project and a Guest on another:

| Role | Capabilities & Permissions |
| :--- | :--- |
| **Owner (Team Lead)** | • Full control over board settings, columns, and deletion.<br>• Invite/remove board members and assign roles.<br>• Configure the Discord Webhook URL and select the AI Nudge tone.<br>• Trigger AI requirement breakdowns and bulk-approve tasks.<br>• Move cards from `Code Review` to `Done` (final approval). |
| **Member (Contributor)** | • Create, edit, and assign task cards.<br>• Move cards across workflow columns (up to `Code Review`).<br>• Manage and check off subtasks.<br>• Trigger manual "Nudge" reminders for stagnant tasks. |
| **Viewer (Guest)** | • Read-only access to the board, columns, cards, and progress checklists.<br>• Cannot modify board state, create tasks, or trigger notifications. |

---

## Beyond CRUD: Key Differentiators

To satisfy advanced project requirements, Nudget implements two core non-trivial features:

### 1. **AI-Powered Task Breakdown (LLM Integration):**
* Users can send raw, unstructured text (such as project requirements or a assignment description) to `POST /api/boards/{id}/ai-breakdown`.
* The backend uses an external LLM to parse the text and return a structured JSON draft of recommended task cards and subtasks.
* **Human-in-the-Loop Workflow:** The draft is displayed on the frontend for user review. Once approved, the selected tasks are saved, preventing database pollution.

### 2. **Uniform Discord Notifications & Procrastination Nudging:**
* Each board can be linked to a Discord channel via a standard webhook URL.
* **Automated & Manual Alerts:** When a task sits stagnant in progress without updates for too long, a uniform structured notification is dispatched to the team's Discord channel.
* Team members can also manually trigger a **"Nudge"** button on any stalled card to ping the assigned user via Discord, keeping everyone accountable without over-engineering text generation.