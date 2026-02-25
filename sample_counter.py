#!/usr/bin/env python3
"""基于电压过零点的自适应分段，统计每个周期的真实采样点数。"""

from __future__ import annotations

import argparse
import csv
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Sample:
    voltage: float | None
    current: float | None


@dataclass
class Cycle:
    cycle_id: int
    start_index: int
    end_index: int
    sample_count: int


def parse_float(raw: str) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_samples(csv_path: Path, encoding: str) -> List[Sample]:
    samples: List[Sample] = []
    with csv_path.open("r", encoding=encoding, newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            samples.append(
                Sample(
                    voltage=parse_float(row.get("电压", "")),
                    current=parse_float(row.get("电流", "")),
                )
            )
    return samples


def find_rising_zero_crossings(
    samples: List[Sample],
    deadband: float,
    min_slope: float,
) -> List[int]:
    """找到电压上升过零点(负->正)对应的索引。"""
    anchors: List[int] = []
    prev_v: float | None = None
    prev_i: int | None = None

    for i, point in enumerate(samples):
        v = point.voltage
        if v is None:
            continue
        if prev_v is None or prev_i is None:
            prev_v = v
            prev_i = i
            continue

        crossed_strong = prev_v <= -deadband and v >= deadband
        crossed_basic = prev_v < 0 <= v and (v - prev_v) >= min_slope
        if crossed_strong or crossed_basic:
            anchors.append(i)

        prev_v = v
        prev_i = i

    return anchors


def build_cycles_from_anchors(anchors: List[int]) -> List[Cycle]:
    cycles: List[Cycle] = []
    for idx in range(len(anchors) - 1):
        start = anchors[idx]
        end = anchors[idx + 1]
        cycles.append(
            Cycle(
                cycle_id=idx + 1,
                start_index=start,
                end_index=end,
                sample_count=end - start,
            )
        )
    return cycles


def save_report(cycles: List[Cycle], nominal_len: int, output_csv: Path) -> None:
    with output_csv.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["周期编号", "起始索引", "结束索引", "真实采样点数", "相对128偏差"])
        for c in cycles:
            writer.writerow(
                [
                    c.cycle_id,
                    c.start_index,
                    c.end_index,
                    c.sample_count,
                    c.sample_count - nominal_len,
                ]
            )


def print_summary(samples: List[Sample], anchors: List[int], cycles: List[Cycle], nominal_len: int) -> None:
    print(f"总采样点: {len(samples)}")
    print(f"检测到上升过零锚点数: {len(anchors)}")
    print(f"可形成完整周期数: {len(cycles)}")

    if not cycles:
        return

    counts = [c.sample_count for c in cycles]
    mean_count = statistics.mean(counts)
    median_count = statistics.median(counts)
    print(
        "周期采样点统计: "
        f"min={min(counts)}, max={max(counts)}, mean={mean_count:.3f}, median={median_count:.3f}"
    )
    print(
        f"与标称点数({nominal_len})偏差范围: "
        f"[{min(counts) - nominal_len}, {max(counts) - nominal_len}]"
    )

    print("前5个周期: 周期编号, 起始索引, 结束索引, 真实采样点数")
    for c in cycles[:5]:
        print(f"{c.cycle_id}, {c.start_index}, {c.end_index}, {c.sample_count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="基于电压过零点统计每周期真实采样点数")
    parser.add_argument("--input", default="电动自行车充电波形数据.csv", help="输入 CSV 文件")
    parser.add_argument("--encoding", default="gbk", help="输入文件编码")
    parser.add_argument("--nominal-len", type=int, default=128, help="标称周期点数")
    parser.add_argument("--zero-deadband", type=float, default=5.0, help="过零死区电压阈值（V）")
    parser.add_argument("--min-slope", type=float, default=1.0, help="过零最小斜率阈值")
    parser.add_argument("--output", default="周期真实采样点统计.csv", help="输出统计 CSV")
    args = parser.parse_args()

    samples = read_samples(Path(args.input), args.encoding)
    if not samples:
        raise SystemExit("输入文件无有效数据")

    anchors = find_rising_zero_crossings(samples, args.zero_deadband, args.min_slope)
    cycles = build_cycles_from_anchors(anchors)
    if not cycles:
        raise SystemExit("未检测到足够的过零锚点，无法形成周期")

    save_report(cycles, args.nominal_len, Path(args.output))
    print_summary(samples, anchors, cycles, args.nominal_len)
    print(f"统计结果已输出到: {args.output}")


if __name__ == "__main__":
    main()
