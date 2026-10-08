"""Copy a selected snapshot without overwriting sources or destination files."""
from dataclasses import dataclass, field
from pathlib import Path

from .domain import Status


@dataclass
class CopyReport:
    copied: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


def copy_photos(results, destination, cancelled=lambda:False, progress=lambda *a:None):
    report = CopyReport()
    try:
        destination = Path(destination).resolve(strict=True)
        if not destination.is_dir():
            raise ValueError("복사할 폴더를 선택하세요.")
    except (OSError,ValueError) as error:
        report.errors.append(f'복사 폴더 접근 실패: {error}')
        return report
    rows = [r for r in results if r.status != Status.NORMAL]
    for index, result in enumerate(rows, 1):
        if cancelled():
            report.cancelled = True
            break
        relative = Path(result.relative_path)
        target, created = None, False
        try:
            if relative.is_absolute() or '..' in relative.parts or not relative.name:
                raise ValueError("사진의 상대 경로가 유효하지 않습니다.")
            target = (destination/relative).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("복사할 파일 경로가 선택한 폴더 밖을 가리킵니다.")
            if target == result.path.resolve():
                report.skipped.append(f'{relative}: 원본과 같은 경로')
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with result.path.open('rb') as source:
                try:
                    output = target.open('xb')
                except FileExistsError:
                    report.skipped.append(f'{relative}: 같은 경로에 파일이 이미 있음')
                    continue
                created = True
                with output:
                    while True:
                        if cancelled():
                            report.cancelled = True
                            break
                        chunk = source.read(1024*1024)
                        if not chunk:
                            break
                        output.write(chunk)
                    output.flush()
                if report.cancelled:
                    target.unlink()
                    break
            report.copied += 1
        except (OSError,ValueError) as error:
            if created and target is not None:
                try:
                    target.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    report.errors.append(f'{relative}: 미완성 사본 삭제 실패 — {cleanup_error}')
            report.errors.append(f'{relative}: {error}')
        finally:
            progress(index, len(rows))
    return report
