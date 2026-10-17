# Model weights license

The model weights distributed with this project — `models/melody_mert95.onnx`
and any converted copies — are licensed under the
[Creative Commons Attribution-NonCommercial 4.0 International License
(CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/legalcode).

You may share and adapt the weights for non-commercial purposes, provided you
give appropriate credit and indicate changes. You may not use them for
commercial purposes.

## Why non-commercial

- The acoustic backbone is **MERT-v1-95M** by the m-a-p team, whose model card
  is published under CC BY-NC 4.0.
- The melody model was fine-tuned on **MIR-1K**, a dataset provided for
  research use only. No MIR-1K audio or labels are redistributed in this
  repository.

## Attribution

- MERT-v1-95M: https://huggingface.co/m-a-p/MERT-v1-95M
- MIR-1K: https://zenodo.org/records/3532216
- The ONNX export and the BiGRU melody head were produced for this project.

The Python source code in this repository is licensed separately under the MIT
License (see `LICENSE`). If you need commercial rights to a melody model, use a
backbone and training data that permit commercial use and retrain the model.
