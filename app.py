import os
import threading
import time
from flask import Flask, render_template, request, send_from_directory
import docker

app = Flask(__name__)

UPLOAD_FOLDER = "/app/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

docker_client = docker.DockerClient("unix:///var/run/docker.sock")

containers_list = []
static_files_list = []


def safe_path_segment(name):
    cleaned = os.path.basename((name or "").strip())
    if not cleaned or cleaned in {".", ".."}:
        return None
    return cleaned


def scan_static_files():
    global static_files_list
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


def watch_containers():
    global containers_list
    while True:
        try:
            new_list = []
            for container in docker_client.containers.list():
                labels = container.labels
                if "shady.name" in labels and "shady.url" in labels:
                    new_list.append(
                        {"name": labels["shady.name"], "url": labels["shady.url"]}
                    )
            containers_list = new_list
        except:
            pass
        time.sleep(5)


def watch_static_files():
    while True:
        scan_static_files()
        time.sleep(5)


@app.route("/")
def dashboard():
    scan_static_files()
    return render_template(
        "index.html", containers=containers_list, static_files=static_files_list
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


@app.route("/<folder>/")
def serve_static_index(folder):
    folder_name = safe_path_segment(folder)
    if folder_name is None:
        return "Not found", 404
    folder_path = os.path.join(UPLOAD_FOLDER, folder_name)
    if not os.path.isdir(folder_path):
        return "Not found", 404
    return send_from_directory(folder_path, "index.html")


@app.route("/<path:filename>")
def serve_static(filename):
    normalized = filename.strip("/")
    if not normalized:
        return "Not found", 404
    return send_from_directory(UPLOAD_FOLDER, normalized)
    return "Not found", 404


if __name__ == "__main__":
    threading.Thread(target=watch_containers, daemon=True).start()
    threading.Thread(target=watch_static_files, daemon=True).start()
    port = int(os.environ.get("FLASK_RUN_PORT", 7111))
    app.run(host="0.0.0.0", port=port, debug=False)
