from __future__ import annotations

import os


if os.getenv("FLOWSTUDIO_TORCH_LOAD_WEIGHTS_ONLY_FALSE", "0") == "1":
    import torch

    _torch_load = torch.load

    def _flowstudio_torch_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return _torch_load(*args, **kwargs)

    torch.load = _flowstudio_torch_load
