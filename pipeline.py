#!/usr/bin/env python3
"""
StepInside 3D — Video to Virtual Tour Pipeline

Usage:
    python3 pipeline.py upload <video.mp4>           # Upload video to KIRI Engine
    python3 pipeline.py status <serialize_id>        # Check processing status
    python3 pipeline.py download <serialize_id>      # Download processed .ply file
    python3 pipeline.py publish <file.ply> <title>   # Publish to SuperSplat & get share link
    python3 pipeline.py balance                      # Check API credit balance
    python3 pipeline.py full <video.mp4> <title>     # Full pipeline: upload → process → publish

API Endpoints (from docs.kiriengine.app):
    POST   /api/v1/open/3dgs/video        — Upload video for 3DGS processing
    GET    /api/v1/open/model/getStatus    — Check processing status
    GET    /api/v1/open/model/getModelZip  — Download processed model (zip, link valid 60 min)
    GET    /api/v1/open/balance            — Check credit balance

Status codes:
    -1 = Uploading
     0 = Processing
     1 = Failed
     2 = Successful ✓
     3 = Queuing
     4 = Expired
"""

import os
import sys
import json
import time
import requests
from pathlib import Path

# Config
API_BASE = "https://api.kiriengine.app/api/v1/open"
PROJECT_DIR = Path(__file__).parent
CONFIG_FILE = PROJECT_DIR / "config.json"
OUTPUT_DIR = PROJECT_DIR / "output"

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
    key = config.get("kiri_api_key", "") or os.environ.get("KIRI_API_KEY", "")
    if not key:
        print("❌ No KIRI API key found. Set KIRI_API_KEY env var or add to config.json")
        print("   Get your key at: https://www.kiriengine.app/api/keys")
        sys.exit(1)
    return key

def headers():
    return {"Authorization": f"Bearer {get_api_key()}"}

def check_balance():
    """Check credit balance."""
    resp = requests.get(f"{API_BASE}/balance", headers=headers(), timeout=10)
    resp.raise_for_status()
    result = resp.json()
    balance = result.get("data", {}).get("balance", "?")
    print(f"💰 Credit balance: {balance} credits")
    return balance

def upload_video(video_path):
    """Upload video to KIRI Engine for 3DGS processing."""
    video_path = Path(video_path)
    
    if not video_path.exists():
        print(f"❌ Video not found: {video_path}")
        sys.exit(1)
    
    size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"📤 Uploading {video_path.name} ({size_mb:.1f} MB)...")
    
    url = f"{API_BASE}/3dgs/video"
    files = {"videoFile": open(video_path, "rb")}
    data = {"isMesh": "0", "isMask": "0"}
    
    resp = requests.post(url, headers=headers(), files=files, data=data, timeout=300)
    resp.raise_for_status()
    result = resp.json()
    
    if result.get("ok"):
        serialize = result["data"]["serialize"]
        calc_type = result["data"].get("calculateType", "?")
        print(f"✅ Upload successful!")
        print(f"   Task ID: {serialize}")
        print(f"   Type: {calc_type} (3 = 3DGS Scan)")
        
        config = load_config()
        config["last_task"] = serialize
        save_config(config)
        return serialize
    else:
        print(f"❌ Upload failed: {result}")
        sys.exit(1)

def check_status(serialize_id):
    """Check processing status. Returns status code."""
    resp = requests.get(
        f"{API_BASE}/model/getStatus",
        headers=headers(),
        params={"serialize": serialize_id},
        timeout=30
    )
    resp.raise_for_status()
    result = resp.json()
    
    status_map = {
        -1: "📤 Uploading",
        0: "⚙️ Processing",
        1: "❌ Failed",
        2: "✅ Successful",
        3: "⏳ Queuing",
        4: "⏰ Expired"
    }
    
    status_code = result.get("data", {}).get("status", "?")
    status_text = status_map.get(status_code, f"Unknown ({status_code})")
    print(f"Status: {status_text}")
    
    return result

def download_result(serialize_id):
    """Download the processed model as zip."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    print(f"📥 Requesting download link for {serialize_id}...")
    resp = requests.get(
        f"{API_BASE}/model/getModelZip",
        headers=headers(),
        params={"serialize": serialize_id},
        timeout=30
    )
    resp.raise_for_status()
    result = resp.json()
    
    if not result.get("ok"):
        print(f"❌ Download request failed: {result}")
        return None
    
    model_url = result.get("data", {}).get("modelUrl")
    if not model_url:
        print("❌ No download URL returned")
        return None
    
    print(f"📦 Downloading model (link valid 60 min)...")
    download_resp = requests.get(model_url, timeout=120, stream=True)
    download_resp.raise_for_status()
    
    output_file = OUTPUT_DIR / f"{serialize_id}.zip"
    total = 0
    with open(output_file, "wb") as f:
        for chunk in download_resp.iter_content(chunk_size=8192):
            f.write(chunk)
            total += len(chunk)
    
    print(f"✅ Downloaded: {output_file} ({total / (1024*1024):.1f} MB)")
    
    # Extract zip
    import zipfile
    with zipfile.ZipFile(output_file, 'r') as z:
        z.extractall(OUTPUT_DIR / serialize_id)
        print(f"📂 Extracted to: {OUTPUT_DIR / serialize_id}")
        # Find .ply file
        for name in z.namelist():
            if name.endswith('.ply'):
                ply_path = OUTPUT_DIR / serialize_id / name
                print(f"   Found PLY: {ply_path}")
                return ply_path
    
    return output_file

def publish_to_supersplat(ply_path, title="Property Tour"):
    """
    Instructions for publishing to SuperSplat.
    SuperSplat doesn't have a public API yet — manual step for now.
    """
    ply_path = Path(ply_path)
    size_mb = ply_path.stat().st_size / (1024 * 1024) if ply_path.exists() else 0
    print(f"""
📋 PUBLISH TO SUPERSPLAT
========================

1. Open https://playcanvas.com/supersplat/editor
2. Click "Import" → select: {ply_path}
   (File size: {size_mb:.1f} MB)
3. Wait for optimization
4. Crop unwanted areas, adjust scene
5. Enable "Walk Mode" for first-person navigation
6. Click "Publish"
7. Title: "{title}"
8. Copy the shareable link (e.g. superspl.at/xxxxx)

🎉 Send that link to the estate agent!

💡 Alternative: We can self-host a PlayCanvas viewer on our 
   GitHub Pages site for a fully branded experience.
""")

def full_pipeline(video_path, title="Property Tour"):
    """Run the complete pipeline: upload → wait → download → publish."""
    print(f"""
🚀 StepInside 3D — Full Pipeline
=================================
Video: {video_path}
Title: {title}
""")
    
    # Check balance first
    balance = check_balance()
    if isinstance(balance, (int, float)) and balance < 1:
        print("❌ Not enough credits!")
        sys.exit(1)
    
    # Step 1: Upload
    serialize_id = upload_video(video_path)
    
    # Step 2: Wait for processing
    print(f"\n⏳ Processing... typically takes 5-15 minutes.")
    print(f"   Task ID: {serialize_id}")
    
    # Step 3: Poll for completion
    print(f"\n🔄 Polling (every 30s, max 30 min)...")
    max_checks = 60
    
    for i in range(max_checks):
        time.sleep(30)
        result = check_status(serialize_id)
        status_code = result.get("data", {}).get("status")
        
        if status_code == 2:  # Successful
            print(f"\n✅ Processing complete!")
            ply = download_result(serialize_id)
            if ply:
                publish_to_supersplat(ply, title)
            return ply
        elif status_code == 1:  # Failed
            print(f"\n❌ Processing failed!")
            return None
        elif status_code == 4:  # Expired
            print(f"\n⏰ Task expired!")
            return None
        else:
            elapsed = (i + 1) * 30
            print(f"   [{elapsed}s elapsed] Still processing...")
    
    print(f"\n⏰ Timeout after 30 minutes. Check manually:")
    print(f"   python3 pipeline.py status {serialize_id}")
    print(f"   python3 pipeline.py download {serialize_id}")
    return None

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "balance":
        check_balance()
    elif command == "upload" and len(sys.argv) >= 3:
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
