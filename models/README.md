# Model files

The repository does not contain model weights. Put the two files below in
place, or run `python scripts/download_models.py`.

| File | Size | SHA-256 |
| --- | ---: | --- |
| `models/melody_mert95.onnx` | 399,157,368 bytes (381 MiB) | `cea1a8418f8c5e1e0b38335ad7b9a0c05dcdb0da7efd613a47983feb89d887ea` |
| `models/demucs/955717e8-8726e21a.th` | 84,141,911 bytes (80 MiB) | `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4` |

`models/demucs/htdemucs.yaml` is part of the repository (demucs bag file).

The ONNX file is attached to the project's GitHub Releases. The download
script reads the latest release when the clone has a GitHub `origin`; you can
also pass an explicit URL:

```bash
python scripts/download_models.py --onnx-url https://example.com/melody_mert95.onnx
```

The htdemucs checkpoint can be fetched from the official Meta URL by the same
script if no release asset is found.

## License

The ONNX weights are **CC BY-NC 4.0** (non-commercial) because they derive from
MERT-v1-95M (CC BY-NC 4.0) and were fine-tuned on MIR-1K (research use only).
See `LICENSE-MODEL.md`. The demucs checkpoint is MIT-licensed. No MIR-1K audio
or labels are included in this repository.
