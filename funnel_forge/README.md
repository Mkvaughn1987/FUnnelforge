# Funnel Forge - Modular Structure

## Overview

Funnel Forge has been refactored into a modular structure for better maintainability, stability, and ease of updates.

## Folder Structure

```
FunnelForge/
├── run_app.py                  # Main launcher script - run this to start the app
├── funnelforge_gui.py          # Original monolithic version (kept for reference)
├── funnelforge_core.py         # Core email sending logic (unchanged)
└── funnel_forge/               # Modular application package
    ├── __init__.py             # Package initialization
    ├── app.py                  # Main application window with routing
    ├── styles.py               # All constants, colors, fonts, and helper functions
    └── sidebar.py              # Left navigation sidebar
```

## Running the Application

### Modular Version (Recommended)
```bash
python run_app.py
```

### Original Version (Fallback)
```bash
python funnelforge_gui.py
```

## Module Descriptions

### `styles.py`
Contains all shared constants, styling, and helper functions:
- **Colors**: `BG_ROOT`, `ACCENT`, `FG_TEXT`, etc.
- **Fonts**: `FONT_BASE`, `FONT_LABEL`, `FONT_FIELD_HDR`
- **Constants**: `TIME_OPTIONS`, `CONTACT_FIELDS`, `EMAIL_RE`
- **Paths**: `APP_DIR`, `USER_DIR`, `CONFIG_PATH`, `TEMPLATES_DIR`, etc.
- **Helper Functions**: `load_config()`, `save_config()`, `merge_tokens()`, `normalize_text()`, `detect_and_convert_contacts_to_official()`

### `sidebar.py`
Creates the left navigation sidebar:
- **Function**: `create_sidebar(parent, nav_callback)` - Creates sidebar with navigation buttons
- **Returns**: `(sidebar_frame, nav_buttons_dict)` - Sidebar widget and button references
- **Navigation Items**:
  - Dashboard
  - Create a campaign
  - Build emails (sub-nav)
  - Choose contact list (sub-nav)
  - Set Schedule (sub-nav)
  - Preview and Launch (sub-nav)
  - Contact Lists

### `app.py`
Main application with routing and view management:
- **Class**: `FunnelForgeApp(tk.Tk)` - Main application window
- **Router**: `_show_screen(key)` - Central navigation routing method
- **Views**: All view building methods (_build_dashboard_screen, _build_create_campaign_screen, etc.)
- **Entry Point**: `main()` - Application entry point

## Benefits of Modular Structure

### 1. **Stability**
- Navigation routing is centralized in one method
- No more broken navigation links due to duplicate button keys
- Clear separation of concerns

### 2. **Maintainability**
- Constants and styles in one place - easy to update colors/fonts globally
- Sidebar navigation logic separate from main app
- Helper functions organized and reusable

### 3. **Ease of Updates**
- Update styles once in `styles.py` - affects entire app
- Modify navigation structure in one place (`sidebar.py`)
- Router prevents navigation bugs

### 4. **Extensibility**
- Easy to add new views - just add a case in the router
- Easy to add new navigation items - just call the sidebar functions
- Clear module boundaries for future refactoring

## Migration Notes

All existing functionality is preserved. The modular version:
- ✅ Uses the same core email sending logic
- ✅ Maintains all view layouts exactly as before
- ✅ Keeps all user data paths and configurations
- ✅ Preserves all button behaviors and event handlers
- ✅ No changes to templates, contacts, or campaign logic

## Future Enhancements

The current modularization lays the groundwork for:
1. Extracting each view into its own file (view_dashboard.py, view_build_emails.py, etc.)
2. Creating base view classes for common patterns
3. Adding unit tests for individual modules
4. Further separation of business logic from UI code

## Technical Details

### Import Strategy
- `app.py` uses relative imports (`from .styles import ...`)
- Must be run as a module via `run_app.py` launcher
- All constants imported from `styles.py` to avoid duplication

### Router Pattern
The router in `app.py`:
```python
def _show_screen(self, key: str):
    # Handle navigation aliases
    screen_key = key
    if key == "contact_lists_main":
        screen_key = "contacts"  # Multiple nav items can show same screen

    # Hide all screens, show selected one
    frame = self._screens.get(screen_key)
    for screen_frame in self._screens.values():
        screen_frame.grid_remove()
    frame.grid(row=0, column=0, sticky="nsew")

    # Update nav button styles
    self._active_nav = key
    self._update_nav_styles()
```

This central router:
- Handles all navigation in one place
- Supports navigation aliases (multiple buttons → same view)
- Updates button styling automatically
- Cannot break due to missing screen definitions

## Contact & Support

For issues or questions about the modular structure, refer to the codebase comments or contact the development team.
