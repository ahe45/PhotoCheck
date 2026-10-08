"""Build-time only. The shipped application never downloads models."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
import yaml  # Build-time only; excluded from the executable.

ROOT = Path(__file__).resolve().parent.parent
MODELS = {
    "blaze_face_short_range.tflite": "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    "ppocrv3_det.onnx": "https://media.githubusercontent.com/media/opencv/opencv_zoo/47534e27c9851bb1128ccc0102f1145e27f23f98/models/text_detection_ppocr/text_detection_cn_ppocrv3_2023may.onnx",
    "korean_ppocrv5_rec.onnx": "https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec_onnx/resolve/5c6f574b8e2230adf4287b33e736d71b9fabd28e/inference.onnx",
}


def main():
    folder = ROOT / "models"
    folder.mkdir(exist_ok=True)
    manifest_path = folder / "manifest.json"
    old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    expected = {m["filename"]: m["sha256"] for m in old["models"]} if old else {}
    expected["ppocrv3_det.onnx"] = "03f550c6b406fda8bf54bd8327815f6c7e2edd98cea02348c93d879254366587"
    expected['korean_ppocrv5_rec.onnx'] = '92f0b7785e64fc9090106a241cf4c1eb97472824558272751b88a2a4476d3a08'
    entries = []
    for filename, url in MODELS.items():
        target = folder / filename
        if target.exists():
            data = target.read_bytes()
        else:
            with urlopen(url, timeout=120) as response:
                data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if filename in expected and digest != expected[filename]:
            raise RuntimeError(f"Model hash mismatch: {filename}")
        if not target.exists():
            target.write_bytes(data)
        entries.append({"filename": filename, "sha256": digest, "url": url, "bytes": len(data)})
        print(filename, len(data), digest)
    dictionary_url = 'https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec_onnx/resolve/5c6f574b8e2230adf4287b33e736d71b9fabd28e/inference.yml'
    dictionary_path = folder/'korean_rec_dict.json'
    if dictionary_path.exists():
        dictionary = dictionary_path.read_bytes()
    else:
        with urlopen(dictionary_url, timeout=120) as response:
            source = response.read()
        if hashlib.sha256(source).hexdigest() != 'f757fa1c40e99edcf27e9cce879b93eb2a51fa46f5ef39095689b8c37dd75998':
            raise RuntimeError('Recognition dictionary source hash mismatch')
        characters = yaml.safe_load(source)['PostProcess']['character_dict']
        dictionary = (json.dumps(characters, ensure_ascii=False, separators=(',', ':'))+'\n').encode('utf-8')
    digest = hashlib.sha256(dictionary).hexdigest()
    if digest != '8c89748b14e07b3332eb3fa569cf39eb78dbfc7ed2fe0f333f19f9574e94c6f3':
        raise RuntimeError('Recognition dictionary hash mismatch')
    dictionary_path.write_bytes(dictionary)
    entries.append({'filename': dictionary_path.name, 'sha256': digest, 'url': dictionary_url, 'bytes': len(dictionary)})
    manifest_path.write_text(json.dumps({"version": "google-float16-v1+ppocrv3-det+korean-ppocrv5-rec", "models": entries}, indent=2), encoding="utf-8")
    licenses = ROOT / "licenses"
    licenses.mkdir(exist_ok=True)
    license_path = licenses / "MediaPipe-Apache-2.0.txt"
    if not license_path.exists():
        with urlopen("https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/LICENSE", timeout=60) as response:
            license_path.write_bytes(response.read())
    text_license = licenses / "PaddleOCR-Apache-2.0.txt"
    with urlopen("https://raw.githubusercontent.com/opencv/opencv_zoo/47534e27c9851bb1128ccc0102f1145e27f23f98/models/text_detection_ppocr/LICENSE", timeout=60) as response:
        text_license.write_bytes(response.read())
    (licenses / "PaddleOCR-model-NOTICE.txt").write_text(
        "PP-OCRv3 text detection (detection only)\nCopyright (c) 2016 PaddlePaddle Authors. Apache License 2.0.\n"
        "https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/text_detection_ppocr\n"
        "Source weights: text_detection_cn_ppocrv3_2023may.onnx\n"
        "SHA256 03f550c6b406fda8bf54bd8327815f6c7e2edd98cea02348c93d879254366587\n"
        "Korean PP-OCRv5 mobile recognition and its character dictionary (Apache 2.0)\n"
        "https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec_onnx/tree/5c6f574b8e2230adf4287b33e736d71b9fabd28e\n"
        "Recognition SHA256 92f0b7785e64fc9090106a241cf4c1eb97472824558272751b88a2a4476d3a08\n"
        "Dictionary source inference.yml SHA256 f757fa1c40e99edcf27e9cce879b93eb2a51fa46f5ef39095689b8c37dd75998\n"
        "Dictionary reformatted as UTF-8 JSON; recognition is used only to count consecutive characters.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
