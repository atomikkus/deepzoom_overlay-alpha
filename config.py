"""
Application configuration: CLI arguments and derived settings.
"""

import os
import argparse

# Parse CLI arguments
parser = argparse.ArgumentParser(description="WSI Viewer Server")
parser.add_argument("--slides", type=str, nargs='*', default=None,
                    help="One or more GCS paths (gs://bucket/path or https://storage.googleapis.com/...)")
parser.add_argument("--slides-local", type=str, nargs='*', default=None,
                    help="One or more local paths to slides")
parser.add_argument("--overlay", type=str, nargs='*', default=None,
                    help="One or more overlay directories (searched in order)")
parser.add_argument("--session-ttl", type=int, default=30,
                    help="Session TTL in minutes (default: 30)")
args, unknown = parser.parse_known_args()

# Validate and build slide paths
if args.slides and args.slides_local:
    raise ValueError("Cannot specify both --slides and --slides-local")

slide_paths = []
if args.slides:
    slide_paths.extend(args.slides)
elif args.slides_local:
    slide_paths.extend(args.slides_local)
else:
    slide_paths = ["uploads"]

overlay_paths = args.overlay if args.overlay else []

# GCS configuration
GCS_SERVICE_ACCOUNT_PATH = os.getenv(
    "GCS_SERVICE_ACCOUNT_PATH",
    "in-4bc-engineering-1f84a3a8a86d-read-access.json",
)
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "wsi_bucket53")

# Server port (Cloud Run sets PORT=8080)
PORT = int(os.getenv("PORT", 8511))
