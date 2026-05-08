#!/usr/bin/env python3
"""
StepInside 3D — Video to Virtual Tour Pipeline

Usage:
    python3 pipeline.py upload <video.mp4>           # Upload video to KIRI Engine
    python3 pipeline.py status <serialize_id>        # Check processing status
    python3 pipeline.py download <serialize_id>      # Download processed .ply file
    python3 pipeline.py publish <file.ply> <title>   # Publish to SuperSplat & get share link
    python3 pipeline.py full <video.mp4> <title>     # Full pipeline: upload → process → publish
"""

import os
import sys
import json
import time
import requests
from pathlib import Path

# Config
KIRI_API_BASE = "https://api.kiriengine.app/api/v1/open"
CONFIG_FILE = Path(__file__).parent / "config.json"

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_api_key():
    config = load_config()
    key = config.get("kiri_api_key", "")
    if not key:
        key = os.environ.get("KIRI_API_KEY", "")
    if not key:
        print("❌ No KIRI API key found. Set KIRI_API_KEY env var or add to config.json")
        print("   Get your key at: https://www.kiriengine.app/api/keys")
        sys.exit(1)
    return key

def upload_video(video_path):
    """Upload video to KIRI Engine for 3DGS processing."""
    api_key = get_api_key()
    video_path = Path(video_path)
    
    if not video_path.exists():
        print(f"❌ Video not found: {video_path}")
        sys.exit(1)
    
    size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"📤 Uploading {video_path.name} ({size_mb:.1f} MB)...")
    
    url = f"{KIRI_API_BASE}/3dgs/video"
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"videoFile": open(video_path, "rb")}
    data = {"isMesh": "0", "isMask": "0"}
    
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=300)
    resp.raise_for_status()
    result = resp.json()
    
    if result.get("ok"):
        serialize = result["data"]["serialize"]
        print(f"✅ Upload successful!")
        print(f"   Task ID: {serialize}")
        print(f"   Type: 3DGS Scan")
        
        config = load_config()
        config["last_task"] = serialize
        save_config(config)
        return serialize
    else:
        print(f"❌ Upload failed: {result}")
        sys.exit(1)

def check_status(serialize_id):
    """Check processing status of a task."""
    api_key = get_api_key()
    # KIRI Engine uses the task list endpoint to check status
    url = f"{KIRI_API_BASE}/3dgs/status"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"serialize": serialize_id}
    
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    
    if resp.status_code == 200:
        result = resp.json()
        print(json.dumps(result, indent=2))
        return result
    else:
        # Fallback: check via task list
        url = f"{KIRI_API_BASE}/task/list"
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            tasks = resp.json()
            for task in tasks.get("data", []):
                if task.get("serialize") == serialize_id:
                    print(json.dumps(task, indent=2))
                    return task
        print(f"⚠️ Could not check status. HTTP {resp.status_code}")
        print(resp.text[:500])
        return None

def download_result(serialize_id, output_dir="output"):
    """Download the processed Gaussian Splat file."""
    api_key = get_api_key()
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    # Check task status first
    print(f"🔍 Checking status for {serialize_id}...")
    
    # Try to download the PLY file
    url = f"{KIRI_API_BASE}/3dgs/download"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"serialize": serialize_id}
    
    resp = requests.get(url, headers=headers, params=params, timeout=120, stream=True)
    
    if resp.status_code == 200:
        output_file = output_dir / f"{serialize_id}.ply"
        total = 0
        with open(output_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                total += len(chunk)
        print(f"✅ Downloaded: {output_file} ({total / (1024*1024):.1f} MB)")
        return output_file
    else:
        print(f"❌ Download failed. HTTP {resp.status_code}")
        print("   The task may still be processing. Check status first.")
        print(resp.text[:500])
        return None

def publish_to_supersplat(ply_path, title="Property Tour"):
    """
    Instructions for publishing to SuperSplat.
    
    SuperSplat doesn't have a public API yet, so this is manual for now.
    The PlayCanvas team has mentioned API plans on their roadmap.
    """
    ply_path = Path(ply_path)
    print(f"""
📋 PUBLISH TO SUPERSPLAT (Manual Steps)
========================================

1. Open https://playcanvas.com/supersplat/editor
2. Click "Import" and select: {ply_path}
3. Wait for processing and optimization
4. Clean up the scene (crop unwanted areas, adjust)
5. Enable "Walk Mode" in settings
6. Click "Publish" 
7. Set title: "{title}"
8. Copy the shareable link

The link will look like: https://superspl.at/xxxxx

Send that link to the estate agent! 🎉

💡 TIP: For a future automated pipeline, we could use the PlayCanvas 
   Engine to self-host the viewer on our GitHub Pages site.
""")

def full_pipeline(video_path, title="Property Tour"):
    """Run the complete pipeline."""
    print(f"""
🚀 StepInside 3D — Full Pipeline
=================================
Video: {video_path}
Title: {title}
""")
    
    # Step 1: Upload
    serialize_id = upload_video(video_path)
    
    # Step 2: Wait for processing
    print(f"\n⏳ Processing... KIRI Engine typically takes 5-15 minutes.")
    print(f"   Task ID: {serialize_id}")
    print(f"\n   You can check status later with:")
    print(f"   python3 pipeline.py status {serialize_id}")
    
    # Step 3: Try to poll
    print(f"\n🔄 Polling for completion (checking every 60s)...")
    max_wait = 30  # 30 minutes max
    
    for i in range(max_wait):
        time.sleep(60)
        print(f"   [{i+1}/{max_wait}] Checking...", end=" ")
        
        status = check_status(serialize_id)
        if status:
            state = status.get("status", status.get("state", ""))
            print(f"Status: {state}")
            
            if state in ["completed", "done", "finished", "success"]:
                print(f"\n✅ Processing complete!")
                result = download_result(serialize_id)
                if result:
                    publish_to_supersplat(result, title)
                return
            elif state in ["failed", "error"]:
                print(f"\n❌ Processing failed: {status}")
                return
    
    print(f"\n⏰ Timeout after {max_wait} minutes. Check manually:")
    print(f"   python3 pipeline.py status {serialize_id}")
    print(f"   python3 pipeline.py download {serialize_id}")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "upload" and len(sys.argv) >= 3:
        upload_video(sys.argv[2])
    elif command == "status" and len(sys.argv) >= 3:
        check_status(sys.argv[2])
    elif command == "download" and len(sys.argv) >= 3:
        download_result(sys.argv[2])
    elif command == "publish" and len(sys.argv) >= 3:
        publish_to_supersplat(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "Property Tour")
    elif command == "full" and len(sys.argv) >= 3:
        title = sys.argv[3] if len(sys.argv) > 3 else "Property Tour"
        full_pipeline(sys.argv[2], title)
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
