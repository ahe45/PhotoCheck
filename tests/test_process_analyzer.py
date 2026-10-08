import os

from PIL import Image
import pytest

from photocheck.domain import Check, Result, Status
from photocheck.files import inspect
from photocheck.process_analyzer import ProcessAnalyzer


def simulated_engine(connection):
    connection.send(("ready", "simulated"))
    while True:
        request = connection.recv()
        if request is None:
            break
        _, _, result = request
        if "crash" in result.relative_path:
            os._exit(7)
        if "timeout" in result.relative_path:
            import time
            time.sleep(30)
        result.direction_check = result.framing_check = Check.PASS
        connection.send(("result", result))


@pytest.mark.parametrize("failure", ["crash", "timeout"])
def test_native_failure_and_timeout_recover_next_file(tmp_path, failure):
    for name in (f"{failure}.png", "next.png"):
        Image.new("RGB", (300, 400)).save(tmp_path / name)
    analyzer = ProcessAnalyzer(timeout=2, _target=simulated_engine)
    try:
        failed = inspect(tmp_path / f"{failure}.png", tmp_path, analyzer)
        assert failed.status == Status.REVIEW
        assert failed.direction_check == failed.framing_check == Check.REVIEW
        recovered = inspect(tmp_path / "next.png", tmp_path, analyzer)
        assert recovered.status == Status.NORMAL
    finally:
        analyzer.close()
    assert analyzer.process is None

