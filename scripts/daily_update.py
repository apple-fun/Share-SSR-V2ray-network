#!/usr/bin/env python3
"""
KC云加速（学术 / 开发向仓库）每日 README 自动更新

流程：
  1. 调用 speed_test.py 生成当日节点数据 -> data/*.csv
  2. 在 README 的「## 📅 第五部分」之前插入当日更新块
  3. 在第五部分下方写入/更新当日维护日志条目
  4. 顺带清理历史遗留的重复条目与多余空行

设计要点：
  - 幂等：同一天重复运行只覆盖当天内容，不重复堆叠
  - 每日不同：内容按日期做随机种子，跨天组合不重复
  - 保留原文件换行风格（CRLF / LF）
"""

import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
README_PATH = os.path.join(ROOT, "README.md")

MARKER = "## 📅 第五部分：维护日志与版本迭代记录"

sys.path.insert(0, HERE)
import speed_test  # noqa: E402

TIPS = [
    "💡 **协议小课堂**：VLESS Reality 具备防主动探测特性，在校园网、公司网等严格环境下存活率明显优于传统 VMess。",
    "💡 **客户端推荐**：Clash Verge Rev（Windows / macOS）与 Mihomo Party 均已支持 Meta 内核，一键导入订阅即可使用。",
    "💡 **检索提示**：访问 IEEE Xplore、ScienceDirect 时若频繁弹人机验证，说明当前出口 IP 纯净度不足，建议切至原生住宅 IP 专线。",
    "💡 **开发环境**：开启 Tun 模式接管全局流量后，`git clone`、`docker pull`、`pip install` 走国际线路，可显著减少中断。",
    "💡 **移动端技巧**：Android 端开启 Mux 多路复用后，地铁、电梯等弱网环境下断流重连速度提升明显。",
    "💡 **流媒体提示**：观看 Netflix、Disney+ 建议使用专属流媒体分组，避免与下载流量互相抢占带宽。",
    "💡 **分流建议**：将常用学术域名写入 DOMAIN-SUFFIX 规则走专线，其余国内流量保持 DIRECT，兼顾速度与日常体验。",
    "💡 **网络常识**：晚高峰（20:00–23:00）国际出口普遍拥堵，BGP 专线入口在这个时段优势最明显。",
    "💡 **文档效率**：Google Scholar 批量导出 BibTeX 时容易触发限流，固定出口 IP 可明显减少重复验证。",
]

BENEFITS = [
    "🎁 **新人福利**：通过专属通道注册即可领取试用时长，加群还有额外优惠，详见下方试用说明。",
    "🎁 **性价比**：入门套餐低至 ¥18/月，适合以学术检索、文献下载为主的轻度用户。",
    "🎁 **长期建议**：年付套餐折算每月成本最低，适合长期做科研、跨境开发的同学。",
]


def split_at_marker(text):
    idx = text.find(MARKER)
    if idx == -1:
        raise SystemExit("❌ README 中未找到标记：" + MARKER)
    return text[:idx], text[idx:]


def strip_today(text, today):
    """移除今天已存在的更新块与日志条目，保证幂等。"""
    heading = f"### 📌 {today} 今日更新"
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == heading:
            i += 1
            while i < len(lines) and (lines[i].strip() == "" or lines[i].lstrip().startswith("- ")):
                i += 1
            continue
        if line.startswith(f"{today}："):
            i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def cleanup(text):
    """清理历史遗留的重复条目与多余空行（不改变任何有效内容）。"""
    # 1) 重复的「日期 | 测速摘要 + 提示」组合块
    pat = re.compile(r'(\d{4}-\d{2}-\d{2}) \| \d+ nodes tested \| Best latency: \d+ms\n\n([^\n]+)')
    seen = set()

    def _dedupe(m):
        key = (m.group(1), m.group(2).strip())
        if key in seen:
            return "\x00"
        seen.add(key)
        return m.group(0)

    text = pat.sub(_dedupe, text)
    text = re.sub(r'\x00+(\n+)?', '', text)

    # 2) 重复的维护日志行
    seen_log, out = set(), []
    for line in text.split("\n"):
        if re.match(r'^\d{4}-\d{2}-\d{2}：', line):
            if line.strip() in seen_log:
                continue
            seen_log.add(line.strip())
        out.append(line)
    text = "\n".join(out)

    # 3) 压缩连续空行
    return re.sub(r'\n{3,}', '\n\n', text)


def trim_blocks(text, keep=7):
    """只保留最近 keep 个「今日更新」块，避免 README 无限膨胀（历史仍留在维护日志里）。"""
    lines = text.split("\n")
    starts = [i for i, l in enumerate(lines)
              if re.match(r'^### 📌 \d{4}-\d{2}-\d{2} 今日更新$', l.strip())]
    if len(starts) <= keep:
        return text

    ranges = []
    for s in starts:
        e = s + 1
        while e < len(lines) and (lines[e].strip() == "" or lines[e].lstrip().startswith("- ")):
            e += 1
        while e < len(lines) and lines[e].strip() == "":
            e += 1
        ranges.append((s, e))

    remove = set()
    for s, e in ranges[:-keep]:
        remove.update(range(s, e))
    return "\n".join(l for i, l in enumerate(lines) if i not in remove)


def main():
    from datetime import datetime, timedelta, timezone
    # 固定按北京时间取日期：GitHub Actions 运行器是 UTC，
    # 定时任务常被推迟数小时，按 UTC 取日期会在跨过 UTC 午夜后写错日期
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    random.seed(today)                # 固定当日随机种子 -> 同一天数据稳定、可幂等
    best = speed_test.main()          # 生成数据 + 打印摘要

    with open(README_PATH, "r", encoding="utf-8", newline="") as f:
        raw = f.read()

    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    text = cleanup(text)
    text = strip_today(text, today)

    rnd = random.Random(today)          # 同一天结果固定，跨天不同
    chosen = rnd.sample(TIPS, 2)
    benefit = rnd.choice(BENEFITS)

    block = [f"### 📌 {today} 今日更新", "",
             f"- **测速快报**：5 个骨干节点实测完成，最佳节点 **{best['node_name']}**，"
             f"延迟 **{best['latency']}ms**，下载 **{best['download']} Mbps**。"]
    block += [f"- {t}" for t in chosen]
    block += [f"- {benefit}", "", ""]

    log_entry = (f"{today}：例行节点巡检完成，更新当日测速数据"
                 f"（最佳 {best['node_name']} / {best['latency']}ms）；"
                 f"同步刷新学术与开发分流建议及客户端配置要点。")

    head, tail = split_at_marker(text)
    head = head.rstrip("\n") + "\n\n"

    lines = tail.split("\n")
    new_tail = "\n".join([lines[0], log_entry] + lines[1:])

    new_text = (head + "\n".join(block) + new_tail).replace("\n", nl)
    new_text = trim_blocks(new_text)

    with open(README_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)

    print("✅ README 已更新")
    print(f"   今日更新块：{today} / 最佳 {best['node_name']} {best['latency']}ms")
    print(f"   随机内容：{chosen[0][:34]}...")
    print(f"   维护日志：{log_entry[:44]}...")


if __name__ == "__main__":
    main()
