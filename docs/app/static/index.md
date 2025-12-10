# Main Chat Interface Documentation

**File**: `app/static/index.html`
**Logic**: `app/static/js/app.js`
**Styles**: `app/static/css/styles.css`

## Overview
The Main Chat Interface provides the primary user interaction point for the Support Chatbot. It is a Single Page Application (SPA) designed for robustness, accessibility, and a seamless user experience.

## Architecture

### Separation of Concerns
*   **HTML (`index.html`)**: Defines the semantic structure, including the sidebar, chat area, and modals. content is updated dynamically via JavaScript.
*   **JavaScript (`js/app.js`)**: Encapsulates all application logic within a `ChatApp` class. This class handles state management, API communication, event listeners, and UI updates.
*   **CSS (`css/styles.css`)**: Contains all styling, including dark mode variables (`:root[data-theme="dark"]`) and responsive design rules.

### `ChatApp` Class
The `ChatApp` class initializes on `DOMContentLoaded` and manages:
*   **State**: Conversation history (persisted in `sessionStorage`), network status, speech recognition state, and generating state.
*   **Network Handling**: Monitors `navigator.onLine` to provide real-time status updates ("Online"/"Offline").
*   **API Communication**: Uses `fetch` with `AbortController` for streaming responses from `/api/v1/chat`.
*   **Security**: Sanitizes user inputs and validates session storage data to prevent crashes.

## Key Features

### 1. Robust Streaming Chat
*   **Real-time Streaming**: Bot responses are streamed to the client using `TextDecoder` and rendered incrementally.
*   **Markdown Rendering**: `marked.js` parses bot responses, supporting headers, lists, code blocks, and bold text.
*   **Stop Generation**: User can abort a running response generation at any time.

### 2. Accessibility (a11y)
*   **Keyboard Navigation**: All interactive elements (including "div-buttons" like history items) differ `tabindex="0"`, `role="button"`, and support Enter/Space activation.
*   **Screen Reader Support**:
    *   `aria-live="polite"` regions for chat messages and typing indicators ensure blind users are notified of updates.
    *   `aria-labels` provided for all icon-only buttons.
*   **Focus Management**: Modals trap focus when open and restore focus to the triggering element upon closure.

### 3. Speech & Multimedia
*   **Speech Recognition**: Integrated `webkitSpeechRecognition` for voice input.
*   **Text-to-Speech**: `window.speechSynthesis` reads out bot responses (toggleable).
*   **Image Support**: Users can upload images via button or paste from clipboard/drag-and-drop.

### 4. Resilience
*   **Offline Handling**: Prevents message sending when offline and updates UI status.
*   **Error Recovery**: Gracefully handles network errors, API failures, and JSON parsing errors during storage restoration.

## Development & Maintenance

### File Structure
```
app/static/
├── css/
│   └── styles.css      # Core styles
├── js/
│   └── app.js          # Main application logic
├── index.html          # Chat interface structure
└── logo.png            # Application logo
```

### Future Improvements
*   **Unit Tests**: Add Jest tests for `ChatApp` logic.
*   **Localization**: Expand the language dropdown to support dynamic UI translation (currently only passes language code to backend).

