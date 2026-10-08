"""Run packaged sample validation from a read-only executable directory."""
import csv
import json
import os
from pathlib import Path
from build_artifact import executable_path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
sid_output = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], encoding="utf-8", errors="replace")
sid = next(row[1] for row in csv.reader(sid_output.splitlines()) if len(row) > 1 and row[1].startswith("S-1-"))
with tempfile.TemporaryDirectory(prefix="사진 검수 단일 배포-") as directory:
    temporary = Path(directory).resolve()
    app_dir = temporary / "읽기 전용 실행 폴더"
    app_dir.mkdir()
    executable = app_dir / executable_path(root).name
    shutil.copyfile(executable_path(root), executable)
    env = {key: value for key, value in os.environ.items() if not key.startswith(("PYTHON", "QT_"))}
    env["PATH"] = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")
    env["LOCALAPPDATA"] = str(temporary / "사용자 데이터")
    env["TEMP"] = env["TMP"] = str(temporary / "존재하지 않는 기본 임시 폴더")
    env["QT_QPA_PLATFORM"] = "offscreen"
    # The only permission mutation is on this newly-created, verified temp directory.
    assert app_dir.is_relative_to(temporary)
    deny = subprocess.run(["icacls", str(app_dir), "/deny", f"*{sid}:(W)"], capture_output=True)
    assert deny.returncode == 0
    try:
        report = root / "build" / "sample-frozen.json"
        result = subprocess.run([str(executable), "--validate-folder", str(root / "sample"), str(report)],
                                cwd=app_dir, env=env, timeout=1800, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, f"validation exit {result.returncode}"
        data = json.loads(report.read_text(encoding="utf-8"))
        data["deployment_conditions"] = {"single_executable_only": True,
            "python_paths_removed": True, "readonly_executable_directory": True,
            "invalid_default_tmp": True, "runtime_in_user_local_data": True}
        report.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        permission_report = root / "build" / "frozen-permissions.json"
        # The application scan above deliberately used a broken default TEMP.
        # Diagnostic fixtures need a real writable directory for creating ACL cases.
        fixture_env = dict(env, TMP=str(temporary), TEMP=str(temporary))
        fixtures = list((root / "sample").rglob("120200199.jpg"))
        assert len(fixtures) == 1, "Permission-test sample must have one unambiguous location"
        permission_result = subprocess.run([str(executable), "--permission-test",
            str(fixtures[0]), str(permission_report)],
            cwd=app_dir, env=fixture_env, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
        permissions = json.loads(permission_report.read_text(encoding="utf-8"))
        assert permission_result.returncode == 0 and permissions["ok"] and permissions["frozen"], permissions
        assert str(temporary).casefold() in permissions["python_dll"].casefold(), permissions
        assert "_mei" in permissions["python_dll"].casefold(), permissions
        permissions["deployment_conditions"] = dict(data["deployment_conditions"],
            invalid_default_tmp=False, diagnostic_fixture_temp_available=True)
        permission_report.write_text(json.dumps(permissions, ensure_ascii=False, indent=2), encoding="utf-8")
        assert all(data["ui_checks"].values()), data["ui_checks"]
        print(json.dumps({key: data[key] for key in ("ok", "total", "counts", "elapsed_seconds", "memory", "deployment_conditions")}, ensure_ascii=False))
    finally:
        restore = subprocess.run(["icacls", str(app_dir), "/remove:d", f"*{sid}"], capture_output=True)
        assert restore.returncode == 0
