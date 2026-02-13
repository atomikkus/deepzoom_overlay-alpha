# Polygon Drawing Feature

## Overview

The WSI Viewer now supports client-side polygon drawing functionality, allowing users to annotate slides with custom polygons during their viewing session. All polygon data is stored in the browser's memory and is lost when the page is refreshed or closed.

## Features

### ✅ Drawing Polygons
- Click to add polygon vertices
- Double-click to complete a polygon
- Visual feedback during drawing (yellow dashed line)
- Point markers with numbers

### ✅ Viewing Polygons
- Saved polygons shown in blue with transparency
- Numbered vertices for reference
- Per-slide storage (polygons only show for their respective slide)
- Automatic updates when zooming/panning

### ✅ Managing Polygons
- Clear all polygons with one click
- Cancel drawing with ESC key
- Session-based storage (not persistent)

## User Interface

### Drawing Controls

Located in the viewer controls panel:

```
┌─────────────────────────────────┐
│ ➕ ➖ 🏠 🔄 ⛶ │ 📐 🗑️      │
│ Zoom/Nav Controls│ Draw/Clear   │
└─────────────────────────────────┘
```

**Buttons:**
- **📐 Draw Polygon** - Toggle drawing mode
- **🗑️ Clear All** - Remove all polygons

## How to Use

### Drawing a Polygon

1. **Load a slide** - Select any slide from the sidebar
2. **Click the 📐 button** - Activates drawing mode
3. **Click points** - Click anywhere on the slide to add polygon vertices
4. **Double-click to finish** - Completes the polygon (minimum 3 points required)
5. **Polygon saved** - Appears in blue and is stored for this session

### Visual Feedback

**During Drawing (yellow):**
```
   1 ●───────● 2
     │       │
     │       │
   4 ●───────● 3
```
- Yellow dashed outline
- Yellow point markers
- Crosshair cursor

**Saved Polygon (blue):**
```
   1 ●───────● 2
     │░░░░░░░│
     │░░░░░░░│
   4 ●───────● 3
```
- Blue solid outline
- Blue fill (20% opacity)
- Numbered vertices
- White point markers

### Canceling a Polygon

- Press **ESC** key during drawing
- Or click the 📐 button again to exit drawing mode

### Clearing Polygons

- Click the **🗑️ Clear All** button
- Removes all polygons from all slides

## Technical Details

### Storage
- **Client-side only** - No server communication
- **Memory-based** - Stored in JavaScript arrays
- **Session-scoped** - Lost on page refresh/close
- **Per-slide** - Polygons tagged with slide name

### Data Structure

```javascript
{
  id: 1707331234567,              // Timestamp
  slide: "example.svs",           // Associated slide
  timestamp: "2024-02-07T12:34:56.789Z",
  points: [
    { x: 0.123, y: 0.456 },      // Viewport coordinates
    { x: 0.234, y: 0.567 },
    { x: 0.345, y: 0.678 },
    ...
  ]
}
```

### Coordinate System

- Uses **OpenSeadragon viewport coordinates** (normalized 0-1)
- Automatically scales with zoom/pan
- Converted to pixel coordinates for SVG rendering

### Performance

- Lightweight SVG rendering
- Redraws on viewport changes (zoom, pan, rotate)
- Handles multiple polygons efficiently

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **ESC** | Cancel current polygon / Exit drawing mode |

## Button States

### 📐 Draw Polygon Button

| State | Appearance | Tooltip |
|-------|-----------|---------|
| **Inactive** | White background | "Draw Polygon" |
| **Active** | Blue background, white icon | "Click to finish polygon (or ESC to cancel)" |

### 🗑️ Clear All Button

- Always enabled when polygons exist
- Shows toast if no polygons to clear

## Notifications

| Action | Toast Message | Type |
|--------|--------------|------|
| Drawing mode ON | "Drawing mode: Click to add points, double-click to finish" | Info |
| First point | "First point added. Continue adding points." | Success |
| 2nd point | "2 points. Double-click to finish." | Info |
| 3+ points | "N points" | Info |
| Polygon saved | "Polygon saved (N points)" | Success |
| Drawing cancelled | "Polygon drawing cancelled" | Info |
| Cleared | "Cleared N polygon(s)" | Success |
| No polygons | "No polygons to clear" | Info |

## Limitations

### Current Limitations

1. **No persistence** - Polygons lost on page refresh
2. **No editing** - Cannot modify saved polygons
3. **No deletion** - Can only clear all, not individual polygons
4. **No export** - Cannot save polygon data to file
5. **No import** - Cannot load pre-existing annotations

### Design Decisions

- **Session-only storage** as requested by user
- **Simple workflow** - Draw → Save → Clear
- **Minimal UI** - Two buttons only
- **Automatic cleanup** - Polygons filtered by slide

## Future Enhancement Ideas

If persistence is needed later:

- Export polygons as JSON
- Import polygons from file
- Save to server (optional backend API)
- Edit/delete individual polygons
- Polygon labels and categories
- Measurement tools (area, perimeter)
- Polygon properties (color, opacity, stroke)

## Code Files

### Modified Files

1. **index.html** - Added drawing control buttons
2. **viewer.js** - Added polygon drawing logic
3. **styles.css** - Added button styles

### Key Functions

```javascript
// Toggle drawing mode on/off
toggleDrawingMode()

// Handle click during drawing
handlePolygonClick(event)

// Finish and save polygon
finishPolygon(event)

// Update SVG overlay
updatePolygonOverlay()

// Clear all polygons
clearAllPolygons()

// Initialize SVG overlay
initializePolygonOverlay()
```

## Browser Compatibility

Works in all modern browsers supporting:
- SVG rendering
- ES6 JavaScript
- OpenSeadragon 4.1.0+

Tested on:
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Troubleshooting

### Polygon not appearing

- **Check drawing mode** - 📐 button should be blue/active
- **Minimum points** - Need at least 3 points
- **Double-click to finish** - Single click only adds points

### Cursor not changing

- Drawing mode may not be active
- Try toggling the 📐 button again

### Polygons disappear

- Switching slides filters polygons per-slide
- Check if you're viewing the correct slide
- Session-based storage - refresh loses all data

### Can't click slide

- Exit drawing mode (click 📐 or press ESC)
- Drawing mode captures all clicks

## Examples

### Simple 4-Point Rectangle

1. Click 📐 to start
2. Click top-left
3. Click top-right
4. Click bottom-right
5. Click bottom-left
6. Double-click to finish

### Complex Multi-Point Polygon

1. Click 📐 to start
2. Click points around region of interest
3. Add as many points as needed (10, 20, 50+)
4. Double-click anywhere to complete

### Quick Annotation Workflow

1. Load slide → 📐 → Draw → Double-click
2. Repeat for multiple regions
3. 🗑️ to clear when done
4. Switch slides - previous polygons preserved per slide
