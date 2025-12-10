# Admin Panel Documentation

**Location**: `app/static/admin/`

## Overview
The Admin Panel provides a dashboard for monitoring chatbot usage, user feedback, and financial metrics. It is a single-page application (SPA) built with vanilla HTML/CSS/JS that interacts with the backend API.

## Components

### 1. `index.html`
The entry point for the admin interface.
-   **Structure**:
    -   **Sidebar**: Navigation links (`Overview`, `Trends`, `Spend`).
    -   **Main Content**: Dynamic `div` sections toggled via visibility classes.
    -   **Dependencies**: Font Awesome (Icons), Chart.js (Visualizations), Marked.js (Markdown rendering).

### 2. `admin.js`
Contains all frontend logic, initialization, and event handling.
-   **Key Features**:
    -   **`safeFetch(url)`**: A wrapper around `fetch` that automatically checks `res.ok` and throws errors for non-2xx responses.
    -   **`loadStats()`**: Fetches aggregate summary data (daily/weekly counts, feedback scores).
    -   **`loadTrend(days)`**: Visualizes message volume and satisfaction rates over time using Chart.js. Handles race conditions with a `trendLoadId`.
    -   **`loadFeedback()`**: Fetches and renders paginated user feedback cards with "Load More" functionality.
    -   **`loadSpend()`**: Displays financial metrics (token usage, estimated cost).
    -   **Security**: Uses `escapeHtml()` to sanitize user inputs and prevents XSS. Markdown rendering is handled via `marked.parse` for bot responses.

### 3. `admin.css`
Styles for the dashboard.
-   **Design System**: Dark mode theme with a blue/purple accent palette.
-   **Components**:
    -   `.stat-card`: Summary metric boxes.
    -   `.feedback-detail-card`: Expandable accordion for user feedback.
    -   `.spinner-overlay`: Loading state overlay.
    -   `.error-overlay`: Visual feedback for failed chart loads.

## API Integration

The admin panel consumes the following endpoints:

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/v1/admin/summary` | GET | High-level usage stats. |
| `/api/v1/admin/spend` | GET | Cost and token usage breakdown. |
| `/api/v1/admin/feedback` | GET | Paginated list of positive/negative feedback. |
| `/api/v1/admin/messages-trend` | GET | Historical message volume. |
| `/api/v1/admin/feedback-trend` | GET | Historical satisfaction rates. |

## Development & Maintenance

### Accessibility
-   All interactive elements (tabs, nav items) support keyboard navigation (`Tab` + `Enter`/`Space`).
-   Sidebar items have `role="button"` and `tabindex="0"`.

### Error Handling
-   Network errors are caught and logged.
-   UI displays "Err" or error overlays instead of crashing.
-   `safeFetch` ensures consistent error propagation.

### Adding New Features
1.  **New View**: Add a new `.view` div in `index.html` and a `.nav-item` in the sidebar. Add logic in `admin.js` navigation handler.
2.  **New Chart**: Add a `<canvas>` element and initialize a new `Chart` instance in a dedicated load function.

