"""
WSI to DeepZoom Converter
Handles conversion of whole slide imaging files to DeepZoom format
"""

import os
import json
from pathlib import Path
import openslide
from openslide import OpenSlide
from openslide.deepzoom import DeepZoomGenerator


class WSIConverter:
    """Converts WSI files to DeepZoom format with caching"""
    
    def __init__(self, upload_dir='uploads', cache_dir='cache'):
        """
        Initialize the converter
        
        Args:
            upload_dir: Directory for uploaded WSI files
            cache_dir: Directory for cached DeepZoom tiles
        """
        self.upload_dir = Path(upload_dir)
        self.cache_dir = Path(cache_dir)
        
        # Create directories if they don't exist
        if not self.upload_dir.exists():
            self.upload_dir.mkdir(parents=True)
        elif not self.upload_dir.is_dir():
            raise ValueError(f"Upload path exists but is not a directory: {self.upload_dir}")
            
        if not self.cache_dir.exists():
            self.cache_dir.mkdir(parents=True)
        elif not self.cache_dir.is_dir():
            raise ValueError(f"Cache path exists but is not a directory: {self.cache_dir}")
    
    def get_slide_info(self, slide_path):
        """
        Extract metadata from a WSI file
        
        Args:
            slide_path: Path to the WSI file
            
        Returns:
            Dictionary containing slide metadata
        """
        try:
            slide = OpenSlide(str(slide_path))
            
            # Extract basic properties
            info = {
                'dimensions': slide.dimensions,
                'level_count': slide.level_count,
                'level_dimensions': slide.level_dimensions,
                'level_downsamples': slide.level_downsamples,
                'properties': {}
            }
            
            # Extract relevant properties
            important_props = [
                openslide.PROPERTY_NAME_VENDOR,
                openslide.PROPERTY_NAME_QUICKHASH1,
                openslide.PROPERTY_NAME_BACKGROUND_COLOR,
                openslide.PROPERTY_NAME_OBJECTIVE_POWER,
                openslide.PROPERTY_NAME_MPP_X,
                openslide.PROPERTY_NAME_MPP_Y,
            ]
            
            for prop in important_props:
                if prop in slide.properties:
                    info['properties'][prop] = slide.properties[prop]
            
            slide.close()
            return info
            
        except Exception as e:
            raise Exception(f"Failed to read slide info: {str(e)}")
    
    def get_dzi_path(self, slide_name):
        """Get the path for DZI file for a given slide"""
        return self.cache_dir / f"{slide_name}.dzi"
    
    def get_tiles_dir(self, slide_name):
        """Get the directory path for tiles for a given slide"""
        return self.cache_dir / f"{slide_name}_files"
    
    def is_converted(self, slide_name):
        """Check if a slide has been fully converted to DeepZoom"""
        dzi_path = self.get_dzi_path(slide_name)
        tiles_dir = self.get_tiles_dir(slide_name)
        marker_path = tiles_dir / "completed.txt"
        return dzi_path.exists() and tiles_dir.exists() and marker_path.exists()

    def is_viewable(self, slide_name):
        """Check if a slide is ready for viewing (DZI exists)"""
        dzi_path = self.get_dzi_path(slide_name)
        return dzi_path.exists()
    
    def convert_to_deepzoom(self, slide_path, tile_size=256, overlap=1, limit_bounds=False, progress_callback=None):
        """
        Convert a WSI file to DeepZoom format
        
        Args:
            slide_path: Path to the WSI file
            tile_size: Size of each tile (default: 256)
            overlap: Overlap between tiles (default: 1)
            limit_bounds: Whether to limit bounds (default: False)
            progress_callback: Optional callback function(current_tiles, total_tiles)
            
        Returns:
            Path to the generated DZI file
        """
        try:
            slide_path = Path(slide_path)
            slide_name = slide_path.stem
            
            print(f"\n{'='*60}")
            print(f"Starting conversion: {slide_name}")
            print(f"{'='*60}")
            
            # Check if already converted
            if self.is_converted(slide_name):
                print(f"✓ Slide already converted, using cached version")
                if progress_callback:
                    progress_callback(1, 1)  # 100%
                return self.get_dzi_path(slide_name)
            
            # Open the slide
            print(f"Opening slide file...")
            slide = OpenSlide(str(slide_path))
            
            # Print slide info
            width, height = slide.dimensions
            print(f"Slide dimensions: {width:,} x {height:,} pixels")
            print(f"Pyramid levels: {slide.level_count}")
            
            # Create DeepZoom generator
            print(f"Creating DeepZoom generator (tile size: {tile_size}px, overlap: {overlap}px)...")
            dz = DeepZoomGenerator(
                slide,
                tile_size=tile_size,
                overlap=overlap,
                limit_bounds=limit_bounds
            )
            
            # Get output paths
            dzi_path = self.get_dzi_path(slide_name)
            tiles_dir = self.get_tiles_dir(slide_name)
            
            # Create tiles directory
            tiles_dir.mkdir(exist_ok=True)
            
            # Generate DZI descriptor file
            print(f"Generating DZI descriptor file...")
            dzi_content = dz.get_dzi('jpeg')
            with open(dzi_path, 'w') as f:
                f.write(dzi_content)
            
            # Calculate total tiles
            total_tiles = sum(cols * rows for cols, rows in dz.level_tiles)
            print(f"Total tiles to generate: {total_tiles:,}")
            print(f"DeepZoom levels: {dz.level_count}")
            print(f"\nGenerating tiles...")
            
            # Generate all tiles with progress
            tiles_generated = 0
            
            for level in range(dz.level_count):
                level_dir = tiles_dir / str(level)
                level_dir.mkdir(exist_ok=True)
                
                cols, rows = dz.level_tiles[level]
                level_tiles = cols * rows
                
                print(f"  Level {level}/{dz.level_count-1}: {cols}x{rows} = {level_tiles:,} tiles", end='')
                
                for col in range(cols):
                    for row in range(rows):
                        tile = dz.get_tile(level, (col, row))
                        tile_path = level_dir / f"{col}_{row}.jpeg"
                        tile.save(str(tile_path), 'JPEG', quality=90)
                        tiles_generated += 1
                        
                        # Call progress callback occasionally to avoid overhead
                        if progress_callback and tiles_generated % 10 == 0:
                            progress_callback(tiles_generated, total_tiles)
                
                # Show progress for this level
                progress = (tiles_generated / total_tiles) * 100
                print(f" ✓ ({progress:.1f}% complete)")
                
                if progress_callback:
                    progress_callback(tiles_generated, total_tiles)
            
            slide.close()
            
            # Write completion marker
            with open(tiles_dir / "completed.txt", 'w') as f:
                f.write("completed")
            
            print(f"\n{'='*60}")
            print(f"✓ Conversion complete!")
            print(f"  Generated {tiles_generated:,} tiles")
            print(f"  DZI file: {dzi_path.name}")
            print(f"  Tiles directory: {tiles_dir.name}")
            print(f"{'='*60}\n")
            
            return dzi_path
            
        except Exception as e:
            print(f"\n✗ Conversion failed: {str(e)}\n")
            raise Exception(f"Failed to convert slide: {str(e)}")
    
    def get_tile(self, slide_path, level, col, row):
        """
        Get a specific tile from a slide
        
        Args:
            slide_path: Path to the WSI file
            level: Zoom level
            col: Column index
            row: Row index
            
        Returns:
            PIL Image object of the tile
        """
        try:
            slide = OpenSlide(str(slide_path))
            dz = DeepZoomGenerator(slide, tile_size=256, overlap=1)
            
            tile = dz.get_tile(level, (col, row))
            slide.close()
            
            return tile
            
        except Exception as e:
            raise Exception(f"Failed to get tile: {str(e)}")
    
    def get_dzi_xml(self, slide_path, tile_size=256, overlap=1):
        """
        Generate DZI XML descriptor for a slide on the fly
        
        Args:
            slide_path: Path to the WSI file
            tile_size: Tile size (default: 256)
            overlap: Overlap (default: 1)
            
        Returns:
            XML string
        """
        try:
            slide = OpenSlide(str(slide_path))
            dz = DeepZoomGenerator(slide, tile_size=tile_size, overlap=overlap)
            xml = dz.get_dzi('jpeg')
            slide.close()
            return xml
        except Exception as e:
            raise Exception(f"Failed to generate DZI XML: {str(e)}")

    def cleanup_cache(self, slide_name=None):
        """
        Clean up cached DeepZoom files
        
        Args:
            slide_name: Optional specific slide to clean up. If None, cleans all.
        """
        if slide_name:
            # Clean up specific slide
            dzi_path = self.get_dzi_path(slide_name)
            tiles_dir = self.get_tiles_dir(slide_name)
            
            if dzi_path.exists():
                dzi_path.unlink()
            
            if tiles_dir.exists():
                import shutil
                shutil.rmtree(tiles_dir)
        else:
            # Clean up all cached files
            import shutil
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(exist_ok=True)
