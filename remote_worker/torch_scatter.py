from __future__ import annotations

import torch


def _expanded_index(index: torch.Tensor, src: torch.Tensor, dim: int) -> torch.Tensor:
    if dim < 0:
        dim += src.dim()
    while index.dim() < src.dim():
        index = index.expand(*src.shape[: index.dim()], *([1] * (src.dim() - index.dim())))
    shape = list(src.shape)
    shape[dim] = index.shape[dim]
    return index.expand_as(src)


def _output(src: torch.Tensor, index: torch.Tensor, dim: int, out: torch.Tensor | None, dim_size: int | None) -> torch.Tensor:
    if dim < 0:
        dim += src.dim()
    if out is not None:
        return out
    size = list(src.shape)
    size[dim] = int(dim_size or (index.max().item() + 1 if index.numel() else 0))
    return src.new_zeros(size)


def scatter_mean(
    src: torch.Tensor,
    index: torch.Tensor,
    dim: int = -1,
    out: torch.Tensor | None = None,
    dim_size: int | None = None,
) -> torch.Tensor:
    if dim < 0:
        dim += src.dim()
    expanded = _expanded_index(index.long(), src, dim)
    result = _output(src, expanded, dim, out, dim_size)
    result.zero_()
    result.scatter_add_(dim, expanded, src)
    counts = torch.zeros_like(result)
    counts.scatter_add_(dim, expanded, torch.ones_like(src))
    return result / counts.clamp_min(1)


def scatter_max(
    src: torch.Tensor,
    index: torch.Tensor,
    dim: int = -1,
    out: torch.Tensor | None = None,
    dim_size: int | None = None,
) -> tuple[torch.Tensor, torch.Tensor]:
    if dim < 0:
        dim += src.dim()
    expanded = _expanded_index(index.long(), src, dim)
    result = _output(src, expanded, dim, out, dim_size)
    result.fill_(-torch.inf)
    result.scatter_reduce_(dim, expanded, src, reduce="amax", include_self=True)
    result = torch.where(torch.isinf(result), torch.zeros_like(result), result)
    argmax = torch.full_like(result, -1, dtype=torch.long)
    return result, argmax
