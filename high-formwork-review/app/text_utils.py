"""文本归一化工具。

集中管理 NFKC 归一化、全半角替换、LaTeX 残片归一、空白压缩等共享文本处理。
"""

from __future__ import annotations

import re
import unicodedata


def norm(text: str) -> str:
    """归一化文本：NFKC + 全半角替换 + 空白压缩（返回无空白紧凑串）。

    用法：
        文本比对（容错全/半角/不间断空白）
        中文文本窗口截取
    """
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("（", "(").replace("）", ")").replace("＝", "=")
    text = text.replace("\\leq", "≤").replace("\\geq", "≥")
    text = text.replace("\\le", "≤").replace("\\ge", "≥")
    text = text.replace("\\quad", " ").replace("\\,", " ").replace("\\;", " ")
    return re.sub(r"\s+", "", text)


def normalize_symbol_text(text: str) -> str:
    """归一化 LaTeX 数学符号：\\gamma_c → γc, \\beta1 → β1。

    用 \\b 边界避免误吃 \\betac/\\gamma1 等伪词。
    """
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"\\gamma[_]?c\b", "γc", text, flags=re.IGNORECASE)
    text = re.sub(r"\\gamma[_]?0?\b", "γ0", text, flags=re.IGNORECASE)
    text = re.sub(r"\\beta(?![\w])", "β", text, flags=re.IGNORECASE)
    text = re.sub(r"\\beta[_]?([12])\b", r"β\1", text, flags=re.IGNORECASE)
    text = text.replace("＝", "=").replace("：", ":")
    return text
