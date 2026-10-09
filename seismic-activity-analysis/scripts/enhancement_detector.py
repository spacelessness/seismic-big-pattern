#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
地震活动显著增强检测模块

基于《测震分析预测技术方法工作手册》第5章定义，对地震目录进行网格化时空扫描，
自动识别满足"地震活动显著增强"判据的区域。

判据（文档 5.3 节）：
  ① 应变释放曲线明显上升，呈上翘弧形
  ② 上升时间至少持续 1 年以上
  ③ 上升期间，年应变释放量 ≥ 前 3 年平均释放量的 2 倍
  ④ 上升期间，年地震频度 ≥ 前 3 年平均频度的 2 倍

用法：
    from enhancement_detector import detect_enhancement, benioff_strain
    results = detect_enhancement('catalog.eqt', grid_size=1.0)
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
from collections import defaultdict
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


# ═══════════════════════════════════════════════════════════
# 1. Benioff 应变计算
# ═══════════════════════════════════════════════════════════

def seismic_energy_joules(magnitude):
    """
    Gutenberg-Richter 能量公式 (SI 单位).
    log10(E) = 4.8 + 1.5*M  →  E = 10^(4.8 + 1.5M) Joules
    """
    return np.power(10.0, 4.8 + 1.5 * magnitude)


def benioff_strain(magnitude):
    """
    Benioff 应变释放: sqrt(E) = 10^(2.4 + 0.75*M)  J^(1/2)
    """
    return np.power(10.0, 2.4 + 0.75 * magnitude)


# ═══════════════════════════════════════════════════════════
# 2. 震级完整性估算
# ═══════════════════════════════════════════════════════════

def estimate_magnitude_completeness(df, mag_col='magnitude'):
    """
    从目录估算完整性震级 Mc。

    使用 MAXC (最大曲率) 方法：统计震级-频度分布，取频度最高档位 + 0.2 作为 Mc。
    如果目录条目较少则回退到 5 分位数法。
    """
    mags = df[mag_col].dropna()
    if len(mags) < 20:
        return np.percentile(mags, 10)

    # 0.1 档宽统计
    bins = np.arange(np.floor(mags.min() * 10) / 10,
                     np.ceil(mags.max() * 10) / 10 + 0.1, 0.1)
    hist, edges = np.histogram(mags, bins=bins)
    if len(hist) == 0:
        return np.percentile(mags, 10)

    peak_idx = np.argmax(hist)
    mc = edges[peak_idx] + 0.2
    return round(min(mc, np.percentile(mags, 30)), 1)


# ═══════════════════════════════════════════════════════════
# 3. 时间序列构建
# ═══════════════════════════════════════════════════════════

def _make_timeseries(events, start_date, end_date, window_months=12):
    """
    构建月度统计时间序列。

    返回 DataFrame，每行一个月份：
      month_start, count, strain_sum, strain_cum, trailing_{w}m_strain, trailing_{w}m_count
    """
    if len(events) == 0:
        return pd.DataFrame()

    # 确保 datetime 列
    events = events.copy()
    events['datetime'] = pd.to_datetime(
        dict(year=events['year'].astype(int),
             month=events['month'].astype(int).clip(1, 12),
             day=events['day'].astype(int).clip(1, 28)),
        errors='coerce'
    )

    # 月度区间
    current = pd.Timestamp(start_date.year, start_date.month, 1)
    end = pd.Timestamp(end_date.year, end_date.month, 1)

    rows = []
    while current <= end:
        month_end = current + pd.DateOffset(months=1)
        mask = (events['datetime'] >= current) & (events['datetime'] < month_end)
        month_events = events[mask]
        rows.append({
            'month_start': current,
            'count': len(month_events),
            'strain_sum': benioff_strain(month_events['magnitude'].values).sum(),
        })
        current = month_end

    ts = pd.DataFrame(rows)
    if len(ts) == 0:
        return ts

    ts['strain_cum'] = ts['strain_sum'].cumsum()

    # 滑动窗口统计
    for w in [6, 12]:
        ts[f'trailing_{w}m_strain'] = ts['strain_sum'].rolling(w, min_periods=1).sum()
        ts[f'trailing_{w}m_count'] = ts['count'].rolling(w, min_periods=1).sum()

    return ts


# ═══════════════════════════════════════════════════════════
# 4. 单网格增强检测
# ═══════════════════════════════════════════════════════════

def _detect_in_grid(events, mc, window_months, min_baseline_months=36,
                    min_duration_months=12, min_events=10):
    """
    在单个网格内检测地震活动显著增强。

    参数
    ----------
    events : DataFrame (含 year/month/day/magnitude)
    window_months : int — 分析窗口长度 (6 或 12)
    min_baseline_months : int — 基线最少月数 (默认 36 = 3年)
    min_duration_months : int — 增强最少持续月数 (默认 12)
    min_events : int — 网格最少事件数

    返回
    -------
    list of dict — 每个增强时段一条
    """
    if len(events) < min_events:
        return []

    events = events[events['magnitude'] >= mc]
    if len(events) < min_events:
        return []

    # 时间范围
    start = pd.Timestamp(int(events['year'].min()), max(int(events['month'].min()), 1), 1)
    end = pd.Timestamp(int(events['year'].max()), max(int(events['month'].max()), 1), 1)
    if (end - start).days < 365:
        return []

    ts = _make_timeseries(events, start, end, window_months)
    if len(ts) < window_months + min_baseline_months:
        return []

    w = window_months
    strain_col = f'trailing_{w}m_strain'
    count_col = f'trailing_{w}m_count'

    # 逐月检测
    results = []
    in_enhancement = False
    enhance_start = None
    enhance_peak_ratio = 0.0

    # 需要足够基线: 从 36 个月后开始
    for idx in range(min_baseline_months + w, len(ts)):
        # 当前窗口的年度指标
        win_strain = ts[strain_col].iloc[idx]
        win_count = ts[count_col].iloc[idx]

        # 基线: 前 3 年 (当前窗口之前 36 个月)
        baseline_start = idx - w - min_baseline_months
        baseline_end = idx - w
        if baseline_start < 0:
            continue

        baseline_events = ts.iloc[baseline_start:baseline_end]
        if baseline_events['count'].sum() < 5:
            continue
        baseline_strain_annual = baseline_events['strain_sum'].sum() / (min_baseline_months / 12)
        baseline_count_annual = baseline_events['count'].sum() / (min_baseline_months / 12)

        if baseline_strain_annual <= 0 or baseline_count_annual <= 0:
            continue

        # 年化 (窗口为 w 月, 折算为 12 个月)
        annual_strain = win_strain * (12.0 / w)
        annual_count = win_count * (12.0 / w)

        strain_ratio = annual_strain / baseline_strain_annual
        count_ratio = annual_count / baseline_count_annual

        meets_criteria = (strain_ratio >= 2.0 and count_ratio >= 2.0)

        if meets_criteria and not in_enhancement:
            in_enhancement = True
            enhance_start = ts['month_start'].iloc[idx]
            enhance_peak_ratio = max(strain_ratio, count_ratio)
        elif meets_criteria and in_enhancement:
            enhance_peak_ratio = max(enhance_peak_ratio, strain_ratio, count_ratio)
        elif not meets_criteria and in_enhancement:
            # 增强结束
            duration = (ts['month_start'].iloc[idx] - enhance_start).days / 30.44
            if duration >= min_duration_months:
                enhance_end = ts['month_start'].iloc[idx]
                enhance_events = events[
                    (events['datetime'] >= enhance_start) &
                    (events['datetime'] < enhance_end) &
                    (events['magnitude'] >= mc)
                ]
                results.append({
                    'enhance_start': enhance_start,
                    'enhance_end': enhance_end,
                    'duration_months': round(duration, 1),
                    'strain_ratio': round(enhance_peak_ratio, 1),
                    'count_ratio': round(count_ratio, 1),
                    'n_events_window': len(enhance_events),
                    'max_magnitude': enhance_events['magnitude'].max(),
                    'total_strain': benioff_strain(enhance_events['magnitude'].values).sum(),
                    'window_months': w,
                    'mc_used': mc,
                })
            in_enhancement = False
            enhance_start = None
            enhance_peak_ratio = 0.0

    # 如果增强持续到末尾
    if in_enhancement and enhance_start is not None:
        duration = (ts['month_start'].iloc[-1] - enhance_start).days / 30.44
        if duration >= min_duration_months:
            enhance_events = events[
                (events['datetime'] >= enhance_start) &
                (events['magnitude'] >= mc)
            ]
            results.append({
                'enhance_start': enhance_start,
                'enhance_end': ts['month_start'].iloc[-1],
                'duration_months': round(duration, 1),
                'strain_ratio': round(enhance_peak_ratio, 1),
                'count_ratio': round(count_ratio, 1),
                'n_events_window': len(enhance_events),
                'max_magnitude': enhance_events['magnitude'].max(),
                'total_strain': benioff_strain(enhance_events['magnitude'].values).sum(),
                'window_months': w,
                'mc_used': mc,
            })

    return results


# ═══════════════════════════════════════════════════════════
# 5. 网格扫描主函数
# ═══════════════════════════════════════════════════════════

def detect_enhancement(input_data, grid_size=1.0, windows=(6, 12),
                       mc=None, min_events=10, min_duration_months=12,
                       output_path=None, verbose=True):
    """
    对地震目录进行网格化时空扫描，检测地震活动显著增强。

    参数
    ----------
    input_data : str, Path, or pd.DataFrame
        输入数据 (.eqt / .csv / DataFrame)
    grid_size : float
        网格大小（度），默认 1.0°
    windows : tuple of int
        分析窗口长度（月），默认 (6, 12)
    mc : float or None
        完整性震级下限，None 则自动估算
    min_events : int
        网格最少事件数，低于此值跳过
    min_duration_months : int
        增强最少持续月数（默认 12，对应"至少持续 1 年"）
    output_path : str or None
        结果输出 CSV 路径
    verbose : bool
        是否打印进度

    返回
    -------
    pd.DataFrame
        检测结果，每行一个增强时段。列:
        grid_lat, grid_lon, grid_w, grid_e, grid_s, grid_n,
        enhance_start, enhance_end, duration_months,
        strain_ratio, count_ratio, window_months, mc_used,
        n_events_window, max_magnitude, total_strain
    """
    # 1. 解析输入
    if isinstance(input_data, pd.DataFrame):
        df = input_data.copy()
    elif isinstance(input_data, (str, Path)):
        path = Path(input_data)
        if path.suffix.lower() == '.eqt':
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from read_eqt import read_eqt
            df = read_eqt(str(path))
        elif path.suffix.lower() == '.csv':
            df = pd.read_csv(path, encoding='utf-8')
        else:
            df = pd.read_csv(path, sep=r'\s+', encoding='utf-8')
    else:
        raise TypeError(f'不支持的类型: {type(input_data)}')

    # 列名标准化
    _col_map = {'lon': 'longitude', 'lng': 'longitude', 'lat': 'latitude', 'mag': 'magnitude', 'm': 'magnitude'}
    df = df.rename(columns={c: _col_map[c] for c in df.columns if c.lower() in _col_map})

    # 过滤：仅保留年份 >= 1900 的仪器记录（古地震不适用于增强检测）
    if 'year' in df.columns:
        n_before = len(df)
        df = df[df['year'] >= 1900].copy()
        if verbose and n_before > len(df):
            print(f'[过滤] 去除 {n_before - len(df)} 条 1900 年前的记录')

    # 2. 完整性震级
    if mc is None:
        mc = estimate_magnitude_completeness(df)
    if verbose:
        print(f'[完整性震级] Mc = {mc}')

    # 3. 构建网格
    lat_min, lat_max = np.floor(df['latitude'].min()), np.ceil(df['latitude'].max())
    lon_min, lon_max = np.floor(df['longitude'].min()), np.ceil(df['longitude'].max())

    lat_edges = np.arange(lat_min, lat_max + grid_size, grid_size)
    lon_edges = np.arange(lon_min, lon_max + grid_size, grid_size)

    n_grids = (len(lat_edges) - 1) * (len(lon_edges) - 1)
    if verbose:
        print(f'[网格] {grid_size}°×{grid_size}° 共 {n_grids} 个网格')
        print(f'[范围] 经度 {lon_min}–{lon_max}  纬度 {lat_min}–{lat_max}')
        print(f'[窗口] {windows} 个月  |  最少持续 {min_duration_months} 个月')

    # 添加 datetime 列（处理无效月份/日期）
    years = df['year'].fillna(2000).astype(int)
    months = df['month'].fillna(1).astype(int).clip(1, 12)
    days = df['day'].fillna(1).astype(int).clip(1, 28)
    df['datetime'] = pd.to_datetime(
        dict(year=years, month=months, day=days),
        errors='coerce'
    )
    # 去除无法解析的日期
    df = df.dropna(subset=['datetime'])

    # 4. 网格扫描
    all_results = []
    scanned = 0
    for i in range(len(lat_edges) - 1):
        for j in range(len(lon_edges) - 1):
            scanned += 1
            s, n = lat_edges[i], lat_edges[i + 1]
            w, e = lon_edges[j], lon_edges[j + 1]

            mask = ((df['latitude'] >= s) & (df['latitude'] < n) &
                    (df['longitude'] >= w) & (df['longitude'] < e))
            grid_events = df[mask]

            if len(grid_events) < min_events:
                continue

            for wm in windows:
                results = _detect_in_grid(
                    grid_events, mc=mc, window_months=wm,
                    min_duration_months=min_duration_months,
                    min_events=min_events
                )
                for r in results:
                    r['grid_lat'] = round((s + n) / 2, 2)
                    r['grid_lon'] = round((w + e) / 2, 2)
                    r['grid_w'] = w
                    r['grid_e'] = e
                    r['grid_s'] = s
                    r['grid_n'] = n
                    all_results.append(r)

            if verbose and scanned % max(1, n_grids // 20) == 0:
                print(f'  扫描进度: {scanned}/{n_grids} ({scanned*100//n_grids}%)')

    if verbose:
        print(f'[完成] 扫描 {scanned} 个网格，检测到 {len(all_results)} 个增强时段')

    # 5. 整理结果
    if not all_results:
        if verbose:
            print('[结果] 未检测到满足条件的地震活动显著增强')
        return pd.DataFrame()

    result_df = pd.DataFrame(all_results)
    # 按增强开始时间排序
    result_df = result_df.sort_values('enhance_start').reset_index(drop=True)

    # 去重：相邻网格检测到的相同增强时段合并
    result_df = _merge_overlapping_results(result_df)

    if verbose and len(result_df) > 0:
        print(f'[去重后] {len(result_df)} 个独立增强时段')
        print()
        _print_summary(result_df)

    # 6. 保存
    if output_path:
        result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        if verbose:
            print(f'\n[保存] {output_path}')

    return result_df


def _merge_overlapping_results(df, time_tol_months=3, space_tol_deg=1.5):
    """
    合并相邻网格中检测到的重叠增强时段。
    时间重叠 > time_tol_months 且空间距离 < space_tol_deg 的合并为一个。
    """
    if len(df) <= 1:
        return df

    df = df.sort_values('enhance_start').reset_index(drop=True)
    merged = []
    used = set()

    for i in range(len(df)):
        if i in used:
            continue
        group = [i]
        used.add(i)
        for j in range(i + 1, len(df)):
            if j in used:
                continue
            # 时间重叠
            a_start = df['enhance_start'].iloc[i]
            a_end = df['enhance_end'].iloc[i]
            b_start = df['enhance_start'].iloc[j]
            b_end = df['enhance_end'].iloc[j]
            time_overlap = (min(a_end, b_end) - max(a_start, b_start)).days / 30.44
            if time_overlap < -time_tol_months:
                continue
            # 空间距离
            dist = np.sqrt((df['grid_lat'].iloc[i] - df['grid_lat'].iloc[j])**2 +
                           (df['grid_lon'].iloc[i] - df['grid_lon'].iloc[j])**2)
            if dist < space_tol_deg:
                group.append(j)
                used.add(j)

        if len(group) > 1:
            # 合并：取最早开始、最晚结束、最大比例
            sub = df.iloc[group]
            row = sub.iloc[0].to_dict()
            row['enhance_start'] = sub['enhance_start'].min()
            row['enhance_end'] = sub['enhance_end'].max()
            row['duration_months'] = round(
                (row['enhance_end'] - row['enhance_start']).days / 30.44, 1)
            row['strain_ratio'] = sub['strain_ratio'].max()
            row['count_ratio'] = sub['count_ratio'].max()
            row['n_events_window'] = sub['n_events_window'].sum()
            row['max_magnitude'] = sub['max_magnitude'].max()
            row['grid_lat'] = round(sub['grid_lat'].mean(), 2)
            row['grid_lon'] = round(sub['grid_lon'].mean(), 2)
            row['grid_w'] = sub['grid_w'].min()
            row['grid_e'] = sub['grid_e'].max()
            row['grid_s'] = sub['grid_s'].min()
            row['grid_n'] = sub['grid_n'].max()
            merged.append(row)
        else:
            merged.append(df.iloc[i].to_dict())

    return pd.DataFrame(merged)


def _print_summary(df):
    """打印检测结果摘要。"""
    print(f'{"#":<4} {"开始":<10} {"结束":<10} {"持续/月":<8} {"应变比":<8} {"频次比":<8} {"窗/月":<6} {"网格中心":<12} {"最大M":<6}')
    print('─' * 80)
    for i, (_, r) in enumerate(df.iterrows(), 1):
        s = str(r['enhance_start'])[:10]
        e = str(r['enhance_end'])[:10]
        g = f'({r["grid_lat"]:.1f},{r["grid_lon"]:.1f})'
        print(f'{i:<4} {s:<10} {e:<10} {r["duration_months"]:<8.0f} '
              f'{r["strain_ratio"]:<8.1f} {r["count_ratio"]:<8.1f} '
              f'{r["window_months"]:<6} {g:<12} M{r["max_magnitude"]:<5.1f}')


# ═══════════════════════════════════════════════════════════
# 6. 命令行入口
# ═══════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description='检测地震活动显著增强（网格扫描）')
    parser.add_argument('input', type=str, help='输入文件 (.eqt / .csv)')
    parser.add_argument('-o', '--output', type=str, default=None, help='输出 CSV 路径')
    parser.add_argument('-g', '--grid-size', type=float, default=1.0, help='网格大小（度）')
    parser.add_argument('--mc', type=float, default=None, help='完整性震级（不指定则自动估算）')
    parser.add_argument('--min-events', type=int, default=10, help='网格最少事件数')
    parser.add_argument('--min-duration', type=int, default=12, help='增强最少持续月数')
    parser.add_argument('--windows', type=str, default='6,12', help='分析窗口（月），逗号分隔')
    args = parser.parse_args()

    windows = tuple(int(w.strip()) for w in args.windows.split(','))

    detect_enhancement(
        args.input,
        grid_size=args.grid_size,
        windows=windows,
        mc=args.mc,
        min_events=args.min_events,
        min_duration_months=args.min_duration,
        output_path=args.output,
        verbose=True
    )


if __name__ == '__main__':
    main()
