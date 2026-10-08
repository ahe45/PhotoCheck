"""Windows diagnostic: use real ACL denial and file locks only in owned temp fixtures."""
import csv
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def python_dll_path():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel.GetModuleHandleW.restype = wintypes.HMODULE
    kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    buffer = ctypes.create_unicode_buffer(32768)
    handle = kernel.GetModuleHandleW(f"python{sys.version_info.major}{sys.version_info.minor}.dll")
    kernel.GetModuleFileNameW(handle, buffer, len(buffer))
    return buffer.value


def run(image_path, report_path):
    from .domain import Check, Result, Status
    from .export import export_excel
    from .photo_copy import copy_photos
    from .files import collect, inspect
    from .process_analyzer import ProcessAnalyzer
    from .criteria import Criteria, load_criteria, save_criteria
    from dataclasses import replace

    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)),
              "is_admin": bool(ctypes.windll.shell32.IsUserAnAdmin()),
              "python_dll": python_dll_path(), "checks": {}}
    rows = list(csv.reader(subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"],
                                                 encoding="utf-8", errors="replace").splitlines()))
    sid = next(row[1] for row in rows if len(row) > 1 and row[1].startswith("S-1-"))
    acl_paths = []

    def acl(path, operation, permission=""):
        target = str(path.resolve())
        # All mutation targets are explicitly validated to stay inside this temporary tree.
        if not Path(target).is_relative_to(root.resolve()):
            raise ValueError("ACL target escaped temporary fixture directory")
        args = ["icacls", target, operation, f"*{sid}{permission}"]
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError(f"테스트 임시 파일 ACL 설정 실패 ({result.returncode})")

    try:
        with tempfile.TemporaryDirectory(prefix="photocheck-권한 검증-") as folder:
            root = Path(folder)
            denied_image = root / "읽기차단.jpg"
            allowed_image = root / "읽기가능.jpg"
            shutil.copyfile(image_path, denied_image)
            shutil.copyfile(image_path, allowed_image)
            denied_folder = root / "접근차단폴더"
            denied_folder.mkdir()
            (denied_folder / "child.jpg").write_bytes(b"test")
            blocked_output = root / "저장차단폴더"
            blocked_output.mkdir()
            saved = root / "읽기전용.xlsx"
            saved.write_bytes(b"existing excel must remain unchanged")
            try:
                acl(denied_image, "/deny", ":(RD)")
                acl_paths.append(denied_image)
                failed = inspect(denied_image, root)
                report["checks"]["unreadable_file_is_error"] = failed.status == Status.ERROR and failed.direction_check == Check.SKIP
                acl(denied_folder, "/deny", ":(RD)")
                acl_paths.append(denied_folder)
                collection = collect(root, True)
                report["checks"]["unreadable_subfolder_reported"] = bool(collection.issues)
                acl(blocked_output, "/deny", ":(W)")
                acl_paths.append(blocked_output)
                row = Result(allowed_image, allowed_image.name)
                try:
                    export_excel(blocked_output / "denied.xlsx", [row])
                    report["checks"]["unwritable_export_rejected"] = False
                except PermissionError:
                    report["checks"]["unwritable_export_rejected"] = True
                copied = copy_photos([row],blocked_output)
                report['checks']['unwritable_photo_copy_reported'] = copied.copied == 0 and len(copied.errors) == 1
                denied_copy_folder = root/'읽기 불가 사본'
                denied_copy_folder.mkdir()
                denied_copy = copy_photos([Result(denied_image,denied_image.name)],denied_copy_folder)
                report['checks']['unreadable_photo_copy_reported'] = denied_copy.copied == 0 and len(denied_copy.errors) == 1
                try:
                    save_criteria(Criteria(), blocked_output / "settings.json")
                    report["checks"]["unwritable_settings_rejected"] = False
                except PermissionError:
                    report["checks"]["unwritable_settings_rejected"] = True
                preferences = root / "사용자 설정.json"
                save_criteria(Criteria(), preferences)
                report["checks"]["writable_settings_roundtrip"] = load_criteria(preferences) == (Criteria(), "")
                preferences.chmod(0o444)
                previous_settings = preferences.read_bytes()
                try:
                    save_criteria(replace(Criteria(),roll_degrees=8), preferences)
                    report["checks"]["readonly_settings_preserved"] = False
                except PermissionError:
                    report["checks"]["readonly_settings_preserved"] = preferences.read_bytes() == previous_settings
                finally:
                    preferences.chmod(0o666)
                saved.chmod(0o444)
                before = saved.read_bytes()
                try:
                    export_excel(saved, [row])
                    report["checks"]["readonly_excel_preserved"] = False
                except PermissionError:
                    report["checks"]["readonly_excel_preserved"] = saved.read_bytes() == before
                finally:
                    saved.chmod(0o666)
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                              ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
                kernel.CreateFileW.restype = wintypes.HANDLE
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel.CreateFileW(str(saved), 0x80000000, 0, None, 3, 0, None)
                if handle == ctypes.c_void_p(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    try:
                        export_excel(saved, [row])
                        report["checks"]["locked_excel_rejected"] = False
                    except PermissionError as error:
                        report["checks"]["locked_excel_rejected"] = True
                finally:
                    kernel.CloseHandle(handle)
                analyzer = ProcessAnalyzer()
                try:
                    before = hashlib.sha256(allowed_image.read_bytes()).hexdigest()
                    result = inspect(allowed_image, root, analyzer)
                    report["checks"]["analysis_without_admin"] = not report["is_admin"] and result.model_version != "unavailable" and not any("분석 실패" in s for s in result.reasons)
                    report["checks"]["original_preserved"] = hashlib.sha256(allowed_image.read_bytes()).hexdigest() == before
                finally:
                    analyzer.close()
                good_excel = root / "결과.xlsx"
                export_excel(good_excel, [result])
                report["checks"]["writable_export_succeeds"] = good_excel.stat().st_size > 0
                copy_folder = root/'사진 사본'
                copy_folder.mkdir()
                source_before = allowed_image.read_bytes()
                copied = copy_photos([row],copy_folder)
                report['checks']['photo_copy_original_preserved'] = (copied.copied == 1 and
                    (copy_folder/allowed_image.name).read_bytes() == source_before and allowed_image.read_bytes() == source_before)
                copied = copy_photos([row],copy_folder)
                report['checks']['existing_photo_copy_preserved'] = (copied.copied == 0 and len(copied.skipped) == 1
                    and (copy_folder/allowed_image.name).read_bytes() == source_before)
                report["checks"]["no_orphan_export_temporary"] = not list(root.rglob(".photocheck-*.tmp"))
                report["checks"]["no_orphan_settings_temporary"] = not list(root.rglob(".settings-*.tmp"))
                report["ok"] = all(report["checks"].values())
            finally:
                for target in reversed(acl_paths):
                    acl(target, "/remove:d")
    except Exception as error:
        import traceback
        report.update(error=str(error), traceback=traceback.format_exc())
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if sys.stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1
