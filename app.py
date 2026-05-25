import os
import json
import threading
import time
from urllib.parse import urlparse
from flask import Flask, render_template, request, send_from_directory, redirect
import docker

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
CONFIG_FOLDER = "config"
DYNAMIC_FILE = os.path.join(CONFIG_FOLDER, "dynamic.json")
MOCK_FILE = os.path.join("resources", "mocks.json")
USE_MOCKS = os.getenv("SHADY_USE_MOCKS", "").lower() in {"1", "true", "yes", "on"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CONFIG_FOLDER, exist_ok=True)

docker_client = None

containers_list = []
static_files_list = []
dynamic_entries_list = []
docker_status = "mock" if USE_MOCKS else "unknown"


def load_mock_entries(section):
    try:
        with open(MOCK_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError, TypeError):
        return []

    entries = []
    for item in data.get(section, []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        if name and url:
            entries.append({"name": name, "url": url})
    return sorted(entries, key=lambda item: item["name"].lower())


def safe_path_segment(name):
    cleaned = os.path.basename((name or "").strip())
    if not cleaned or cleaned in {".", ".."}:
        return None
    return cleaned


def is_valid_url(url):
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def get_docker_client():
    global docker_client
    if docker_client is None:
        docker_client = docker.DockerClient("unix:///var/run/docker.sock")
    return docker_client


def scan_static_files():
    global static_files_list
    if USE_MOCKS:
        static_files_list = load_mock_entries("static_files")
        return

    files = []
    if os.path.exists(UPLOAD_FOLDER):
        for folder_name in os.listdir(UPLOAD_FOLDER):
            folder_path = os.path.join(UPLOAD_FOLDER, folder_name)
            if not os.path.isdir(folder_path):
                continue
            index_path = os.path.join(folder_path, "index.html")
            if os.path.isfile(index_path):
                files.append({"name": folder_name, "url": f"/{folder_name}/"})
    files.sort(key=lambda item: item["name"].lower())
    static_files_list = files


def scan_dynamic_entries():
    global dynamic_entries_list
    if USE_MOCKS:
        dynamic_entries_list = load_mock_entries("dynamic_entries")
        return

    entries = []
    if not os.path.isfile(DYNAMIC_FILE):
        dynamic_entries_list = []
        return

    try:
        with open(DYNAMIC_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                url = str(item.get("url", "")).strip()
                if name and url:
                    entries.append({"name": name, "url": url})
    except (OSError, ValueError, TypeError):
        pass

    entries.sort(key=lambda item: item["name"].lower())
    dynamic_entries_list = entries


def save_dynamic_entries(entries):
    with open(DYNAMIC_FILE, "w", encoding="utf-8") as file:
        json.dump(entries, file, indent=2)


def watch_containers():
    global containers_list, docker_status
    while True:
        try:
            new_list = []
            if USE_MOCKS:
                containers_list = load_mock_entries("containers")
                docker_status = "mock"
                time.sleep(5)
                continue

            for container in get_docker_client().containers.list():
                labels = container.labels
                if "shady.name" in labels and "shady.url" in labels:
                    new_list.append(
                        {"name": labels["shady.name"], "url": labels["shady.url"]}
                    )
            containers_list = sorted(new_list, key=lambda item: item["name"].lower())
            docker_status = "connected"
        except Exception:
            docker_status = "unavailable"
        time.sleep(5)


def watch_static_files():
    while True:
        scan_static_files()
        time.sleep(5)


def watch_dynamic_entries():
    while True:
        scan_dynamic_entries()
        time.sleep(5)


@app.route("/")
def dashboard():
    global containers_list, docker_status
    if USE_MOCKS:
        containers_list = load_mock_entries("containers")
        docker_status = "mock"
    scan_static_files()
    scan_dynamic_entries()
    return render_template(
        "index.html",
        containers=containers_list,
        static_files=static_files_list,
        dynamic_entries=dynamic_entries_list,
        docker_status=docker_status,
        use_mocks=USE_MOCKS,
    )


@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files")
    if not files:
        return "No files", 400

    paths = request.form.getlist("paths")
    if len(paths) != len(files):
        return "Invalid upload", 400

    root_name = None
    normalized = []
    for file_obj, rel_path in zip(files, paths):
        rel_path = (rel_path or "").replace("\\", "/").strip("/")
        if not rel_path:
            continue

        parts = [safe_path_segment(part) for part in rel_path.split("/")]
        if any(part is None for part in parts):
            return "Invalid path", 400

        current_root = parts[0]
        if root_name is None:
            root_name = current_root
        elif current_root != root_name:
            return "Upload a single folder", 400

        normalized.append((file_obj, parts))

    if not root_name:
        return "Invalid folder", 400

    root_folder = os.path.join(UPLOAD_FOLDER, root_name)
    os.makedirs(root_folder, exist_ok=True)

    has_index = False
    for file_obj, parts in normalized:
        target_path = os.path.join(UPLOAD_FOLDER, *parts)
        if os.path.commonpath([UPLOAD_FOLDER, target_path]) != UPLOAD_FOLDER:
            return "Invalid path", 400

        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        file_obj.save(target_path)

        if parts[-1].lower() == "index.html":
            has_index = True

    if not has_index or not os.path.isfile(os.path.join(root_folder, "index.html")):
        return "Folder must include index.html", 400

    scan_static_files()
    return "OK", 200


@app.route("/dynamic", methods=["POST"])
def add_dynamic_entry():
    name = (request.form.get("name") or "").strip()
    url = (request.form.get("url") or "").strip()

    if not name or not url:
        return "Name and URL are required", 400

    if not is_valid_url(url):
        return "URL must start with http:// or https://", 400

    scan_dynamic_entries()

    for entry in dynamic_entries_list:
        if entry["name"].lower() == name.lower():
            return "Name already exists", 400

    updated = dynamic_entries_list + [{"name": name, "url": url}]
    save_dynamic_entries(updated)
    scan_dynamic_entries()
    return redirect("/")


@app.route("/dynamic/<name>", methods=["POST"])
def delete_dynamic_entry(name):
    target = (name or "").strip().lower()
    if not target:
        return "Name is required", 400

    scan_dynamic_entries()
    updated = [entry for entry in dynamic_entries_list if entry["name"].lower() != target]
    if len(updated) == len(dynamic_entries_list):
        return "Not found", 404

    save_dynamic_entries(updated)
    scan_dynamic_entries()
    return redirect("/")


@app.route("/health")
def health():
    return {
        "ok": True,
        "docker_status": docker_status,
        "use_mocks": USE_MOCKS,
    }


@app.route("/<folder>/")
def serve_static_index(folder):
    folder_name = safe_path_segment(folder)
    if folder_name is None:
        return "Not found", 404
    folder_path = os.path.join(UPLOAD_FOLDER, folder_name)
    if not os.path.isdir(folder_path):
        return "Not found", 404
    return send_from_directory(folder_path, "index.html")


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory("assets", filename)


if __name__ == "__main__":
    threading.Thread(target=watch_containers, daemon=True).start()
    threading.Thread(target=watch_static_files, daemon=True).start()
    threading.Thread(target=watch_dynamic_entries, daemon=True).start()
    app.run(host="0.0.0.0", port=7111, debug=False)
