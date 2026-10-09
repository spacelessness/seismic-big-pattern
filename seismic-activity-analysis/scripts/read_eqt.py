#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 EQT 格式地震目录文件。

可作为命令行工具调用，也可作为模块导入使用：

    from read_eqt import read_eqt
    df = read_eqt('catalog.eqt')
    m6 = df[df['magnitude'] >= 6.0]

命令行用法：
    python read_eqt.py input.eqt              # 默认：打印摘要到 stdout
    python read_eqt.py input.eqt --json       # 输出 JSON 到 stdout（供程序消费）
    python read_eqt.py input.eqt -o out.csv   # 可选：保存为 CSV
    python read_eqt.py input.eqt --summary    # 详细摘要
"""

import pandas as pd
import argparse
import sys
import json
from pathlib import Path


def read_eqt(file_path):
    """
    读取 EQT 格式的地震事件文件，返回 DataFrame。

    参数
    ----------
    file_path : str or Path
        .eqt 文件路径。

    返回
    -------
    pandas.DataFrame
        包含列：year, month, day, hour, minute, second,
        latitude, longitude, magnitude, depth, location
    """
    colspecs = [
        (0, 5),    # 年份
        (5, 7),    # 月份
        (7, 9),    # 日期
        (9, 11),   # 小时
        (11, 13),  # 分钟
        (13, 15),  # 秒
        (15, 21),  # 纬度
        (21, 28),  # 经度
        (28, 32),  # 震级
        (32, 39),  # 深度
        (39, None) # 地名
    ]
    names = ['year', 'month', 'day', 'hour', 'minute', 'second',
             'latitude', 'longitude', 'magnitude', 'depth', 'location']

    df = pd.read_fwf(
        file_path,
        colspecs=colspecs,
        names=names,
        encoding='GBK',
        header=None,
        dtype=str
    )
    numeric_cols = ['year', 'month', 'day', 'hour', 'minute', 'second',
                    'latitude', 'longitude', 'magnitude', 'depth']
    for col in numeric_cols:
        df[col] = df[col].str.strip()
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
    return df


def main():
    parser = argparse.ArgumentParser(
        description='读取 EQT 地震目录文件，默认打印摘要不产生文件'
    )
    parser.add_argument('input', type=str, help='输入 .eqt 文件路径')
    parser.add_argument('-o', '--output', type=str, default=None,
                        help='（可选）输出 CSV 文件路径')
    parser.add_argument('--summary', action='store_true',
                        help='打印详细摘要')
    parser.add_argument('--json', action='store_true',
                        help='以 JSON 格式输出全部数据到 stdout')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f'错误：文件 {input_path} 不存在', file=sys.stderr)
        sys.exit(1)

    df = read_eqt(input_path)

    if args.json:
        # 输出 JSON 到 stdout，depth NaN 转为 null
        output = df.to_dict(orient='records')
        for rec in output:
            for k, v in rec.items():
                if pd.isna(v):
                    rec[k] = None
                elif isinstance(v, (pd.Timestamp,)):
                    rec[k] = str(v)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    elif args.summary:
        print(f'文件：{input_path}')
        print(f'事件总数：{len(df)}')
        print(f'年份范围：{int(df["year"].min())} – {int(df["year"].max())}')
        print(f'震级范围：M{df["magnitude"].min():.1f} – M{df["magnitude"].max():.1f}')
        print()
        print('列统计：')
        print(df.describe(include='all'))
        print()
        print('前5行：')
        print(df.head().to_string())
    elif args.output:
        output_path = Path(args.output)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f'已保存为：{output_path}')
    else:
        # 默认：简洁摘要
        print(f'文件：{input_path}')
        print(f'事件总数：{len(df)}')
        print(f'年份范围：{int(df["year"].min())} – {int(df["year"].max())}')
        print(f'震级范围：M{df["magnitude"].min():.1f} – M{df["magnitude"].max():.1f}')
        print()
        print(df.to_string(max_rows=20))


if __name__ == '__main__':
    main()
