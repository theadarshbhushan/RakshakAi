"""
Verification script for media analysis upload:
- Uploads data/videos/intrusion/intrusion_01.mp4 to cam_terrace with sim_start 23:40
- Polls job until done
- Confirms incident created
- Confirms annotated video with bounding boxes exists and is non-empty
"""
import httpx
import json
from pathlib import Path
import sys
import time

BASE_URL = "http://localhost:8000"
VIDEO_PATH = Path("data/videos/intrusion/intrusion_01.mp4")

def main():
    assert VIDEO_PATH.exists(), f"Video file not found at {VIDEO_PATH}"
    client = httpx.Client(base_url=BASE_URL, timeout=120.0)

    # 1. Login
    login_res = client.post("/api/v1/auth/login", json={"email": "owner@sunrise.demo", "password": "Owner@12345"})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Logged in successfully.")

    # 2. Upload video
    print(f"Uploading {VIDEO_PATH} for camera cam_terrace at sim_start 23:40...")
    with open(VIDEO_PATH, "rb") as vf:
        files = {"file": ("intrusion_01.mp4", vf, "video/mp4")}
        data = {"camera_id": "cam_terrace", "sim_start": "23:40"}
        upload_res = client.post("/api/v1/analyze/upload", headers=headers, files=files, data=data)

    print("Upload response status:", upload_res.status_code)
    assert upload_res.status_code in (200, 202), f"Upload failed: {upload_res.text}"
    upload_data = upload_res.json()
    job_id = upload_data["job_id"]
    print(f"Job created successfully: job_id={job_id}")

    # 3. Poll job status
    print("Polling analysis job status...")
    max_wait = 60
    start_t = time.time()
    final_job = None
    while time.time() - start_t < max_wait:
        poll_res = client.get(f"/api/v1/analyze/jobs/{job_id}", headers=headers)
        assert poll_res.status_code == 200, f"Poll failed: {poll_res.text}"
        job_info = poll_res.json()
        status = job_info["status"]
        progress = job_info.get("progress", 0)
        print(f"  Job {job_id}: status={status}, progress={progress}%")
        if status in ("done", "failed", "cancelled"):
            final_job = job_info
            break
        time.sleep(2.0)

    assert final_job is not None, "Job timed out"
    print("Final Job Summary:", json.dumps(final_job, indent=2))
    assert final_job["status"] == "done", f"Job failed: {final_job.get('error')}"

    # 4. Check incident created
    incident_ids = final_job.get("incident_ids", [])
    print(f"Incidents created by job: {incident_ids}")
    assert len(incident_ids) > 0, "Expected at least one incident from intrusion video!"
    inc_res = client.get(f"/api/v1/incidents/{incident_ids[0]}", headers=headers)
    assert inc_res.status_code == 200
    inc_data = inc_res.json()
    print("Created Incident Details:")
    print(f"  ID: {inc_data['id']}")
    print(f"  Severity: {inc_data['severity']}")
    print(f"  Zone: {inc_data['zone_id']}")
    print(f"  Explanation: {inc_data['explanation']}")

    # 5. Check annotated video
    annotated_res = client.get(f"/api/v1/analyze/jobs/{job_id}/annotated", headers=headers)
    print("Annotated video endpoint status:", annotated_res.status_code)
    assert annotated_res.status_code == 200, f"Failed to get annotated video: {annotated_res.status_code}"
    video_bytes = len(annotated_res.content)
    print(f"Annotated video downloaded: {video_bytes} bytes")
    assert video_bytes > 1000, "Annotated video is too small or empty!"

    print("\nSTEP 4 PASSED: Upload analyzed, incident confirmed, and annotated video generated.")

if __name__ == "__main__":
    main()
