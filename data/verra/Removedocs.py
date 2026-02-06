import json
from copy import deepcopy
from pathlib import Path

def strip_documents(payload):
    """
    Supports BOTH formats:
    A) {"projects": [ { "VCS_1764": {..., "documents": [...] } }, ... ]}
    B) [ { "VCS_1764": {..., "documents": [...] } }, ... ]
    """
    out = deepcopy(payload)

    # Case A: dict with "projects"
    if isinstance(out, dict) and isinstance(out.get("projects"), list):
        project_list = out["projects"]

    # Case B: directly a list
    elif isinstance(out, list):
        project_list = out

    else:
        raise ValueError(
            f"Unexpected JSON shape. Top-level type={type(out)} keys={list(out.keys()) if isinstance(out, dict) else 'N/A'}"
        )

    for project_wrapper in project_list:
        # project_wrapper looks like {"VCS_1764": {...}}
        if not isinstance(project_wrapper, dict):
            continue

        for _, project_data in project_wrapper.items():
            if isinstance(project_data, dict):
                project_data.pop("documents", None)

    return out


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent  # verra/
    in_path = base_dir / "projects.json"
    out_path = base_dir / "projects_without_docs.json"

    if not in_path.exists():
        raise FileNotFoundError(f"Can't find: {in_path}")

    with in_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    cleaned = strip_documents(payload)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print(f"✅ Wrote {out_path}")
