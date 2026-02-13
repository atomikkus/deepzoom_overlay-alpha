# UI Changes - Simplified Interface

## What Changed

### ✅ Removed
- Slide Information section (dimensions, levels, vendor, etc.)
- Old "Show Cancer Density" button in separate section

### ✅ Added
- Inline "TCA" button next to each slide name
- Compact density opacity slider (only shows when overlay is active)

## New Layout

### Sidebar
```
┌────────────────────────────┐
│ Available Slides           │
├────────────────────────────┤
│                            │
│ ┌────────────────────────┐ │
│ │ Head_neck_pathology    │ │
│ │ 👁 Ready          [TCA]│ │  ← TCA button appears if overlay exists
│ └────────────────────────┘ │
│                            │
│ ┌────────────────────────┐ │
│ │ Another_slide          │ │
│ │ 👁 Ready               │ │  ← No TCA button (no overlay)
│ └────────────────────────┘ │
│                            │
└────────────────────────────┘

When TCA is active:
┌────────────────────────────┐
│ Density Overlay            │
├────────────────────────────┤
│ Opacity: 60%               │
│ [──────●───────]           │
└────────────────────────────┘
```

## TCA Button Behavior

### States

1. **Hidden** (default)
   - Button not visible
   - No overlay available for this slide

2. **Inactive** (visible)
   - Shows "TCA" text
   - Gray background
   - Hover: blue accent
   - Tooltip: "Show Tumor Cell Annotation overlay"

3. **Active** (clicked)
   - Background: accent blue
   - Text: white "TCA"
   - Tooltip: "Hide Tumor Cell Annotation overlay"
   - Opacity slider appears in sidebar

## User Flow

1. **Page loads** → All slides listed
2. **Background check** → TCA button appears for slides with overlays
3. **Click slide name** → Load slide in viewer
4. **Click TCA button** → Toggle overlay on/off
5. **Adjust slider** → Change overlay opacity
6. **Switch slides** → Overlay resets, button state updates

## Technical Details

### Button Rendering
```javascript
// Button is always rendered but hidden by default
<button class="density-toggle-btn" id="density-btn-${slide.name}">
    TCA
</button>

// Shows via display: flex when overlay available
densityBtn.style.display = 'flex';
```

### Async Overlay Check
```javascript
// Called after slide list renders
slides.forEach(slide => {
    checkDensityOverlayAvailability(slide.name);
});
```

### Toggle Function
```javascript
// Accepts slide name parameter
toggleDensityOverlay(slideName)

// Updates button state
btn.classList.add('active');  // or remove('active')
```

## CSS Classes

- `.density-toggle-btn` - Base button style
- `.density-toggle-btn:hover` - Hover state
- `.density-toggle-btn.active` - Active/enabled state
- `.density-toggle-btn:disabled` - Disabled state

## Benefits

1. **Cleaner UI** - No unnecessary info section
2. **Intuitive** - Button right next to slide name
3. **Compact** - TCA = Tumor Cell Annotation (short acronym)
4. **Clear state** - Button styling shows active/inactive
5. **Space efficient** - More room for slides list
