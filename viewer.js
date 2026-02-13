/**
 * WSI Viewer - Frontend Logic
 * Handles slide management and OpenSeadragon viewer
 */

// Global state
let viewer = null;
let currentSlide = null;
let slides = [];
let densityOverlayImage = null;
let densityOverlayEnabled = false;
let densityGridData = null;
let densityMetadata = null;

// Polygon drawing state
let drawingMode = false;
let deleteMode = false;
let labelMode = false;
let currentPolygon = [];
let polygons = [];
let polygonOverlays = [];
let polygonSvgOverlay = null;

// Free-floating labels (independent of polygons)
let labels = [];
let labelSvgOverlay = null;


// API base URL - derived from the session token in the URL path
// e.g., if URL is /a8f3k2x9/, API_BASE becomes /a8f3k2x9
const SESSION_TOKEN = window.location.pathname.split('/')[1] || '';
const API_BASE = SESSION_TOKEN ? `/${SESSION_TOKEN}` : '';

// Session keepalive heartbeat (every 5 minutes)
if (SESSION_TOKEN) {
    setInterval(() => {
        fetch(`/api/sessions/${SESSION_TOKEN}/heartbeat`, { method: 'POST' })
            .catch(() => console.warn('Heartbeat failed'));
    }, 5 * 60 * 1000);
}

// Formats that can be viewed directly without conversion
const DIRECTLY_VIEWABLE_FORMATS = ['tif', 'tiff', 'svs', 'vms', 'vmu', 'ndpi', 'scn', 'mrxs', 'svslide', 'bif'];

// ========================================
// Initialization
// ========================================

document.addEventListener('DOMContentLoaded', () => {
    // Verify GeoTIFFTileSource library is loaded
    if (typeof OpenSeadragon !== 'undefined' && typeof OpenSeadragon.GeoTIFFTileSource === 'undefined') {
        console.warn('GeoTIFFTileSource plugin not found. Direct viewing of GeoTIFF files may not work.');
        console.warn('Make sure geotiff-tilesource library is loaded before viewer.js');
    }

    initializeEventListeners();
    loadSlides();
});

// ========================================
// Event Listeners
// ========================================

function initializeEventListeners() {
    // Viewer controls
    const zoomInBtn = document.getElementById('zoom-in-btn');
    if (zoomInBtn) zoomInBtn.addEventListener('click', () => {
        if (viewer) viewer.viewport.zoomBy(1.5);
    });

    const zoomOutBtn = document.getElementById('zoom-out-btn');
    if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => {
        if (viewer) viewer.viewport.zoomBy(0.67);
    });

    const homeBtn = document.getElementById('home-btn');
    if (homeBtn) homeBtn.addEventListener('click', () => {
        if (viewer) viewer.viewport.goHome();
    });

    const rotateBtn = document.getElementById('rotate-btn');
    if (rotateBtn) rotateBtn.addEventListener('click', () => {
        if (viewer) {
            const currentRotation = viewer.viewport.getRotation();
            viewer.viewport.setRotation(currentRotation + 90);
        }
    });

    const fullscreenBtn = document.getElementById('fullscreen-btn');
    if (fullscreenBtn) fullscreenBtn.addEventListener('click', () => {
        if (viewer) viewer.setFullScreen(!viewer.isFullPage());
    });

    // Snapshot button
    const snapshotBtn = document.getElementById('snapshot-btn');
    if (snapshotBtn) snapshotBtn.addEventListener('click', takeSnapshot);

    // Polygon drawing controls
    const drawPolygonBtn = document.getElementById('draw-polygon-btn');
    if (drawPolygonBtn) drawPolygonBtn.addEventListener('click', toggleDrawingMode);

    const labelPolygonBtn = document.getElementById('label-polygon-btn');
    if (labelPolygonBtn) labelPolygonBtn.addEventListener('click', toggleLabelMode);

    const deletePolygonBtn = document.getElementById('delete-polygon-btn');
    if (deletePolygonBtn) deletePolygonBtn.addEventListener('click', toggleDeleteMode);

    const clearPolygonsBtn = document.getElementById('clear-polygons-btn');
    if (clearPolygonsBtn) clearPolygonsBtn.addEventListener('click', clearAllPolygons);
}

// ========================================
// Slide Management
// ========================================

async function loadSlides() {
    try {
        const response = await fetch(`${API_BASE}/api/slides`);
        if (!response.ok) throw new Error('Failed to load slides');

        const data = await response.json();
        slides = data.slides;

        // Update slide count
        document.getElementById('slide-count').textContent =
            `${slides.length} slide${slides.length !== 1 ? 's' : ''}`;

        // Render slides list
        renderSlidesList();

    } catch (error) {
        console.error('Load slides error:', error);
        showToast('Failed to load slides', 'error');
    }
}

function renderSlidesList() {
    const slidesList = document.getElementById('slides-list');

    if (slides.length === 0) {
        slidesList.innerHTML = '<p class="empty-state">No slides uploaded yet</p>';
        return;
    }

    slidesList.innerHTML = slides.map(slide => `
        <div class="slide-item ${currentSlide === slide.name ? 'active' : ''}">
            <div class="slide-item-main" onclick="loadSlide('${slide.name}')">
                <div class="slide-name">${slide.name}</div>
                <div class="slide-status">
                    ${slide.viewable ? 'Ready to view' : 'Loading...'}
                </div>
            </div>
            <button class="density-toggle-btn" 
                    id="density-btn-${slide.name}" 
                    onclick="event.stopPropagation(); toggleDensityOverlay('${slide.name}')"
                    style="display: flex;"
                    title="Toggle Tumor Cell Annotation overlay">
                TCA
            </button>
        </div>
    `).join('');
    
    console.log(`Rendered ${slides.length} slides, checking overlay availability...`);
    
    // After rendering, check which slides have overlays
    slides.forEach(slide => {
        setTimeout(() => checkDensityOverlayAvailability(slide.name), 100);
    });
}

async function convertSlide(slideName) {
    try {
        const response = await fetch(`${API_BASE}/api/convert/${slideName}`, {
            method: 'POST'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || errorData.error || 'Conversion failed');
        }

        return await response.json();

    } catch (error) {
        console.error('Conversion error:', error);
        throw error;
    }
}

async function loadSlide(slideName) {
    try {
        currentSlide = slideName;
        
        // Clear any existing overlay pages
        const existingOverlays = document.querySelectorAll('.slide-overlay-container');
        existingOverlays.forEach(el => el.remove());
        
        // Reset density overlay state
        if (densityOverlayImage) {
            viewer.world.removeItem(densityOverlayImage);
            densityOverlayImage = null;
        }
        densityOverlayEnabled = false;
        densityGridData = null;
        window._overlayConfig = null;
        window._overlayGridUrl = null;
        
        // Hide opacity slider
        const opacitySection = document.getElementById('density-opacity-section');
        if (opacitySection) opacitySection.style.display = 'none';

        // Find slide object to get filename
        const slide = slides.find(s => s.name === slideName);
        if (!slide) throw new Error('Slide not found in list');

        // Use GeoTIFFTileSource for all SVS/TIFF files (works for both local and GCS with range requests)
        console.log('Loading with GeoTIFFTileSource (range requests)');
        const rawSlideUrl = `${API_BASE}/api/raw_slides/${slide.filename}`;
        loadInViewer(rawSlideUrl, 'geotiff');

        // Update slides list
        renderSlidesList();
        
        // Load overlay config for current slide
        await loadOverlayConfigForSlide(slideName);
        
        // Update polygon and label overlays for current slide
        if (polygonSvgOverlay) {
            updatePolygonOverlay();
        }
        if (labelSvgOverlay) {
            updateLabelOverlay();
        }

        showToast('Slide loaded', 'success');

    } catch (error) {
        console.error('Load slide error:', error);
        showToast(`Failed to load slide: ${error.message}`, 'error');
    }
}



// ========================================
// Viewer Management
// ========================================

async function loadInViewer(sourceUrl, type) {
    const viewerContainer = document.getElementById('viewer-container');

    // Clear existing content if creating new viewer
    if (viewer) {
        viewer.destroy();
        viewer = null;
    }

    viewerContainer.innerHTML = '';

    let tileSources = sourceUrl;

    // If GeoTIFF, create the specific tile source
    if (type === 'geotiff') {
        try {
            // Ensure URL is absolute
            let absoluteUrl = sourceUrl;
            if (!sourceUrl.startsWith('http')) {
                // Convert relative URL to absolute
                absoluteUrl = new URL(sourceUrl, window.location.origin).href;
            }

            console.log('Attempting to load GeoTIFF from:', absoluteUrl);
            console.log('OpenSeadragon available:', typeof OpenSeadragon !== 'undefined');
            console.log('GeoTIFFTileSource available:', typeof OpenSeadragon.GeoTIFFTileSource !== 'undefined');

            // Verify GeoTIFFTileSource is available
            if (!OpenSeadragon.GeoTIFFTileSource) {
                throw new Error('GeoTIFFTileSource plugin not loaded. Check that geotiff-tilesource library is included.');
            }

            // Test URL accessibility first
            try {
                const testResponse = await fetch(absoluteUrl, {
                    method: 'HEAD'
                });
                console.log('HEAD test status:', testResponse.status);
                console.log('HEAD headers:', Object.fromEntries(testResponse.headers.entries()));
                
                if (!testResponse.ok) {
                    throw new Error(`HEAD request failed with status ${testResponse.status}`);
                }
                
                const acceptRanges = testResponse.headers.get('accept-ranges');
                const contentLength = testResponse.headers.get('content-length');
                console.log('Accept-Ranges:', acceptRanges);
                console.log('Content-Length:', contentLength);
                
                if (!acceptRanges || acceptRanges === 'none') {
                    console.warn('Server does not support range requests!');
                }
                
                if (!contentLength || contentLength === '0') {
                    throw new Error('File size is 0 or unknown');
                }
            } catch (testError) {
                console.error('URL accessibility test FAILED:', testError);
                throw new Error(`Cannot access file: ${testError.message}`);
            }

            // Use getAllTileSources static method as per documentation
            // Supports both local files (File object) and remote URLs (string)
            const options = {
                logLatency: true,  // Enable logging for debugging
                // Enable range requests for better performance
                useRangeRequests: true
            };

            // Add CORS-related options for HTTP URLs
            if (absoluteUrl.startsWith('http')) {
                options.headers = {
                    'Accept': 'image/tiff,image/*,*/*'
                };
            }

            console.log('Calling GeoTIFFTileSource.getAllTileSources with options:', options);
            tileSources = await OpenSeadragon.GeoTIFFTileSource.getAllTileSources(absoluteUrl, options);

            console.log('GeoTIFFTileSource created successfully, tile sources:', tileSources);

            // Validate tile sources
            if (!tileSources || (Array.isArray(tileSources) && tileSources.length === 0)) {
                throw new Error('GeoTIFFTileSource returned empty or invalid tile sources');
            }
            
            // Handle multiple pages (SVS files often have main slide + label + macro)
            if (Array.isArray(tileSources) && tileSources.length > 1) {
                console.log(`Found ${tileSources.length} pages in the slide`);
                
                // Sort by size (largest first)
                const sortedSources = tileSources.map((ts, idx) => ({
                    source: ts,
                    index: idx,
                    width: ts.width || 0,
                    height: ts.height || 0,
                    area: (ts.width || 0) * (ts.height || 0)
                })).sort((a, b) => b.area - a.area);
                
                console.log('Sorted pages by size:', sortedSources.map(s => ({
                    index: s.index,
                    width: s.width,
                    height: s.height,
                    area: s.area
                })));
                
                // Use the largest as main tile source
                tileSources = sortedSources[0].source;
                
                // Store smaller images for overlay display
                window._additionalPages = sortedSources.slice(1).map(s => s.source);
                console.log(`Main image: ${sortedSources[0].width}x${sortedSources[0].height}`);
                console.log(`Additional pages: ${window._additionalPages.length}`);
            } else {
                window._additionalPages = null;
            }
        } catch (e) {
            console.error('Failed to create GeoTIFFTileSource:', e);
            console.error('Error name:', e.name);
            console.error('Error message:', e.message);
            console.error('Error stack:', e.stack);

            showToast(`Failed to load slide: ${e.message}`, 'error');
            showViewerPlaceholder();
            return;
        }
    }

    // Create OpenSeadragon viewer
    try {
        viewer = OpenSeadragon({
            id: 'viewer-container',
            prefixUrl: 'https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/images/',
            tileSources: tileSources,
            showNavigationControl: false,
            showNavigator: true,
            navigatorPosition: 'BOTTOM_LEFT',
            animationTime: 0.5,
            blendTime: 0.1,
            constrainDuringPan: true,
            maxZoomPixelRatio: 2,
            minZoomLevel: 0.8,
            visibilityRatio: 1,
            zoomPerScroll: 2,
            timeout: 120000,
            crossOriginPolicy: 'Anonymous',
            ajaxWithCredentials: false  // Set to false for CORS with signed URLs
        });

        // Add event handlers
        viewer.addHandler('open', () => {
            console.log('Viewer opened successfully');

            // Add additional pages (label, macro) as overlays
            if (window._additionalPages && window._additionalPages.length > 0) {
                console.log('Adding additional pages as overlays...');
                displayAdditionalPages(window._additionalPages);
            }

            // Try to load density overlay for current slide if config available
            if (currentSlide && window._overlayConfig) {
                loadDensityOverlay(window._overlayConfig);
            }
        });

        viewer.addHandler('open-failed', (event) => {
            console.error('Viewer open failed:', event);
            console.error('Event details:', JSON.stringify(event, null, 2));

            // Extract error message if available
            let errorMessage = 'Failed to open slide in viewer';
            if (event && event.message) {
                errorMessage = event.message;
            } else if (event && event.userData && event.userData.error) {
                errorMessage = event.userData.error;
            }

            console.log('Viewer open failed:', errorMessage);
            showToast(`Failed to open slide: ${errorMessage}`, 'error');
            showViewerPlaceholder();
        });

    } catch (error) {
        console.error('Error creating viewer:', error);
        showToast(`Error creating viewer: ${error.message}`, 'error');
        showViewerPlaceholder();
    }
}

function showViewerPlaceholder() {
    const viewerContainer = document.getElementById('viewer-container');
    viewerContainer.innerHTML = `
        <div class="viewer-placeholder">
            <div class="placeholder-content">
                <div class="placeholder-icon">🔬</div>
                <h2 class="placeholder-title">No Slide Loaded</h2>
                <p class="placeholder-text">Select a slide from the sidebar to view</p>
            </div>
        </div>
    `;
}



// ========================================
// Additional Pages (Label, Macro) Display
// ========================================

function displayAdditionalPages(pages) {
    // Remove any existing overlays
    const existingOverlays = document.querySelectorAll('.slide-overlay-container');
    existingOverlays.forEach(el => el.remove());
    
    // Display up to 2 additional pages (label and macro)
    pages.slice(0, 2).forEach((page, idx) => {
        const width = page.width || 1000;
        const height = page.height || 1000;
        const aspectRatio = width / height;
        
        // Determine dimensions maintaining aspect ratio
        let overlayWidth = 200;
        let overlayHeight = Math.round(overlayWidth / aspectRatio);
        
        // Limit height
        if (overlayHeight > 150) {
            overlayHeight = 150;
            overlayWidth = Math.round(overlayHeight * aspectRatio);
        }
        
        const overlayDiv = document.createElement('div');
        overlayDiv.className = 'slide-overlay-container';
        overlayDiv.id = `slide-overlay-${idx}`;
        overlayDiv.style.cssText = `
            top: ${10 + (idx * (overlayHeight + 20))}px;
            left: 10px;
            width: ${overlayWidth}px;
            height: ${overlayHeight}px;
        `;
        
        const label = document.createElement('div');
        label.className = 'slide-overlay-label';
        label.textContent = idx === 0 ? 'Label' : 'Macro';
        
        const closeBtn = document.createElement('button');
        closeBtn.className = 'slide-overlay-close';
        closeBtn.innerHTML = '×';
        closeBtn.title = 'Close';
        closeBtn.onclick = () => overlayDiv.remove();
        
        const viewerDiv = document.createElement('div');
        viewerDiv.id = `overlay-viewer-${idx}`;
        viewerDiv.style.cssText = `
            width: 100%;
            height: 100%;
        `;
        
        overlayDiv.appendChild(label);
        overlayDiv.appendChild(closeBtn);
        overlayDiv.appendChild(viewerDiv);
        document.getElementById('viewer-container').appendChild(overlayDiv);
        
        // Create mini viewer for this page
        try {
            const miniViewer = OpenSeadragon({
                id: `overlay-viewer-${idx}`,
                tileSources: page,
                showNavigationControl: false,
                showNavigator: false,
                animationTime: 0.3,
                blendTime: 0.1,
                constrainDuringPan: true,
                visibilityRatio: 1,
                minZoomLevel: 0.5,
                maxZoomLevel: 5,
                zoomPerClick: 1.5,
                zoomPerScroll: 1.3,
                crossOriginPolicy: 'Anonymous',
                ajaxWithCredentials: false
            });
            
            miniViewer.addHandler('open', () => {
                console.log(`Overlay viewer ${idx} (${label.textContent}) opened: ${width}x${height}`);
            });
            
        } catch (e) {
            console.error(`Failed to create overlay viewer ${idx}:`, e);
            overlayDiv.remove();
        }
    });
}


// ========================================
// Check Density Overlay Availability
// ========================================

async function checkDensityOverlayAvailability(slideName) {
    console.log(`Checking overlay availability for: ${slideName}`);
    
    try {
        const url = `${API_BASE}/api/overlay-config/${slideName}`;
        console.log(`Fetching: ${url}`);
        
        const configResponse = await fetch(url);
        console.log(`Response status: ${configResponse.status}`);
        
        const config = configResponse.ok ? await configResponse.json() : null;
        console.log(`Config for ${slideName}:`, config);
        
        const densityBtn = document.getElementById(`density-btn-${slideName}`);
        if (!densityBtn) {
            console.warn(`Button not found for ${slideName}`);
            return;
        }
        
        if (config && config.available) {
            densityBtn.style.display = 'flex';
            densityBtn.disabled = false;
            console.log(`✅ TCA overlay available for ${slideName} - button shown`);
        } else {
            densityBtn.style.display = 'none';
            console.log(`❌ No overlay for ${slideName} - button hidden`);
        }
    } catch (error) {
        console.error(`Error checking overlay for ${slideName}:`, error);
        const densityBtn = document.getElementById(`density-btn-${slideName}`);
        if (densityBtn) densityBtn.style.display = 'none';
    }
}

async function loadOverlayConfigForSlide(slideName) {
    try {
        const configResponse = await fetch(`${API_BASE}/api/overlay-config/${slideName}`);
        if (!configResponse.ok) {
            console.log('No overlay config available for current slide');
            window._overlayConfig = null;
            return;
        }

        const config = await configResponse.json();
        if (config.available) {
            window._overlayConfig = config;
            console.log('Overlay config loaded for current slide');
            
            // Show the button for this slide
            const densityBtn = document.getElementById(`density-btn-${slideName}`);
            if (densityBtn) {
                densityBtn.style.display = 'flex';
            }
        } else {
            window._overlayConfig = null;
        }
    } catch (error) {
        console.log('Could not load overlay config:', error.message);
        window._overlayConfig = null;
    }
}

// ========================================
// Toast Notifications
// ========================================

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');

    toast.textContent = message;
    toast.className = `toast ${type}`;

    // Show toast
    setTimeout(() => toast.classList.add('show'), 10);

    // Hide after 3 seconds
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// ========================================
// Density Overlay Management
// ========================================

async function loadDensityOverlay(config) {
    if (!viewer || !config || !config.available) return;

    try {
        // Store the grid URL for later use in toggleDensityOverlay
        window._overlayGridUrl = config.grid;

        // Fetch metadata from the per-slide URL
        const metadataResponse = await fetch(config.metadata);
        if (!metadataResponse.ok) {
            console.log('Could not load density overlay metadata');
            return;
        }

        const metadata = await metadataResponse.json();
        console.log('Density overlay metadata loaded:', metadata);

        // Store metadata for click handling
        densityMetadata = metadata;

        // Calculate the overlay dimensions
        const gridCoverageX = metadata.grid_dimensions[0] * metadata.grid_size;
        const gridCoverageY = metadata.grid_dimensions[1] * metadata.grid_size;

        // WSI dimensions from metadata
        const wsiWidth = metadata.wsi_dimensions[0];
        const wsiHeight = metadata.wsi_dimensions[1];

        // Calculate the overlay width/height in normalized coordinates
        const overlayWidth = gridCoverageX / wsiWidth;
        const overlayHeight = (gridCoverageY / wsiHeight) * (wsiHeight / wsiWidth);

        console.log(`Overlay scaling: ${overlayWidth.toFixed(4)} x ${overlayHeight.toFixed(4)}`);
        console.log(`Grid coverage: ${gridCoverageX}x${gridCoverageY}, WSI: ${wsiWidth}x${wsiHeight}`);

        // Use the per-slide density image URL
        const densityMapUrl = config.density_image;

        // Add the density overlay as a simple image with correct scaling
        const addItemHandler = (event) => {
            const item = event.item;
            if (item.source && item.source.url === densityMapUrl) {
                densityOverlayImage = item;
                densityOverlayImage.setOpacity(0); // Hide initially
                viewer.world.removeHandler('add-item', addItemHandler);
                console.log('Density overlay captured from world event');
            }
        };
        viewer.world.addHandler('add-item', addItemHandler);

        const result = viewer.addSimpleImage({
            url: densityMapUrl,
            opacity: 1,
            x: 0,
            y: 0,
            width: overlayWidth,
            index: 1,
            preload: true
        });

        // Fallback: if it returns the object immediately
        if (result && !densityOverlayImage) {
            densityOverlayImage = result;
            densityOverlayImage.setOpacity(0);
        }

        console.log('Density overlay add request sent');

    } catch (error) {
        console.log('Could not load density overlay:', error.message);
    }
}

async function toggleDensityOverlay(slideName) {
    if (!viewer) return;
    
    // If no slideName provided, use current slide
    if (!slideName) slideName = currentSlide;
    if (!slideName) return;

    // Load overlay if not loaded yet
    if (!densityOverlayImage && window._overlayConfig) {
        await loadDensityOverlay(window._overlayConfig);
    }

    // Fallback: If densityOverlayImage is null, try to find it in the world
    if (!densityOverlayImage) {
        const count = viewer.world.getItemCount();
        for (let i = 0; i < count; i++) {
            const item = viewer.world.getItemAt(i);
            if (item.source && item.source.url && item.source.url.includes('_density.png')) {
                densityOverlayImage = item;
                console.log('Density overlay found in world fallback');
                break;
            }
        }
    }

    if (!densityOverlayImage) {
        // No overlay available - silent, no need to notify user
        return;
    }

    densityOverlayEnabled = !densityOverlayEnabled;
    const btn = document.getElementById(`density-btn-${slideName}`);
    const opacitySection = document.getElementById('density-opacity-section');
    const opacitySlider = document.getElementById('density-opacity');

    if (densityOverlayEnabled) {
        // Show the overlay with current slider value
        const opacity = opacitySlider ? parseInt(opacitySlider.value) / 100 : 0.6;
        densityOverlayImage.setOpacity(opacity);
        
        if (btn) {
            btn.classList.add('active');
            btn.title = 'Hide Tumor Cell Annotation overlay';
        }
        
        if (opacitySection) opacitySection.style.display = 'block';

        // Load grid data for interactive clicks if not already loaded
        if (!densityGridData) {
            try {
                const gridUrl = window._overlayGridUrl;
                if (gridUrl) {
                    const response = await fetch(gridUrl);
                    if (response.ok) {
                        densityGridData = await response.json();
                        console.log('Density grid data loaded for interactive clicks');

                        // Add click handler for density values
                        if (!viewer._densityClickHandler) {
                            viewer._densityClickHandler = true;
                            viewer.addHandler('canvas-click', handleDensityClick);
                        }
                    }
                } else {
                    console.log('No grid URL available');
                }
            } catch (error) {
                console.log('Could not load density grid data:', error);
            }
        }

        showToast('Overlay enabled', 'success');
    } else {
        // Hide the overlay
        densityOverlayImage.setOpacity(0);
        
        if (btn) {
            btn.classList.remove('active');
            btn.title = 'Show Tumor Cell Annotation overlay';
        }
        
        if (opacitySection) opacitySection.style.display = 'none';
        showToast('Overlay disabled', 'info');
    }
}

function updateDensityOpacity(value) {
    // Update opacity value display
    const opacityValueSpan = document.getElementById('density-opacity-value');
    if (opacityValueSpan) {
        opacityValueSpan.textContent = value;
    }

    // Update overlay opacity if visible
    if (densityOverlayImage && densityOverlayEnabled) {
        const opacity = parseInt(value) / 100;
        densityOverlayImage.setOpacity(opacity);
    }
}

function handleDensityClick(event) {
    if (!densityOverlayEnabled || !densityGridData) return;

    const viewportPoint = viewer.viewport.pointFromPixel(event.position);
    const imagePoint = viewer.viewport.viewportToImageCoordinates(viewportPoint);

    const col = Math.floor(imagePoint.x / densityGridData.grid_size);
    const row = Math.floor(imagePoint.y / densityGridData.grid_size);

    if (row >= 0 && row < densityGridData.grid_dimensions[1] &&
        col >= 0 && col < densityGridData.grid_dimensions[0]) {
        const count = densityGridData.density[row][col];
        showToast(`Cancer cells in this region: ${Math.round(count)}`, 'info');
    }
}

// ========================================
// Utility Functions
// ========================================

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// ========================================
// Polygon Drawing Functions
// ========================================

function toggleDrawingMode() {
    if (!viewer) {
        showToast('Please load a slide first', 'error');
        return;
    }

    // Can't be in multiple modes at once
    if (deleteMode) toggleDeleteMode();
    if (labelMode) toggleLabelMode();

    drawingMode = !drawingMode;
    const btn = document.getElementById('draw-polygon-btn');

    if (drawingMode) {
        // Entering drawing mode
        btn.classList.add('active');
        btn.title = 'Click to finish drawing';
        showToast('Drawing mode: Click to add points', 'info');
        
        // Initialize SVG overlay if not exists
        if (!polygonSvgOverlay) {
            initializePolygonOverlay();
        }
        
        // Start new polygon
        currentPolygon = [];
        
        // Add click handler
        viewer.addHandler('canvas-click', handlePolygonClick);
        viewer.addHandler('canvas-double-click', finishPolygon);
        
        // Change cursor
        document.getElementById('viewer-container').style.cursor = 'crosshair';
    } else {
        // Exiting drawing mode
        btn.classList.remove('active');
        btn.title = 'Draw Polygon';
        
        // Remove handlers
        viewer.removeHandler('canvas-click', handlePolygonClick);
        viewer.removeHandler('canvas-double-click', finishPolygon);
        
        // Reset cursor
        document.getElementById('viewer-container').style.cursor = 'default';
        
        // If we have a polygon with 3+ points, save it without label
        if (currentPolygon.length >= 3) {
            const polygon = {
                id: Date.now(),
                points: [...currentPolygon],
                timestamp: new Date().toISOString(),
                slide: currentSlide,
                label: ''
            };

            polygons.push(polygon);
            showToast('Polygon saved', 'success');
            currentPolygon = [];
        } else if (currentPolygon.length > 0) {
            showToast('Incomplete polygon discarded', 'info');
            currentPolygon = [];
        } else {
            showToast('Drawing mode disabled', 'info');
        }
        
        updatePolygonOverlay();
    }
}

function initializePolygonOverlay() {
    // Create SVG overlay element
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("id", "polygon-overlay");
    svg.style.position = "absolute";
    svg.style.top = "0";
    svg.style.left = "0";
    svg.style.width = "100%";
    svg.style.height = "100%";
    svg.style.pointerEvents = "none"; // SVG doesn't capture clicks
    svg.style.zIndex = "1000";

    // Create group for polygons
    const g = document.createElementNS(svgNS, "g");
    g.setAttribute("id", "polygons-group");
    svg.appendChild(g);

    // Add to viewer
    const viewerElement = document.getElementById('viewer-container');
    viewerElement.appendChild(svg);
    
    polygonSvgOverlay = svg;

    // Update overlay on viewport change
    viewer.addHandler('animation', updatePolygonOverlay);
    viewer.addHandler('resize', updatePolygonOverlay);
}

function handlePolygonClick(event) {
    if (!drawingMode) return;

    // Prevent OpenSeadragon from handling this click
    event.preventDefaultAction = true;

    // Get viewport coordinates
    const viewportPoint = viewer.viewport.pointFromPixel(event.position);
    
    // Add point to current polygon
    currentPolygon.push({
        x: viewportPoint.x,
        y: viewportPoint.y
    });

    console.log(`Added point ${currentPolygon.length}:`, viewportPoint);
    
    // Update visual feedback
    updatePolygonOverlay();
}

function finishPolygon(event) {
    if (!drawingMode || currentPolygon.length < 3) {
        return;
    }

    // Prevent default
    event.preventDefaultAction = true;

    // Save polygon without label
    const polygon = {
        id: Date.now(),
        points: [...currentPolygon],
        timestamp: new Date().toISOString(),
        slide: currentSlide,
        label: ''
    };

    polygons.push(polygon);
    
    // Reset current polygon
    currentPolygon = [];
    
    // Update display
    updatePolygonOverlay();
    
    showToast('Polygon saved', 'success');

    // Stay in drawing mode so user can draw more polygons
}

function updatePolygonOverlay() {
    if (!polygonSvgOverlay) return;

    const g = polygonSvgOverlay.querySelector('#polygons-group');
    if (!g) return;

    // Clear existing polygons
    g.innerHTML = '';

    const svgNS = "http://www.w3.org/2000/svg";

    // Draw saved polygons for current slide
    const slidePolygons = polygons.filter(p => p.slide === currentSlide);
    slidePolygons.forEach((polygon, index) => {
        const polygonElement = createPolygonSvgElement(polygon.points, index, false, polygon.label);
        if (polygonElement) g.appendChild(polygonElement);
    });

    // Draw current polygon being drawn
    if (currentPolygon.length > 0) {
        const currentPolyElement = createPolygonSvgElement(currentPolygon, -1, true);
        if (currentPolyElement) g.appendChild(currentPolyElement);
    }
}

function createPolygonSvgElement(points, index, isCurrent = false, label = '') {
    if (points.length === 0) return null;

    const svgNS = "http://www.w3.org/2000/svg";
    const g = document.createElementNS(svgNS, "g");

    // Convert viewport coordinates to pixel coordinates
    const pixelPoints = points.map(p => {
        const pixel = viewer.viewport.pixelFromPoint(new OpenSeadragon.Point(p.x, p.y));
        return { x: pixel.x, y: pixel.y };
    });

    // Create polygon path
    if (pixelPoints.length >= 2) {
        const path = document.createElementNS(svgNS, "path");
        
        let d = `M ${pixelPoints[0].x} ${pixelPoints[0].y}`;
        for (let i = 1; i < pixelPoints.length; i++) {
            d += ` L ${pixelPoints[i].x} ${pixelPoints[i].y}`;
        }
        
        // Close polygon if not current
        if (!isCurrent && pixelPoints.length >= 3) {
            d += ' Z';
        }
        
        path.setAttribute('d', d);
        
        // Different colors based on mode
        let fill, stroke, strokeDash;
        if (isCurrent) {
            fill = 'rgba(255, 255, 0, 0.2)';
            stroke = '#ffff00';
            strokeDash = '5,5';
        } else if (deleteMode) {
            fill = 'rgba(255, 0, 0, 0.3)'; // Red tint in delete mode
            stroke = '#ff0000';
            strokeDash = 'none';
        } else {
            fill = 'rgba(0, 150, 255, 0.2)';
            stroke = '#0096ff';
            strokeDash = 'none';
        }
        
        path.setAttribute('fill', fill);
        path.setAttribute('stroke', stroke);
        path.setAttribute('stroke-width', '2');
        path.setAttribute('stroke-dasharray', strokeDash);
        
        g.appendChild(path);
    }

    // Draw points
    pixelPoints.forEach((point, i) => {
        const circle = document.createElementNS(svgNS, "circle");
        circle.setAttribute('cx', point.x);
        circle.setAttribute('cy', point.y);
        circle.setAttribute('r', '4');
        
        let pointColor;
        if (isCurrent) {
            pointColor = '#ffff00';
        } else if (deleteMode) {
            pointColor = '#ff0000';
        } else {
            pointColor = '#0096ff';
        }
        
        circle.setAttribute('fill', pointColor);
        circle.setAttribute('stroke', 'white');
        circle.setAttribute('stroke-width', '1');
        g.appendChild(circle);
    });

    // Add label if provided (for saved polygons)
    if (!isCurrent && label) {
        // Calculate centroid for label placement
        const centroid = calculateCentroid(pixelPoints);
        
        // Create background rectangle for label
        const labelBg = document.createElementNS(svgNS, "rect");
        const labelText = document.createElementNS(svgNS, "text");
        
        // Set text first to measure it
        labelText.setAttribute('x', centroid.x);
        labelText.setAttribute('y', centroid.y);
        labelText.setAttribute('text-anchor', 'middle');
        labelText.setAttribute('dominant-baseline', 'middle');
        labelText.setAttribute('fill', 'white');
        labelText.setAttribute('font-size', '14px');
        labelText.setAttribute('font-weight', 'bold');
        labelText.textContent = label;
        
        // Approximate text width (more accurate would require rendering)
        const textWidth = label.length * 8.5;
        const textHeight = 18;
        
        labelBg.setAttribute('x', centroid.x - textWidth / 2 - 4);
        labelBg.setAttribute('y', centroid.y - textHeight / 2 - 2);
        labelBg.setAttribute('width', textWidth + 8);
        labelBg.setAttribute('height', textHeight + 4);
        
        let labelBgColor;
        if (deleteMode) {
            labelBgColor = 'rgba(255, 0, 0, 0.9)'; // Red in delete mode
        } else {
            labelBgColor = 'rgba(0, 96, 255, 0.9)'; // Blue in normal mode
        }
        
        labelBg.setAttribute('fill', labelBgColor);
        labelBg.setAttribute('rx', '4');
        labelBg.setAttribute('ry', '4');
        labelBg.setAttribute('stroke', 'white');
        labelBg.setAttribute('stroke-width', '2');
        
        g.appendChild(labelBg);
        g.appendChild(labelText);
    }

    return g;
}

function calculateCentroid(points) {
    let sumX = 0, sumY = 0;
    points.forEach(p => {
        sumX += p.x;
        sumY += p.y;
    });
    return {
        x: sumX / points.length,
        y: sumY / points.length
    };
}

function toggleLabelMode() {
    if (!viewer) {
        showToast('Please load a slide first', 'error');
        return;
    }

    // Can't be in multiple modes at once
    if (drawingMode) toggleDrawingMode();
    if (deleteMode) toggleDeleteMode();

    labelMode = !labelMode;
    const btn = document.getElementById('label-polygon-btn');

    if (labelMode) {
        btn.classList.add('active');
        btn.title = 'Exit label mode';
        showToast('Label mode: Click to place label', 'info');
        
        // Initialize label overlay if not exists
        if (!labelSvgOverlay) {
            initializeLabelOverlay();
        }
        
        // Add click handler
        viewer.addHandler('canvas-click', handlePlaceLabelClick);
        
        // Change cursor
        document.getElementById('viewer-container').style.cursor = 'text';
    } else {
        btn.classList.remove('active');
        btn.title = 'Add Labels';
        
        // Remove handler
        viewer.removeHandler('canvas-click', handlePlaceLabelClick);
        
        // Reset cursor
        document.getElementById('viewer-container').style.cursor = 'default';
        
        showToast('Label mode disabled', 'info');
    }
}

function toggleDeleteMode() {
    if (!viewer) {
        showToast('Please load a slide first', 'error');
        return;
    }

    // Can't be in multiple modes at once
    if (drawingMode) toggleDrawingMode();
    if (labelMode) toggleLabelMode();

    deleteMode = !deleteMode;
    const btn = document.getElementById('delete-polygon-btn');

    if (deleteMode) {
        btn.classList.add('active');
        btn.title = 'Exit delete mode';
        showToast('Delete mode: Click item to delete', 'info');
        
        // Add click handler
        viewer.addHandler('canvas-click', handleDeletePolygonClick);
        
        // Change cursor
        document.getElementById('viewer-container').style.cursor = 'pointer';
        
        // Make polygons more visible for deletion
        updatePolygonOverlay();
    } else {
        btn.classList.remove('active');
        btn.title = 'Delete Items';
        
        // Remove handler
        viewer.removeHandler('canvas-click', handleDeletePolygonClick);
        
        // Reset cursor
        document.getElementById('viewer-container').style.cursor = 'default';
        
        updatePolygonOverlay();
        
        showToast('Delete mode disabled', 'info');
    }
}

function handlePlaceLabelClick(event) {
    if (!labelMode) return;

    event.preventDefaultAction = true;

    const viewportPoint = viewer.viewport.pointFromPixel(event.position);
    
    // Use setTimeout to ensure prompt appears
    setTimeout(() => {
        // Prompt for label text
        const labelText = window.prompt('Enter label text:');
        
        if (labelText && labelText.trim()) {
            const text = labelText.trim();
            
            // Create new label at clicked position
            // Position will be calculated dynamically on each render
            const label = {
                id: Date.now(),
                text: text,
                position: { x: viewportPoint.x, y: viewportPoint.y },
                slide: currentSlide,
                timestamp: new Date().toISOString()
            };
            
            labels.push(label);
            
            updateLabelOverlay();
            showToast('Label added', 'success');
        }
    }, 100);
}

function handleDeletePolygonClick(event) {
    if (!deleteMode) return;

    event.preventDefaultAction = true;

    const viewportPoint = viewer.viewport.pointFromPixel(event.position);
    const pixel = viewer.viewport.pixelFromPoint(viewportPoint);
    
    // Check if clicked on a label first (labels are on top)
    const slideLabels = labels.filter(l => l.slide === currentSlide);
    
    // Recalculate label positions at current zoom level
    const labelPositions = calculateAllLabelPositions(slideLabels);
    
    for (let i = slideLabels.length - 1; i >= 0; i--) {
        const label = slideLabels[i];
        const anchorPixel = viewer.viewport.pixelFromPoint(new OpenSeadragon.Point(label.position.x, label.position.y));
        
        // Use dynamically calculated offset
        const offset = labelPositions[i];
        const labelPixel = {
            x: anchorPixel.x + offset.x,
            y: anchorPixel.y + offset.y
        };
        
        // Check if click is near anchor point (small circle)
        const distToAnchor = Math.sqrt(
            Math.pow(pixel.x - anchorPixel.x, 2) + 
            Math.pow(pixel.y - anchorPixel.y, 2)
        );
        
        // Check if click is within label box
        const textWidth = label.text.length * 9.5;
        const textHeight = 20;
        const padding = 8;
        
        const inLabelBox = (
            pixel.x >= labelPixel.x - textWidth / 2 - padding &&
            pixel.x <= labelPixel.x + textWidth / 2 + padding &&
            pixel.y >= labelPixel.y - textHeight / 2 - padding / 2 &&
            pixel.y <= labelPixel.y + textHeight / 2 + padding / 2
        );
        
        if (distToAnchor <= 10 || inLabelBox) {
            const confirmed = confirm(`Delete label "${label.text}"?`);
            
            if (confirmed) {
                const globalIndex = labels.indexOf(label);
                if (globalIndex > -1) {
                    labels.splice(globalIndex, 1);
                }
                
                updateLabelOverlay();
                showToast('Label deleted', 'success');
            }
            return;
        }
    }
    
    // Check if clicked on a polygon
    const slidePolygons = polygons.filter(p => p.slide === currentSlide);
    
    for (let i = slidePolygons.length - 1; i >= 0; i--) {
        const polygon = slidePolygons[i];
        if (isPointInPolygon(viewportPoint, polygon.points)) {
            // Found the clicked polygon
            const polygonLabel = polygon.label ? ` "${polygon.label}"` : '';
            const confirmed = confirm(`Delete polygon${polygonLabel}?`);
            
            if (confirmed) {
                // Remove from global polygons array
                const globalIndex = polygons.indexOf(polygon);
                if (globalIndex > -1) {
                    polygons.splice(globalIndex, 1);
                }
                
                updatePolygonOverlay();
                showToast('Polygon deleted', 'success');
            }
            return;
        }
    }
    
    // User already in delete mode, no need for redundant message
}

function isPointInPolygon(point, polygonPoints) {
    // Ray casting algorithm
    let inside = false;
    const x = point.x;
    const y = point.y;
    
    for (let i = 0, j = polygonPoints.length - 1; i < polygonPoints.length; j = i++) {
        const xi = polygonPoints[i].x;
        const yi = polygonPoints[i].y;
        const xj = polygonPoints[j].x;
        const yj = polygonPoints[j].y;
        
        const intersect = ((yi > y) !== (yj > y)) &&
                         (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
        if (intersect) inside = !inside;
    }
    
    return inside;
}

function clearAllPolygons() {
    // Clear all polygons and labels for all slides
    const totalCount = polygons.length + labels.length;
    
    if (totalCount === 0) {
        showToast('No annotations to clear', 'info');
        return;
    }

    const confirmed = confirm(`Delete all ${polygons.length} polygon${polygons.length !== 1 ? 's' : ''} and ${labels.length} label${labels.length !== 1 ? 's' : ''}?`);
    if (!confirmed) return;

    polygons = [];
    currentPolygon = [];
    labels = [];
    
    updatePolygonOverlay();
    updateLabelOverlay();
    
    showToast('All annotations cleared', 'success');
}

// ========================================
// Label Functions
// ========================================

function initializeLabelOverlay() {
    // Create SVG overlay element for labels
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("id", "label-overlay");
    svg.style.position = "absolute";
    svg.style.top = "0";
    svg.style.left = "0";
    svg.style.width = "100%";
    svg.style.height = "100%";
    svg.style.pointerEvents = "none";
    svg.style.zIndex = "1001"; // Above polygons
    
    // Create group for labels
    const g = document.createElementNS(svgNS, "g");
    g.setAttribute("id", "labels-group");
    svg.appendChild(g);
    
    // Add to viewer
    const viewerElement = document.getElementById('viewer-container');
    viewerElement.appendChild(svg);
    
    labelSvgOverlay = svg;
    
    // Update overlay on viewport change
    viewer.addHandler('animation', updateLabelOverlay);
    viewer.addHandler('resize', updateLabelOverlay);
}

function updateLabelOverlay() {
    if (!labelSvgOverlay) return;
    
    const g = labelSvgOverlay.querySelector('#labels-group');
    if (!g) return;
    
    // Clear existing labels
    g.innerHTML = '';
    
    const svgNS = "http://www.w3.org/2000/svg";
    
    // Draw labels for current slide with dynamic collision avoidance
    const slideLabels = labels.filter(l => l.slide === currentSlide);
    
    // Recalculate all label positions to avoid overlaps at current zoom
    const labelPositions = calculateAllLabelPositions(slideLabels);
    
    slideLabels.forEach((label, index) => {
        const labelElement = createLabelSvgElement(label, labelPositions[index]);
        if (labelElement) g.appendChild(labelElement);
    });
}

function calculateAllLabelPositions(slideLabels) {
    const positions = [];
    
    for (let i = 0; i < slideLabels.length; i++) {
        const label = slideLabels[i];
        const anchorPixel = viewer.viewport.pixelFromPoint(
            new OpenSeadragon.Point(label.position.x, label.position.y)
        );
        
        // Try different offset positions
        const offsetOptions = [
            { x: 40, y: -40 },   // Top-right (default)
            { x: 60, y: -40 },   // Further right
            { x: 40, y: -60 },   // Higher up
            { x: 60, y: -60 },   // Further right and higher
            { x: -40, y: -40 },  // Top-left
            { x: 40, y: 40 },    // Bottom-right
            { x: -40, y: 40 },   // Bottom-left
            { x: 80, y: -40 },   // Far right
            { x: 40, y: -80 },   // Far up
            { x: 80, y: -80 },   // Far diagonal
            { x: -60, y: -60 },  // Far top-left
            { x: -80, y: -40 },  // Far left
            { x: 100, y: -40 },  // Very far right
            { x: 40, y: -100 },  // Very far up
        ];
        
        let bestOffset = offsetOptions[0];
        
        // Check against all previously positioned labels
        for (const offset of offsetOptions) {
            const newBounds = getLabelBounds(anchorPixel, label.text, offset.x, offset.y);
            let hasOverlap = false;
            
            for (let j = 0; j < i; j++) {
                const existingLabel = slideLabels[j];
                const existingPosition = positions[j];
                const existingAnchorPixel = viewer.viewport.pixelFromPoint(
                    new OpenSeadragon.Point(existingLabel.position.x, existingLabel.position.y)
                );
                const existingBounds = getLabelBounds(
                    existingAnchorPixel,
                    existingLabel.text,
                    existingPosition.x,
                    existingPosition.y
                );
                
                if (boundsOverlap(newBounds, existingBounds)) {
                    hasOverlap = true;
                    break;
                }
            }
            
            if (!hasOverlap) {
                bestOffset = offset;
                break;
            }
        }
        
        positions.push(bestOffset);
    }
    
    return positions;
}

function getLabelBounds(anchorPixel, text, offsetX, offsetY) {
    const textWidth = text.length * 9.5;
    const textHeight = 20;
    const padding = 8;
    
    const labelPixel = {
        x: anchorPixel.x + offsetX,
        y: anchorPixel.y + offsetY
    };
    
    return {
        left: labelPixel.x - textWidth / 2 - padding,
        right: labelPixel.x + textWidth / 2 + padding,
        top: labelPixel.y - textHeight / 2 - padding / 2,
        bottom: labelPixel.y + textHeight / 2 + padding / 2,
        labelPixel: labelPixel
    };
}

function boundsOverlap(bounds1, bounds2) {
    // Add a small margin for spacing
    const margin = 10;
    return !(
        bounds1.right + margin < bounds2.left ||
        bounds1.left - margin > bounds2.right ||
        bounds1.bottom + margin < bounds2.top ||
        bounds1.top - margin > bounds2.bottom
    );
}


function createLabelSvgElement(label, offset) {
    const svgNS = "http://www.w3.org/2000/svg";
    const g = document.createElementNS(svgNS, "g");
    
    // Convert viewport coordinates to pixel coordinates (anchor point)
    const anchorPixel = viewer.viewport.pixelFromPoint(new OpenSeadragon.Point(label.position.x, label.position.y));
    
    // Use provided offset (dynamically calculated) or default
    const useOffset = offset || { x: 40, y: -40 };
    const labelPixel = {
        x: anchorPixel.x + useOffset.x,
        y: anchorPixel.y + useOffset.y
    };
    
    // Approximate text dimensions
    const textWidth = label.text.length * 9.5;
    const textHeight = 20;
    const padding = 8;
    
    // Draw leader line from anchor to label
    const line = document.createElementNS(svgNS, "line");
    line.setAttribute('x1', anchorPixel.x);
    line.setAttribute('y1', anchorPixel.y);
    line.setAttribute('x2', labelPixel.x - textWidth / 2 - padding);
    line.setAttribute('y2', labelPixel.y);
    line.setAttribute('stroke', 'black');
    line.setAttribute('stroke-width', '2');
    g.appendChild(line);
    
    // Draw anchor point (small circle)
    const anchor = document.createElementNS(svgNS, "circle");
    anchor.setAttribute('cx', anchorPixel.x);
    anchor.setAttribute('cy', anchorPixel.y);
    anchor.setAttribute('r', '4');
    anchor.setAttribute('fill', 'black');
    anchor.setAttribute('stroke', 'white');
    anchor.setAttribute('stroke-width', '2');
    g.appendChild(anchor);
    
    // Draw label background
    const bg = document.createElementNS(svgNS, "rect");
    bg.setAttribute('x', labelPixel.x - textWidth / 2 - padding);
    bg.setAttribute('y', labelPixel.y - textHeight / 2 - padding / 2);
    bg.setAttribute('width', textWidth + padding * 2);
    bg.setAttribute('height', textHeight + padding);
    bg.setAttribute('fill', 'white');
    bg.setAttribute('rx', '4');
    bg.setAttribute('ry', '4');
    bg.setAttribute('stroke', 'black');
    bg.setAttribute('stroke-width', '2');
    g.appendChild(bg);
    
    // Draw text
    const text = document.createElementNS(svgNS, "text");
    text.setAttribute('x', labelPixel.x);
    text.setAttribute('y', labelPixel.y);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dominant-baseline', 'middle');
    text.setAttribute('fill', 'black');
    text.setAttribute('font-size', '14px');
    text.setAttribute('font-weight', '600');
    text.textContent = label.text;
    g.appendChild(text);
    
    return g;
}

// ========================================
// Snapshot Functions
// ========================================

async function takeSnapshot() {
    if (!viewer) {
        showToast('No viewer loaded', 'error');
        return;
    }

    try {
        // Capturing snapshot (no need to show toast, it's fast)

        // Get the viewer container
        const viewerContainer = document.getElementById('viewer-container');
        const canvas = viewerContainer.querySelector('canvas');
        
        if (!canvas) {
            showToast('No canvas found', 'error');
            return;
        }

        // Create a new canvas for the snapshot
        const snapshotCanvas = document.createElement('canvas');
        const ctx = snapshotCanvas.getContext('2d');
        
        // Set canvas size to match viewer
        snapshotCanvas.width = canvas.width;
        snapshotCanvas.height = canvas.height;

        // Draw the OpenSeadragon canvas
        ctx.drawImage(canvas, 0, 0);

        // Draw SVG overlays on top
        await drawSvgOverlaysOnCanvas(ctx, snapshotCanvas.width, snapshotCanvas.height);

        // Convert to blob and download
        snapshotCanvas.toBlob((blob) => {
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
            const filename = `${currentSlide || 'slide'}_snapshot_${timestamp}.png`;
            
            link.href = url;
            link.download = filename;
            link.click();
            
            URL.revokeObjectURL(url);
            showToast('Snapshot saved', 'success');
        }, 'image/png');

    } catch (error) {
        console.error('Snapshot error:', error);
        showToast('Snapshot failed', 'error');
    }
}

async function drawSvgOverlaysOnCanvas(ctx, width, height) {
    // Draw density overlay if present (it's rendered as part of OpenSeadragon, so it should already be in the canvas)
    // But we can add additional slide overlays (label/macro images)
    const additionalOverlays = document.querySelectorAll('.slide-overlay-container');
    if (additionalOverlays.length > 0) {
        for (const overlay of additionalOverlays) {
            try {
                const overlayCanvas = overlay.querySelector('canvas');
                if (overlayCanvas && overlay.style.display !== 'none') {
                    // Get overlay position and size
                    const rect = overlay.getBoundingClientRect();
                    const viewerRect = document.getElementById('viewer-container').getBoundingClientRect();
                    
                    // Calculate relative position
                    const x = rect.left - viewerRect.left;
                    const y = rect.top - viewerRect.top;
                    
                    // Draw the overlay canvas
                    ctx.drawImage(overlayCanvas, x, y, rect.width, rect.height);
                }
            } catch (e) {
                console.warn('Failed to draw additional overlay:', e);
            }
        }
    }
    
    // Get all SVG overlays
    const polygonSvg = document.getElementById('polygon-overlay');
    const labelSvg = document.getElementById('label-overlay');
    
    // Draw polygons
    if (polygonSvg) {
        await drawSvgToCanvas(polygonSvg, ctx, width, height);
    }
    
    // Draw labels
    if (labelSvg) {
        await drawSvgToCanvas(labelSvg, ctx, width, height);
    }
}

function drawSvgToCanvas(svgElement, ctx, width, height) {
    return new Promise((resolve, reject) => {
        try {
            // Clone the SVG to avoid modifying the original
            const svgClone = svgElement.cloneNode(true);
            svgClone.setAttribute('width', width);
            svgClone.setAttribute('height', height);
            
            // Serialize SVG to string
            const svgString = new XMLSerializer().serializeToString(svgClone);
            const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
            const svgUrl = URL.createObjectURL(svgBlob);
            
            // Create an image from the SVG
            const img = new Image();
            img.onload = () => {
                ctx.drawImage(img, 0, 0);
                URL.revokeObjectURL(svgUrl);
                resolve();
            };
            img.onerror = () => {
                URL.revokeObjectURL(svgUrl);
                reject(new Error('Failed to load SVG as image'));
            };
            img.src = svgUrl;
        } catch (error) {
            reject(error);
        }
    });
}

// Add keyboard shortcuts for polygon modes
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        if (drawingMode) {
            // Cancel current polygon
            currentPolygon = [];
            updatePolygonOverlay();
            toggleDrawingMode();
            showToast('Polygon drawing cancelled', 'info');
        } else if (labelMode) {
            // Exit label mode
            toggleLabelMode();
        } else if (deleteMode) {
            // Exit delete mode
            toggleDeleteMode();
        }
    }
});
