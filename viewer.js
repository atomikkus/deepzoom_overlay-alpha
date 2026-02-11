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

    // Destroy session on tab close (sendBeacon only sends POST)
    window.addEventListener('beforeunload', () => {
        navigator.sendBeacon(`/api/sessions/${SESSION_TOKEN}/delete`, '');
    });
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
        <div class="slide-item ${currentSlide === slide.name ? 'active' : ''}" 
             onclick="loadSlide('${slide.name}')">
            <div class="slide-name">${slide.name}</div>
            <div class="slide-status ${slide.converted ? 'converted' : 'viewable'}">
                ${slide.converted ? '✓ Converted' : '👁 Ready'}
            </div>
        </div>
    `).join('');
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

        // Find slide object to get filename
        const slide = slides.find(s => s.name === slideName);
        if (!slide) throw new Error('Slide not found in list');

        // Get slide info
        const infoResponse = await fetch(`${API_BASE}/api/info/${slideName}`);
        if (!infoResponse.ok) throw new Error('Failed to load slide info');

        const slideInfo = await infoResponse.json();

        // Display slide info
        displaySlideInfo(slideInfo);

        // Use dynamic DZI for all slides - this works for both converted and unconverted slides
        // because the backend handles on-the-fly tiling
        console.log('Using dynamic DZI source for instant viewing');
        const dziUrl = `${API_BASE}/api/dynamic_dzi/${slideName}.dzi`;
        loadInViewer(dziUrl, 'dzi');

        // Update slides list
        renderSlidesList();



        // Reset density overlay state
        if (densityOverlayImage) {
            viewer.world.removeItem(densityOverlayImage);
            densityOverlayImage = null;
        }
        densityOverlayEnabled = false;
        densityGridData = null;
        const densityBtn = document.getElementById('toggle-density-btn');
        if (densityBtn) {
            densityBtn.textContent = 'Show Cancer Density';
        }

        showToast(`Loaded: ${slideName}`, 'success');

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
                    method: 'HEAD',
                    headers: {
                        'Range': 'bytes=0-1023'
                    }
                });
                console.log('URL test response status:', testResponse.status);
                console.log('URL test response headers:', Object.fromEntries(testResponse.headers.entries()));
            } catch (testError) {
                console.warn('URL accessibility test failed (may be OK):', testError);
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
        } catch (e) {
            console.error('Failed to create GeoTIFFTileSource:', e);
            console.error('Error name:', e.name);
            console.error('Error message:', e.message);
            console.error('Error stack:', e.stack);

            // Check if it's a GCS file
            const isGCSFile = sourceUrl.includes('storage.googleapis.com') || sourceUrl.includes('storage.cloud.google.com');

            if (isGCSFile) {
                showToast(`Failed to load GCS file: ${e.message}. The file may require CORS configuration or the signed URL may have expired.`, 'error');
            } else {
                console.warn('GeoTIFF direct viewing failed, attempting fallback to DZI...');
                showToast('Direct viewing failed, falling back to converted tiles...', 'warning');
                loadDziFallback();
            }
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
            // If we successfully opened a GeoTIFF, show a success message
            if (type === 'geotiff') {
                showToast('Viewing directly from raw file (GeoTIFF)', 'success');
            }

            // Try to load density overlay for this slide
            if (currentSlide) {
                loadDensityOverlay(currentSlide);
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

            if (type === 'geotiff') {
                console.log('GeoTIFF open failed:', errorMessage);
                // For GCS files, we can't fallback to DZI since they're not converted
                const isGCSFile = sourceUrl.includes('storage.googleapis.com') || sourceUrl.includes('storage.cloud.google.com');
                if (isGCSFile) {
                    showToast(`Failed to load GCS file: ${errorMessage}. Check CORS settings or try downloading the file first.`, 'error');
                } else {
                    console.log('GeoTIFF open failed, attempting fallback to DZI');
                    showToast('Direct view failed, falling back to converted tiles...', 'warning');
                    loadDziFallback();
                }
            } else {
                showToast(`Failed to open slide: ${errorMessage}`, 'error');
                showViewerPlaceholder();
            }
        });

    } catch (error) {
        console.error('Error creating viewer:', error);
        if (type === 'geotiff') {
            loadDziFallback();
        }
    }
}

function loadDziFallback() {
    if (currentSlide) {
        const dziUrl = `${API_BASE}/api/dzi/${currentSlide}.dzi`;
        console.log('Falling back to DZI:', dziUrl);
        loadInViewer(dziUrl, 'dzi');
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
// Display Slide Info
// ========================================

function displaySlideInfo(info) {
    const infoSection = document.getElementById('info-section');
    const infoContent = document.getElementById('info-content');

    const [width, height] = info.dimensions;
    const props = info.properties;

    let html = `
        <div class="info-row">
            <span class="info-label">Dimensions</span>
            <span class="info-value">${width.toLocaleString()} × ${height.toLocaleString()}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Levels</span>
            <span class="info-value">${info.level_count}</span>
        </div>
    `;

    if (props['openslide.vendor']) {
        html += `
            <div class="info-row">
                <span class="info-label">Vendor</span>
                <span class="info-value">${props['openslide.vendor']}</span>
            </div>
        `;
    }

    if (props['openslide.objective-power']) {
        html += `
            <div class="info-row">
                <span class="info-label">Magnification</span>
                <span class="info-value">${props['openslide.objective-power']}×</span>
            </div>
        `;
    }

    if (props['openslide.mpp-x'] && props['openslide.mpp-y']) {
        html += `
            <div class="info-row">
                <span class="info-label">Resolution</span>
                <span class="info-value">${parseFloat(props['openslide.mpp-x']).toFixed(3)} μm/px</span>
            </div>
        `;
    }

    infoContent.innerHTML = html;
    infoSection.style.display = 'block';
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

async function loadDensityOverlay(slideName) {
    if (!viewer) return;

    try {
        // Fetch per-slide overlay configuration from backend
        const configResponse = await fetch(`${API_BASE}/api/overlay-config/${slideName}`);
        if (!configResponse.ok) {
            console.log('No overlay config available for this slide');
            return;
        }

        const config = await configResponse.json();
        if (!config.available) {
            console.log('Overlay files not available for this slide');
            return;
        }

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

async function toggleDensityOverlay() {
    if (!viewer) return;

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
        showToast('No density overlay available for this slide', 'info');
        return;
    }

    densityOverlayEnabled = !densityOverlayEnabled;
    const btn = document.getElementById('toggle-density-btn');

    const sliderContainer = document.getElementById('density-slider-container');
    const opacitySlider = document.getElementById('density-opacity');

    if (densityOverlayEnabled) {
        // Show the overlay with current slider value
        const opacity = opacitySlider ? parseInt(opacitySlider.value) / 100 : 0.6;
        densityOverlayImage.setOpacity(opacity);
        btn.textContent = 'Hide Cancer Density';
        btn.classList.add('active');
        if (sliderContainer) sliderContainer.style.display = 'block';

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

        showToast('Cancer density overlay enabled', 'success');
    } else {
        // Hide the overlay and slider
        densityOverlayImage.setOpacity(0);
        btn.textContent = 'Show Cancer Density';
        btn.classList.remove('active');
        if (sliderContainer) sliderContainer.style.display = 'none';
        showToast('Cancer density overlay disabled', 'info');
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
