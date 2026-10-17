# MelodyExtractor: A Deep-Learning-Based Main-Melody Extractor for Piezoelectric Buzzers

一个完全本地运行的 Windows 桌面应用：从歌曲中提取**主旋律**，导出单音 MIDI
和紧凑的「频率 / 音长」TXT 文件。

[English](README.md) | 简体中文

![主旋律提取器界面](docs/screenshots/gui.png)

> **状态：** 桌面应用 v1.0.0。本仓库包含推理应用和打包脚本；模型权重和 Windows
> 安装包作为 Release 附件分发；训练流程和数据集不在本仓库中。

## 为什么需要这个模型

无源压电蜂鸣器只有一个振膜、由一路激励信号驱动，因此同一时刻只能发出一个音；
而且激励频率跳变时，振膜会产生机械瞬态并余振，听感上就是噪声。要让这种蜂鸣器
演奏出可用的旋律，就必须先从复调音频中提取稳定的单声部主旋律——这项工作传统上
依赖人工听记，成本高且难以规模化。

现有的自动方法各有不足：YIN、CREPE 等单音音高估计器，以及 Essentia 的 Melodia
主旋律算法，在单声部输入上表现良好，但在复调环境下逐帧音高估计会在多个同时发声
的声部之间跳动，置信度持续偏低；加入平滑、连续性等后处理约束只能带来有限改善。
基于 Viterbi 解码与 CNN 的复调旋律方法，大多建立在手工音高显著性特征之上，且
只建模局部时序上下文，难以捕捉旋律的长程结构，也无法从根本上解决跨声部干扰。

在此背景下，针对对齐的复调主旋律数据稀缺的问题，我们收集并构建了来自《三角洲
行动》口琴社区的对齐数据集，并提出 MelodyExtractor：用 MERT 预训练编码器提取
音乐表征，用双向 GRU 建模时序上下文，并以和弦检测作为辅助任务提供和声上下文，
与主旋律预测构成联合多任务监督，在对齐数据上端到端训练。推理阶段不做 Viterbi/
HMM 平滑，稳定的单声部输出依赖模型自身的时序建模；仅用轻量的音符切分（中值
滤波、补 gap、最短音符长度）把逐帧判决变成音符。

> **备注：** 本项目为实验性质，数据集规模较小，对部分歌曲效果欠佳；输出更适合作为
> 转谱起点，而非最终成品。

## 功能

- **完全本地**：音频不离开本机，运行时不联网、不需要账号或 API Key。
- **GPU / CPU 自动选择**：有 DirectX 12 GPU 时使用 ONNX Runtime DirectML，
  否则自动回退 CPU；不需要安装 CUDA。
- **可选人声分离**：htdemucs 生成 `vocals + other` 旋律床；可关闭以加快速度。
- **试听**：合成旋律试听，调整频率倍率后实时变调。
- **频率倍率**：滑杆 0.25×–4×，输入框支持 0.1×–10×；作用于 TXT 频率和 MIDI
  音高（MIDI 四舍五入到最近半音）。
- **固定格式导出**：单音 MIDI；TXT 每行 5 组、整数 Hz、整数毫秒、静音显式写出、
  时间轴连续。
- **可复现的分离**：htdemucs 的随机偏移种子已固定，同一台机器重复运行结果一致。

## 环境要求

- Windows 10/11 x64
- Microsoft Edge WebView2 Runtime（安装包会检测并引导到微软官方下载页；
  Windows 11 通常已自带）
- 从源码运行需要 Python 3.12 x64
- 约 1 GB 可用磁盘空间（两个模型文件）
- 建议 8 GB 内存；DirectX 12 GPU 可选，但推荐

## 安装

### Windows 安装包

从 [Releases](../../releases) 下载 `MelodyExtractor_Setup_v1.0.0.exe`，运行后选择
安装目录，可勾选创建桌面快捷方式；安装程序会注册卸载入口。

### 从源码运行

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
python scripts/download_models.py
python main.py
```

如果 `download_models.py` 找不到 Release 附件，请按
[models/README.md](models/README.md) 手动放置模型。无界面端到端自检
（合成音频 → demucs → ONNX → TXT/MIDI）：

```bat
python main.py --selftest
```

## 模型文件

权重不进入 git：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `models/melody_mert95.onnx` | 381 MiB | `cea1a8418f8c5e1e0b38335ad7b9a0c05dcdb0da7efd613a47983feb89d887ea` |
| `models/demucs/955717e8-8726e21a.th` | 80 MiB | `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4` |

`models/demucs/htdemucs.yaml` 已包含在仓库中。下载脚本会在有 GitHub `origin`
的克隆里读取最新 Release，校验两个文件的 SHA-256；htdemucs 权重找不到 Release
附件时会回退到 Meta 官方地址。

## 工作原理

1. **解码**：PyAV/FFmpeg 解码为 44.1 kHz 立体声（需要分离时）或 24 kHz 单声道。
2. **分离**：htdemucs 取 `vocals + other` 作为旋律床；固定随机种子保证可复现。
3. **推理**：旋律床重采样到 24 kHz，整曲 z-normalize，按 163,840 样本一块、
   163,520 样本步长送入 ONNX。模型在 75 Hz 帧率上输出 60 个音高类
   （MIDI 36–95）加一个静音类。
4. **事件**：argmax → 5 帧中值滤波 → 合并同音高且间隔 ≤50 ms 的片段 →
   丢弃短于 60 ms 的音符；结果天然是单音的。
5. **导出**：MIDI、TXT 和合成试听。

ONNX 图契约：

| | |
| --- | --- |
| 输入 | `wav` float32 `(1, T)`，24 kHz，z-normalize，`T >= 400` |
| 输出 | `melody_logits` float32 `(1, F, 61)`，`F = (T - 400) // 320 + 1` |
| 类别 | 0–59 → MIDI 36–95，60 → 静音 |
| 帧 hop | 1/75 s |

导出图在整曲上与 PyTorch 做过对齐；测试机上 DirectML 和 CPU 两个执行提供器的
帧级 argmax 一致率均为 100%。

## TXT 格式

每组为 `{频率Hz, 音长ms}`：频率取整为整数 Hz，音长取整为整数毫秒。每行 5 组，
组内用「逗号 + 空格」，组间用逗号，**每行行尾保留逗号**。静音写成
`{0, 音长}`；时间轴连续并覆盖处理时长。文件为 UTF-8 无 BOM、LF 换行、末尾有
换行；最后一行可以少于 5 组。

```text
{262, 480}, {330, 240}, {0, 120}, {392, 960}, {440, 120},
{494, 360}, {523, 240}, {0, 600}, {587, 480}, {659, 240},
```

MIDI 导出会应用频率倍率并四舍五入到最近半音；TXT 保留倍率后的精确频率并取整为
Hz。两者来自同一组音符事件。

## 构建

安装 [Inno Setup 6.7.3](https://jrsoftware.org/isdl.php)，然后：

```bat
pip install -r requirements-build.txt
python scripts/download_models.py
pyinstaller pack/melody_extractor.spec --noconfirm --clean ^
  --distpath pack/dist --workpath pack/build
cd pack
iscc installer.iss
```

PyInstaller 产物在 `pack/dist/MelodyExtractor/`，安装包在
`pack/installer/MelodyExtractor_Setup_v1.0.0.exe`。spec 会打包应用、WebUI、
ONNX 模型、htdemucs 权重和运行时库；Inno Setup 负责快捷方式、卸载器和
WebView2 检测。

`pack/ChineseSimplified.isl` 来自 Inno Setup 源码树，再分发时请保留其文件头。

## 仓库结构

```text
app/                 管线、ORT 会话、解码、导出、HTTP 服务、JS 桥
webui/               WebView2 加载的 HTML/CSS/JS 界面
main.py              桌面入口与 --selftest
pack/                PyInstaller spec、图标生成、Inno Setup 脚本
scripts/             模型下载与校验
models/              模型放置说明（权重被 git 忽略）
docs/screenshots/    界面截图
```

## 许可证

- **源代码**：MIT，见 [LICENSE](LICENSE)。
- **模型权重**：CC BY-NC 4.0，**禁止商用**，见
  [LICENSE-MODEL.md](LICENSE-MODEL.md)。
- **第三方组件**：见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

非商用限制来自 MERT-v1-95M 骨干（CC BY-NC 4.0）以及使用 MIR-1K（仅限研究用途）
进行微调。仓库不包含任何 MIR-1K 音频/标签，也不包含用户音频或标注。如需商用，
请更换可商用的骨干和训练数据并重新训练。

## 致谢

- [MERT](https://huggingface.co/m-a-p/MERT-v1-95M) — 音乐表征骨干
- [Demucs](https://github.com/facebookresearch/demucs) — 音源分离
- [ONNX Runtime](https://onnxruntime.ai/) / [DirectML](https://learn.microsoft.com/windows/ai/directml/) — 本地推理
- [PyAV](https://pyav.org/) / FFmpeg — 解码
- [pywebview](https://pywebview.flowrl.com/) — 原生窗口与桥接
- [pretty_midi](https://github.com/craffel/pretty-midi) — MIDI 写入
- [Inno Setup](https://jrsoftware.org/isinfo.php) — 安装包

## 限制

- 只提取一条主旋律，不是完整转谱；复杂混音可能让模型跟随伴奏或内声部。
- 可能存在八度错误和音符边界错误；这是研究原型，不是专业转谱工具。
- demucs 只用 CPU（典型台式机 CPU 上大约实时）；DirectML 只加速旋律模型，
  不加速分离。
- 仅支持 Windows；当前界面为中文。
- 首次加载模型和首次推理会比后续运行慢。
