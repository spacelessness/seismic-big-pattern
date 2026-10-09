#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import argparse
from pathlib import Path

def write_eqt(df, file_path):
    """
    将 DataFrame 保存为标准 EQT 格式（GBK编码）。
    """
    required_cols = ['year', 'month', 'day', 'hour', 'minute', 'second',
                     'latitude', 'longitude', 'magnitude', 'depth', 'location']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"DataFrame 缺少必需的列: {col}")

    lines = []
    for _, row in df.iterrows():
        year = row['year'] if not pd.isna(row['year']) else 0
        year_str = f"{int(year):>5}"

        month = row['month'] if not pd.isna(row['month']) else 0
        day   = row['day']   if not pd.isna(row['day'])   else 0
        hour  = row['hour']  if not pd.isna(row['hour'])  else 0
        minute = row['minute'] if not pd.isna(row['minute']) else 0
        second = row['second'] if not pd.isna(row['second']) else 0
        month_str = f"{int(month):02d}"
        day_str   = f"{int(day):02d}"
        hour_str  = f"{int(hour):02d}"
        minute_str = f"{int(minute):02d}"
        second_str = f"{int(second):02d}"

        lat = row['latitude'] if not pd.isna(row['latitude']) else 0.0
        lat_str = f"{float(lat):>6.2f}"

        lon = row['longitude'] if not pd.isna(row['longitude']) else 0.0
        lon_str = f"{float(lon):>7.2f}"

        mag = row['magnitude'] if not pd.isna(row['magnitude']) else 0.0
        mag_str = f"{float(mag):>4.2f}"

        depth = row['depth'] if not pd.isna(row['depth']) else -1000
        depth_str = f"{int(depth):>6}"

        location = row['location'] if not pd.isna(row['location']) else ""
        location_str = str(location).lstrip()

        line = (year_str + month_str + day_str + hour_str + minute_str + second_str +
                lat_str + lon_str + mag_str + depth_str + ' ' + location_str)
        lines.append(line)

    with open(file_path, 'w', encoding='gbk') as f:
        for line in lines:
            f.write(line + '\n')

def main():
    parser = argparse.ArgumentParser(description='将 CSV 文件转换为标准 EQT 格式')
    parser.add_argument('input', type=str, help='输入 CSV 文件路径')
    parser.add_argument('-o', '--output', type=str, help='输出 EQT 文件路径（可选）')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f'错误：文件 {input_path} 不存在', file=sys.stderr)
        sys.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(input_path, encoding='gbk')

    output_path = args.output if args.output else input_path.with_suffix('.eqt')
    write_eqt(df, output_path)
    print(f'已保存为：{output_path}')

if __name__ == '__main__':
    main()