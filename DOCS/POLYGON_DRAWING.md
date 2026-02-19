# Polygon Drawing Feature

## Overview

The WSI Viewer now supports client-side polygon drawing functionality, allowing users to annotate slides with custom polygons during their viewing session. All polygon data is stored in the browser's memory and is lost when the page is refreshed or closed.

## Features

### ✅ Drawing Polygons
- Click to add polygon vertices
- Double-click to complete a polygon
- Visual feedback during drawing (yellow dashed line)
- Point markers with numbers
- Label each polygon after completion

### ✅ Viewing Polygons
- Saved polygons shown in blue with transparency
- Labels displayed at polygon center
- Numbered vertices for reference
- Per-slide storage (polygons only show for their respective slide)
- Automatic updates when zooming/panning
- Polygons persist when toggling drawing mode off

### ✅ Managing Polygons
- Delete individual polygons (delete mode)
- Clear all polygons with confirmation
- Cancel drawing with ESC key
- Session-based storage (not persistent)

## User Interface

### Drawing Controls

Located in the viewer controls panel:

```
┌─────────────────────────────────────┐
│ ➕ ➖ 🏠 🔄 ⛶ │ 📐 🗑 🗑️    │
│ Zoom/Nav Controls│ Draw/Del/Clear │
└─────────────────────────────────────┘
```

**Buttons:**
- **📐 Draw Polygon** - Toggle drawing mode (polygons persist)
- **🗑 Delete** - Toggle delete mode (click polygons to delete)
- **🗑️ Clear All** - Remove all polygons (with confirmation)

## How to Use

### Drawing a Polygon

1. **Load a slide** - Select any slide from the sidebar
2. **Click the 📐 button** - Activates drawing mode
3. **Click points** - Click anywhere on the slide to add polygon vertices
4. **Double-click to finish** - Completes the polygon (minimum 3 points required)
5. **Enter label** - A prompt appears to optionally label your polygon
6. **Polygon saved** - Appears in blue with label and is stored for this session
7. **Continue drawing** - Drawing mode stays active, draw more polygons or click 📐 to exit

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
     │  LABEL │  ← Label at center
     │░░░░░░░│
   4 ●───────● 3
```
- Blue solid outline
- Blue fill (20% opacity)
- Numbered vertices
- Label in blue box at center
- White point markers

**Delete Mode (red):**
```
   1 ●───────● 2
     │▒▒▒▒▒▒▒│
     │  LABEL │  ← Red background
     │▒▒▒▒▒▒▒│
   4 ●───────● 3
```
- Red outline
- Red fill (30% opacity)
- Red point markers
- Label in red box
- Pointer cursor

### Canceling a Polygon

- Press **ESC** key during drawing to discard incomplete polygon
- Or click the 📐 button to exit drawing mode (saved polygons remain)

### Deleting Individual Polygons

1. **Click the 🗑 Delete button** - Activates delete mode
2. **Polygons turn red** - Visual indicator of delete mode
3. **Click a polygon** - Confirmation prompt appears
4. **Confirm deletion** - Polygon is removed
5. **Press ESC or click 🗑 again** - Exit delete mode

### Clearing All Polygons

- Click the **🗑️ Clear All** button
- Confirmation prompt appears
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
  label: "Tumor region",          // User-defined label (optional)
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
| **ESC** | Cancel current polygon / Exit drawing mode / Exit delete mode |

## Button States

### 📐 Draw Polygon Button

| State | Appearance | Tooltip |
|-------|-----------|---------|
| **Inactive** | White background | "Draw Polygon" |
| **Active** | Blue background, white icon | "Stop drawing (polygons will persist)" |

### 🗑 Delete Button

| State | Appearance | Tooltip |
|-------|-----------|---------|
| **Inactive** | White background | "Delete Individual Polygons" |
| **Active** | Blue background, white icon | "Exit delete mode" |

### 🗑️ Clear All Button

- Always enabled
- Shows confirmation before deleting all
- Shows toast if no polygons to clear

## Notifications

| Action | Toast Message | Type |
|--------|--------------|------|
| Drawing mode ON | "Drawing mode: Click to add points, double-click to finish" | Info |
| First point | "First point added. Continue adding points." | Success |
| 2nd point | "2 points. Double-click to finish." | Info |
| 3+ points | "N points" | Info |
| Polygon saved (with label) | "Polygon 'Label' saved (N points)" | Success |
| Polygon saved (no label) | "Polygon saved (N points)" | Success |
| Drawing mode OFF | "Drawing mode disabled" | Info |
| Incomplete polygon | "Incomplete polygon discarded" | Info |
| Delete mode ON | "Delete mode: Click on a polygon to delete it" | Info |
| Delete mode OFF | "Delete mode disabled" | Info |
| Polygon deleted | "Polygon 'Label' deleted" | Success |
| Click in delete mode | "Click on a polygon to delete it" | Info |
| Clear all confirmation | Confirmation dialog | - |
| Cleared all | "Cleared N polygon(s) from all slides" | Success |
| No polygons | "No polygons to clear" | Info |

## Limitations

### Current Limitations

1. **No persistence** - Polygons lost on page refresh
2. **No editing** - Cannot modify saved polygons (points or labels)
3. **No export** - Cannot save polygon data to file
4. **No import** - Cannot load pre-existing annotations
5. **Simple deletion** - Only click-to-delete, no multi-select

### Design Decisions

- **Session-only storage** as requested by user
- **Simple workflow** - Draw → Label → Save → Delete/Clear
- **Persistent display** - Polygons remain visible when toggling modes
- **Minimal UI** - Three buttons with clear purposes
- **Automatic cleanup** - Polygons filtered by slide
- **Visual feedback** - Color coding for different modes

## Future Enhancement Ideas

If persistence or advanced features are needed later:

- Export polygons as JSON/GeoJSON
- Import polygons from file
- Save to server (optional backend API)
- Edit polygon points and labels
- Edit mode (drag vertices to modify)
- Multi-select deletion
- Polygon categories with different colors
- Measurement tools (area, perimeter)
- Custom polygon properties (color, opacity, stroke)
- Undo/redo functionality
- Polygon search/filter by label

## Code Files

### Modified Files

1. **index.html** - Added drawing control buttons
2. **viewer.js** - Added polygon drawing logic
3. **styles.css** - Added button styles

### Key Functions

```javascript
// Toggle drawing mode on/off
toggleDrawingMode()

// Toggle delete mode on/off
toggleDeleteMode()

// Handle click during drawing
handlePolygonClick(event)

// Handle click during delete mode
handleDeletePolygonClick(event)

// Finish and save polygon (with label prompt)
finishPolygon(event)

// Update SVG overlay
updatePolygonOverlay()

// Clear all polygons (with confirmation)
clearAllPolygons()

// Initialize SVG overlay
initializePolygonOverlay()

// Create SVG element for polygon
createPolygonSvgElement(points, index, isCurrent, label)

// Calculate polygon centroid for label
calculateCentroid(points)

// Check if point is inside polygon
isPointInPolygon(point, polygonPoints)
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
- **Check prompt** - Label prompt may be blocking view

### Polygons disappear when clicking 📐

- **Expected behavior** - Polygons now persist when toggling modes
- **If they vanish** - Only incomplete polygon is discarded
- **Check current slide** - Polygons are per-slide

### Can't delete a polygon

- **Enable delete mode** - Click 🗑 button (should turn blue)
- **Click polygon area** - Must click inside the polygon
- **Confirm deletion** - Accept the confirmation prompt
- **Polygons turn red** - Visual indicator of delete mode

### Label not showing

- **Label was empty** - Labels only show if text was entered
- **Zoom level** - Label might be small, try zooming in
- **Check polygon** - Label appears at center of polygon

### Cursor not changing

- Drawing/delete mode may not be active
- Try toggling the button again
- Check if another mode is active

### Polygons disappear on slide switch

- **Correct behavior** - Polygons are per-slide
- Switch back to original slide to see them
- Each slide has its own set of polygons

### Can't click slide in drawing/delete mode

- Exit mode by clicking button or pressing ESC
- Drawing/delete mode captures all clicks
- Normal navigation disabled during these modes

### Confirmation prompt issues

- **Browser blocking prompts** - Check browser settings
- **Prompt behind window** - Look for browser dialog
- **Cancel prompt** - Polygon won't be saved/deleted

## Examples

### Simple Labeled Rectangle

1. Click 📐 to start drawing mode
2. Click top-left corner
3. Click top-right corner
4. Click bottom-right corner
5. Click bottom-left corner
6. Double-click to finish
7. Enter label: "Tumor"
8. Polygon saved with label displayed

### Complex Multi-Point Polygon

1. Click 📐 to start
2. Click points around region of interest
3. Add as many points as needed (10, 20, 50+)
4. Double-click anywhere to complete
5. Enter label or leave empty (optional)
6. Continue drawing more polygons

### Quick Annotation Workflow

1. Load slide
2. Click 📐 → Draw multiple regions → Label each
3. Click 📐 to exit (polygons remain visible)
4. View your annotations
5. Click 🗑 to delete specific polygons
6. Click 🗑️ to clear all when done

### Delete Individual Polygon

1. Click 🗑 to enter delete mode
2. Polygons turn red
3. Click unwanted polygon
4. Confirm deletion
5. Press ESC to exit delete mode

### Multi-Slide Workflow

1. Load slide A → Draw polygons → Label them
2. Switch to slide B → Draw different polygons
3. Switch back to slide A → Original polygons still there
4. Each slide maintains its own set of polygons
