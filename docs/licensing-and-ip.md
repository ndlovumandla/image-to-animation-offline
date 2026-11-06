# Intellectual Property & Open-Source Licensing Audit (`docs/licensing-and-ip.md`)

## 1. Upstream Repository Licence

- **Upstream Source**: `https://github.com/daslearning-org/image-to-animation-offline`
- **Licence**: **MIT License** (`Copyright (c) 2025 daslearning.in`)
- **Permitted Uses**: Commercial use, modification, distribution, and private/public deployment are **explicitly permitted**, provided the [`LICENSE`](../LICENSE) file and copyright notice are retained in all copies or substantial portions of the software.

---

## 2. Production Dependency & AI Model Licence Inventory

| Component | Package / Asset | Licence | Commercial Deployment Permitted? |
|---|---|---|---|
| Frontend Framework | `react`, `react-dom`, `zustand`, `immer`, `idb`, `mp4-muxer` | MIT / ISC | Yes |
| Canvas Engine | `fabric` (`^7.4.0`) | MIT | Yes |
| Project Archive | `jszip` (`3.10.2`) | MIT or GPLv3 (Dual-licensed; elected under **MIT**) | Yes |
| Backend API | `fastapi`, `uvicorn`, `Pillow`, `python-multipart` | MIT / BSD-3-Clause / Apache-2.0 / HPND | Yes |
| Image Processing | `opencv-python-headless` | Apache-2.0 | Yes |
| AI Segmentation | `rembg` + `onnxruntime` + **U²-Net (`u2net.onnx`)** | MIT (`rembg`, `onnxruntime`) + **Apache-2.0** (U²-Net weights by Xuebin Qin et al.) | Yes |
| Infrastructure | Caddy 2, Portainer CE 2.27.1, Cloudflared | Apache-2.0 / Zlib | Yes |

> [!NOTE]
> `ffprobe-static` (which bundles an LGPL/GPL `ffprobe` binary) is used exclusively in `devDependencies` for local test verification and is excluded from the production build (`/srv`) and runtime containers.
