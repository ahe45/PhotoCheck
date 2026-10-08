from importlib.metadata import distributions
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent.parent / "licenses" / "dependency-licenses"
root.mkdir(parents=True, exist_ok=True)
for package in distributions():
    for entry in package.files or []:
        if any(token in str(entry).lower() for token in ("license", "copying", "notice")) and ".dist-info" in str(entry):
            source = Path(package.locate_file(entry))
            if source.is_file():
                parts = Path(str(entry)).parts
                marker = next(i for i, part in enumerate(parts) if part.endswith(".dist-info"))
                target = root / package.metadata["Name"] / Path(*parts[marker + 1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
