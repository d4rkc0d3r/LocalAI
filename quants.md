# 4-Bit Quantization Formats in llama.cpp

## Comparison Overview

| Format | Block Size | Values/Block | bpw | Value Grid | Sub-blocks | Has Offset | Scale Granularity |
|---|---|---|---|---|---|---|---|
| **Q4_0** | 18 bytes | 32 | 4.50 | Linear {−8..7} | 1 | No | Per-block |
| **Q4_1** | 20 bytes | 32 | 5.00 | Linear {0..15} | 1 | Yes (fp16) | Per-block |
| **IQ4_NL** | 18 bytes | 32 | 4.50 | Non-linear 16-val | 1 | No | Per-block |
| **IQ4_XS** | 136 bytes | 256 | 4.25 | Non-linear 16-val | 8 (×32) | No | Per sub-block (6-bit) |
| **Q4_K** | 144 bytes | 256 | 4.50 | Linear {0..15} | 8 (×32) | Yes (6-bit) | Per sub-block (6-bit) |

## Key Differences

### Q4_0 — Centered Linear 4-Bit
- Simplest format. Single scale `d` per 32-value block.
- Stored indices {0..15} map to {-8..7} by subtracting 8.
- Scale derived from absolute maximum: `d = max / -8`.
- **Limitation**: Symmetric grid wastes half the range on skewed distributions.

### Q4_1 — Bounded Linear 4-Bit (with Min/Offset)
- Adds an fp16 min value `m` per block.
- Full range {0..15} maps to [min, max] with uniform spacing: `d = (max - min) / 15`.
- Dequantize: `x = d * q + m`.
- **Trade-off**: Extra 16 bits per block pushes to 5.0 bpw, but eliminates wasted range.

### IQ4_NL — Non-Linear 4-Bit
- Same structure as Q4_0, but replaces the linear grid with a non-linear lookup table:
  `{-127, -104, -83, -65, -49, -35, -22, -10, 1, 13, 25, 38, 53, 69, 89, 113}`
- Finer spacing near zero, coarser for large values — matches typical weight distributions.
- No offset needed; the asymmetric grid handles skewed data natively.

### IQ4_XS — Extra-Small Non-Linear 4-Bit
- 256-value super-blocks with 8 sub-blocks of 32, each with its own 6-bit scale.
- Uses the same non-linear grid as IQ4_NL.
- Global fp16 scale `d` + 8 quantized sub-block scales (packed in 2 bytes: 4 low bits + 2 high bits each).
- No offset — the non-linear grid replaces the need for a min.
- Smallest at 4.25 bpw while maintaining quality close to Q4_K.

### Q4_K — K-Quant 4-Bit
- 256-value super-blocks with 8 sub-blocks of 32, each with its own 6-bit scale **and** 6-bit min.
- Two global fp16 parameters: `d` (scale for scales) and `dmin` (scale for mins).
- Dequantize: `x = d * sc * q - dmin * m` per sub-block.
- Per-sub-block offset handles asymmetric distributions without wasting range.
- Best quality at ~4.5 bpw, but larger than IQ4_XS.

## Evolution

1. **Q4_0 / Q4_1** — Original simple formats. Small 32-value blocks, single scale (and optionally min).
2. **Q4_K** — Larger 256-value super-blocks with per-sub-block scales and mins. Reduces metadata overhead and adapts to local variation.
3. **IQ4_NL / IQ4_XS** — Replaces per-sub-block mins with a non-linear value grid. The asymmetric grid handles skewed distributions without an offset, saving space while maintaining quality.
