"""
Generates a custom app icon using ComfyUI FLUX Schnell,
converts it to .ico, and updates the desktop shortcut.
"""
import json, time, random, urllib.request, urllib.parse, sys, subprocess, io
from pathlib import Path

COMFY_URL   = "http://127.0.0.1:8188"
ICON_PATH   = Path("D:/time-tracker/icon.ico")
CLIENT_ID   = "timetracker_icongen"

PROMPT = (
    "app icon, glowing digital hourglass surrounded by circuit board traces, "
    "deep navy blue background #1a1a2e, electric blue and cyan neon glow, "
    "minimalist geometric design, sharp clean edges, high contrast, "
    "centered composition, futuristic tech aesthetic, "
    "professional software icon, no text, 4k"
)

# ── Workflow ──────────────────────────────────────────────────────────────────

def build_workflow(seed: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": "flux1-schnell.safetensors",
                         "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": "clip_l.safetensors",
                         "clip_name2": "t5xxl_fp16.safetensors",
                         "type": "flux"}},
        "3": {"class_type": "VAELoader",
              "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": PROMPT, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"text": "", "clip": ["2", 0]}},
        "6": {"class_type": "EmptyLatentImage",
              "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "7": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["4", 0],
                         "negative": ["5", 0], "latent_image": ["6", 0],
                         "seed": seed, "steps": 4, "cfg": 1.0,
                         "sampler_name": "euler", "scheduler": "simple",
                         "denoise": 1.0}},
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"images": ["8", 0],
                         "filename_prefix": "timetracker_icon"}},
    }

# ── API helpers ───────────────────────────────────────────────────────────────

def queue_prompt(workflow: dict) -> str:
    payload = json.dumps({"prompt": workflow, "client_id": CLIENT_ID}).encode()
    req = urllib.request.Request(
        f"{COMFY_URL}/prompt", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["prompt_id"]


def wait_for_result(prompt_id: str) -> dict:
    print("Generating icon with FLUX Schnell (4 steps @ 1024x1024)...")
    dots = 0
    while True:
        with urllib.request.urlopen(f"{COMFY_URL}/history/{prompt_id}") as r:
            history = json.loads(r.read())
        if prompt_id in history:
            job = history[prompt_id]
            if job.get("outputs"):
                print()
                return job["outputs"]
            if job.get("status", {}).get("status_str") == "error":
                raise RuntimeError("ComfyUI reported an error — check the ComfyUI terminal.")
        dots = (dots + 1) % 4
        print(f"\r  working{'.' * dots}   ", end="", flush=True)
        time.sleep(2)


def fetch_image(outputs: dict) -> bytes:
    for node_output in outputs.values():
        for img in node_output.get("images", []):
            params = urllib.parse.urlencode({
                "filename": img["filename"],
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output"),
            })
            with urllib.request.urlopen(f"{COMFY_URL}/view?{params}") as r:
                return r.read()
    raise RuntimeError("No image found in ComfyUI output.")

# ── ICO conversion ────────────────────────────────────────────────────────────

def make_ico(image_bytes: bytes):
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img = img.resize((256, 256), Image.LANCZOS)
    img.save(str(ICON_PATH), format="ICO",
             sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    print(f"Icon written -> {ICON_PATH}")

# ── Shortcut update ───────────────────────────────────────────────────────────

def update_shortcut():
    ps = r"""
$python  = (Get-Command python.exe -ErrorAction Stop).Source
$pythonw = $python -replace 'python\.exe$','pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = $python }
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut("$env:USERPROFILE\Desktop\Time Tracker.lnk")
$sc.TargetPath       = $pythonw
$sc.Arguments        = '"D:\time-tracker\TimeTracker.pyw"'
$sc.WorkingDirectory = "D:\time-tracker"
$sc.IconLocation     = "D:\time-tracker\icon.ico, 0"
$sc.Description      = "Time Tracker - PB&J Strategic Accounting"
$sc.Save()
Write-Host "Desktop shortcut updated with custom icon."
"""
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True, text=True)
    msg = result.stdout.strip() or result.stderr.strip()
    if msg:
        print(msg)

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    seed = random.randint(0, 2**32 - 1)
    print(f"Seed: {seed}")
    wf = build_workflow(seed)
    pid = queue_prompt(wf)
    print(f"Queued: {pid}")
    outputs = wait_for_result(pid)
    raw = fetch_image(outputs)
    make_ico(raw)
    update_shortcut()
    print("\nDone! Refresh your desktop to see the new icon.")
