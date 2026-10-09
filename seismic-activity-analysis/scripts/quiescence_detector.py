#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
地震活动显著平静检测模块

基于《测震分析预测技术方法工作手册》第7章定义，对地震目录进行网格化时空扫描，
自动识别满足判据的地震活动显著平静区域。

支持两种方法：
  方法一 — D-T统计法（7.3.1节）：
    对每个网格，计算历史地震间隔时间的均值 μ 和标准差 σ，
    以 μ + k·σ（默认 k=2）为异常阈值。
    当当前平静时间超过该阈值 → 显著平静。

  方法二 — Z值法（7.3.2节）：
    基于累计频度变化率差异的统计检验，
    Z = (R1 - R2) / sqrt(σ1²/n1 + σ2²/n2)，
    其中 R1 为背景期平均变化率，R2 为滑动窗口变化率。
    Z > 0 表示活动减弱（平静）。

用法：
    from quiescence_detector import detect_quiescence
    results = detect_quiescence('catalog.eqt', grid_size=1.0)
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
# 1. 余震删除 — Gardner-Knopoff 方法
# ═══════════════════════════════════════════════════════════

def _gk_space_window(magnitude):
    """Gardner-Knopoff 空间窗半径 (km)"""
    return np.power(10.0, 0.1238 * magnitude + 0.983)


def _gk_time_window(magnitude):
    """Gardner-Knopoff 时间窗 (天)"""
    if magnitude >= 6.5:
        return np.power(10.0, 0.032 * magnitude + 2.7389)
    else:
        return np.power(10.0, 0.5409 * magnitude - 0.547)


def _km_to_deg(km, lat):
    """公里近似转度（纬度方向）"""
    return km / 111.0


def remove_aftershocks(df, method='gardner_knopoff', verbose=True):
    """
    删除地震目录中的余震，保留主震。

    使用 Gardner-Knopoff (1974) 时空窗法：
    - 按震级从大到小遍历每个事件
    - 对每个事件，将其时空窗内所有更小的事件标记为余震
    - 仅保留未被标记的（主震）事件

    参数
    ----------
    df : pd.DataFrame
        含 year, month, day, latitude, longitude, magnitude 列
    method : str
        'gardner_knopoff' — Gardner-Knopoff 时空窗
    verbose : bool
        是否打印统计信息

    返回
    -------
    pd.DataFrame
        去除余震后的目录
    """
    if len(df) == 0:
        return df

    df = df.copy()
    # 构建 datetime
    years = df['year'].fillna(2000).astype(int)
    months = df['month'].fillna(1).astype(int).clip(1, 12)
    days = df['day'].fillna(1).astype(int).clip(1, 28)
    df['datetime'] = pd.to_datetime(
        dict(year=years, month=months, day=days), errors='coerce'
    )
    df = df.dropna(subset=['datetime'])

    # 按震级从大到小排序
    df = df.sort_values(['magnitude', 'datetime'], ascending=[False, True]).reset_index(drop=True)

    n_total = len(df)
    is_aftershock = np.zeros(n_total, dtype=bool)

    for i in range(n_total):
        if is_aftershock[i]:
            continue
        mag_i = df['magnitude'].iloc[i]
        t_i = df['datetime'].iloc[i]
        lat_i = df['latitude'].iloc[i]
        lon_i = df['longitude'].iloc[i]

        space_km = _gk_space_window(mag_i)
        time_days = _gk_time_window(mag_i)

        # 限定搜索范围：仅搜索 i 之后（震级更小或时间更晚）的事件
        for j in range(i + 1, n_total):
            if is_aftershock[j]:
                continue
            # 时间窗
            dt = abs((df['datetime'].iloc[j] - t_i).total_seconds()) / 86400.0
            if dt > time_days:
                continue
            # 空间窗（简化为圆形）
            dlat = abs(df['latitude'].iloc[j] - lat_i) * 111.0
            dlon = abs(df['longitude'].iloc[j] - lon_i) * 111.0 * np.cos(np.radians((lat_i + df['latitude'].iloc[j]) / 2))
            dist_km = np.sqrt(dlat**2 + dlon**2)
            if dist_km <= space_km:
                is_aftershock[j] = True

    result = df[~is_aftershock].copy()
    if verbose:
        removed = n_total - len(result)
        print(f'[余震删除] {n_total} → {len(result)} 条（移除 {removed} 条，{removed*100//n_total}%）')

    return result


# ═══════════════════════════════════════════════════════════
# 2. 震级完整性估算
# ═══════════════════════════════════════════════════════════

def estimate_magnitude_completeness(df, mag_col='magnitude'):
    """
    从目录估算完整性震级 Mc。

    使用 MAXC (最大曲率) 方法：统计震级-频度分布，取频度最高档位 + 0.2 作为 Mc。
    如果目录条目较少则回退到分位数法。
    """
    mags = df[mag_col].dropna()
    if len(mags) < 20:
        return np.percentile(mags, 10)

    bins = np.arange(np.floor(mags.min() * 10) / 10,
                     np.ceil(mags.max() * 10) / 10 + 0.1, 0.1)
    hist, edges = np.histogram(mags, bins=bins)
    if len(hist) == 0:
        return np.percentile(mags, 10)

    peak_idx = np.argmax(hist)
    mc = edges[peak_idx] + 0.2
    return round(min(mc, np.percentile(mags, 30)), 1)


# ═══════════════════════════════════════════════════════════
# 3. D-T 统计法 — 单网格检测
# ═══════════════════════════════════════════════════════════

def _detect_quiescence_dt_grid(events, mag_threshold, sigma_mult=2.0,
                                min_gap_days=30, min_events=20,
                                global_catalog_end=None):
    """
    在单个网格内使用 D-T 统计法检测地震活动显著平静。

    算法（对应文档 7.3.1 节）：
    1. 筛选 ≥ mag_threshold 的事件，按时间排序
    2. 计算相邻事件的时间间隔序列
    3. 计算间隔序列的均值 μ 和标准差 σ
    4. 阈值 T = μ + sigma_mult × σ
    5. 扫描找时间间隔 > T 的时段 → 显著平静

    参数
    ----------
    events : DataFrame (含 datetime, magnitude)
    mag_threshold : float — 震级下限
    sigma_mult : float — σ 倍乘系数（默认 2.0，即 μ+2σ）
    min_gap_days : float — 最短平静时长（天），低于此值不报告
    min_events : int — 最少事件数，低于此值不分析

    返回
    -------
    list of dict
    """
    eq = events[events['magnitude'] >= mag_threshold].sort_values('datetime')
    if len(eq) < min_events:
        return []

    times = eq['datetime'].values
    mags = eq['magnitude'].values

    # 计算间隔时间（天）
    gaps = []
    for i in range(1, len(times)):
        gap = (times[i] - times[i - 1]) / np.timedelta64(1, 'D')
        gaps.append(gap)

    if len(gaps) < 5:
        return []

    gaps = np.array(gaps)
    mu = np.mean(gaps)
    sigma = np.std(gaps, ddof=0)  # 总体标准差

    if sigma < 1e-6:
        return []  # 间隔过于均匀，无法判定

    threshold = mu + sigma_mult * sigma

    # 同时用95分位法交叉验证（文档7.3.1节方法）
    p95 = np.percentile(gaps, 95)
    threshold = max(threshold, p95 * 0.9)  # 取较严格的阈值

    # 扫描异常间隙
    results = []
    for i in range(1, len(times)):
        gap = (times[i] - times[i - 1]) / np.timedelta64(1, 'D')
        if gap > threshold and gap >= min_gap_days:
            q_start = times[i - 1] + np.timedelta64(1, 'D')  # 从上一个事件次日起
            q_end = times[i]  # 到被下一个事件打破
            results.append({
                'quiescence_start': pd.Timestamp(q_start),
                'quiescence_end': pd.Timestamp(q_end),
                'duration_days': round(gap, 1),
                'threshold_days': round(threshold, 1),
                'mean_gap_days': round(mu, 1),
                'std_gap_days': round(sigma, 1),
                'sigma_mult': sigma_mult,
                'p95_days': round(p95, 1),
                'last_event_mag': mags[i - 1],
                'next_event_mag': mags[i],
                'last_event_time': pd.Timestamp(times[i - 1]),
                'next_event_time': pd.Timestamp(times[i]),
                'method': 'D-T',
                'ongoing': False,
            })

    # 检查末尾：最后一个事件至今（如果目录末尾存在正在持续的平静）
    # 使用全局目录结束时间，因为子阈值事件不打破平静
    last_event = times[-1]
    if global_catalog_end is not None:
        catalog_end = pd.Timestamp(global_catalog_end)
    else:
        catalog_end = pd.Timestamp(events['datetime'].max())
    end_gap = (catalog_end - last_event) / np.timedelta64(1, 'D')
    if end_gap > threshold and end_gap >= min_gap_days:
        results.append({
            'quiescence_start': pd.Timestamp(last_event + np.timedelta64(1, 'D')),
            'quiescence_end': catalog_end,
            'duration_days': round(end_gap, 1),
            'threshold_days': round(threshold, 1),
            'mean_gap_days': round(mu, 1),
            'std_gap_days': round(sigma, 1),
            'sigma_mult': sigma_mult,
            'p95_days': round(p95, 1),
            'last_event_mag': mags[-1],
            'next_event_mag': None,
            'last_event_time': pd.Timestamp(last_event),
            'next_event_time': None,
            'method': 'D-T',
            'ongoing': True,
        })

    return results


# ═══════════════════════════════════════════════════════════
# 4. Z值法 — 单网格检测
# ═══════════════════════════════════════════════════════════

def _detect_quiescence_z_grid(events, mag_threshold, window_days=180,
                               step_days=30, z_threshold=2.0,
                               min_events=20, min_duration_days=90):
    """
    在单个网格内使用 Z值法 检测地震活动显著平静。

    算法（对应文档 7.3.2 节）：
    Z(t) = (R1 - R2) / sqrt(R1/T_bg + R2/T_w)

    其中 R1 = N_bg / T_bg（背景期事件率），R2 = N_w / T_w（窗口事件率）。
    使用泊松假设：方差 ≈ 率值。
    Z > 0 表示活动率下降（平静），|Z| ≥ z_threshold 视为统计显著。

    参数
    ----------
    events : DataFrame
    mag_threshold : float
    window_days : int — 滑动窗口（天），默认 180 天
    step_days : int — 时间步长（天），默认 30 天
    z_threshold : float — Z值显著性阈值（默认 2.0）
    min_events : int — 最少事件数
    min_duration_days : float — 平静最短持续天数

    返回
    -------
    list of dict
    """
    eq = events[events['magnitude'] >= mag_threshold].sort_values('datetime')
    if len(eq) < min_events:
        return []

    t_start = eq['datetime'].iloc[0]
    t_end = eq['datetime'].iloc[-1]
    total_days = (t_end - t_start) / np.timedelta64(1, 'D')

    if total_days < window_days * 2:
        return []

    # 背景期：整个时段
    N_bg = len(eq)
    T_bg = total_days
    R1 = N_bg / T_bg if T_bg > 0 else 0

    # 滑动窗口扫描
    results = []
    current = t_start + pd.Timedelta(days=window_days)

    in_quiescence = False
    q_start = None
    z_peak = 0.0

    while current <= t_end:
        window_start = current - pd.Timedelta(days=window_days)

        # 窗口内事件数
        w_mask = (eq['datetime'] >= window_start) & (eq['datetime'] < current)
        N_w = w_mask.sum()
        T_w = window_days

        R2 = N_w / T_w

        # 泊松假设下的 Z 统计量:
        # Var(rate) ≈ rate / time_period
        # Z = (R1 - R2) / sqrt(R1/T_bg + R2/T_w)
        # 为避免除零，确保分母足够大
        var_R1 = max(R1 / T_bg, 1e-12)
        var_R2 = max(R2 / T_w, 1e-12)
        denominator = np.sqrt(var_R1 + var_R2)

        Z = (R1 - R2) / denominator if denominator > 0 else 0

        if Z > z_threshold:
            if not in_quiescence:
                in_quiescence = True
                q_start = current
                z_peak = Z
            else:
                z_peak = max(z_peak, Z)
        else:
            if in_quiescence:
                q_end = current
                duration = (q_end - q_start) / np.timedelta64(1, 'D')
                if duration >= min_duration_days:
                    results.append({
                        'quiescence_start': q_start,
                        'quiescence_end': q_end,
                        'duration_days': round(duration, 1),
                        'z_peak': round(z_peak, 2),
                        'z_threshold': z_threshold,
                        'window_days': window_days,
                        'step_days': step_days,
                        'method': 'Z-value',
                        'ongoing': False,
                    })
                in_quiescence = False
                q_start = None
                z_peak = 0.0

        current += pd.Timedelta(days=step_days)

    # 末尾：检查至目录末尾是否仍处于平静
    if in_quiescence and q_start is not None:
        duration = (t_end - q_start) / np.timedelta64(1, 'D')
        if duration >= min_duration_days:
            results.append({
                'quiescence_start': q_start,
                'quiescence_end': t_end,
                'duration_days': round(duration, 1),
                'z_peak': round(z_peak, 2),
                'z_threshold': z_threshold,
                'window_days': window_days,
                'step_days': step_days,
                'method': 'Z-value',
                'ongoing': True,
            })

    return results


# ═══════════════════════════════════════════════════════════
# 5. 网格扫描主函数
# ═══════════════════════════════════════════════════════════

def detect_quiescence(input_data, grid_size=1.0, mag_threshold=None,
                       method='both', do_remove_aftershocks=True,
                       sigma_mult=2.0, min_gap_days=30,
                       z_window=180, z_step=30, z_threshold=2.0,
                       min_duration_days=90, min_events=20,
                       output_path=None, verbose=True):
    """
    对地震目录进行网格化时空扫描，检测地震活动显著平静。

    参数
    ----------
    input_data : str, Path, or pd.DataFrame
        输入数据 (.eqt / .csv / DataFrame)
    grid_size : float
        网格大小（度），默认 1.0°
    mag_threshold : float or None
        平静分析震级下限，None 则自动估算 Mc
    method : str
        'dt' — 仅 D-T 统计法
        'zvalue' — 仅 Z值法
        'both' — 两种方法都使用
    do_remove_aftershocks : bool
        是否先删除余震（默认 True）
    sigma_mult : float
        D-T 法的 σ 倍乘系数（默认 2.0 = μ+2σ）
    min_gap_days : float
        D-T 法最短平静时长（天），低于此值不报告（默认 30 天）
    z_window : int
        Z值法滑动窗口（天），默认 180 天
    z_step : int
        Z值法时间步长（天），默认 30 天
    z_threshold : float
        Z值显著性阈值（默认 2.0）
    min_duration_days : float
        Z值法平静最短持续天数（默认 90 天）
    min_events : int
        网格最少事件数，低于此值跳过
    output_path : str or None
        结果输出 CSV 路径
    verbose : bool
        是否打印进度

    返回
    -------
    pd.DataFrame
        检测结果，每行一个平静时段。列:
        grid_lat, grid_lon, grid_w, grid_e, grid_s, grid_n,
        quiescence_start, quiescence_end, duration_days,
        threshold_days / z_peak, method, mc_used,
        mean_gap_days, std_gap_days, sigma_mult, p95_days (D-T),
        z_threshold, window_days, step_days (Z-value),
        last_event_mag, next_event_mag, last_event_time, next_event_time,
        n_events_grid, ongoing
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
    _col_map = {'lon': 'longitude', 'lng': 'longitude', 'lat': 'latitude',
                'mag': 'magnitude', 'm': 'magnitude'}
    df = df.rename(columns={c: _col_map[c] for c in df.columns if c.lower() in _col_map})

    # 仅保留年份 >= 1900
    if 'year' in df.columns:
        n_before = len(df)
        df = df[df['year'] >= 1900].copy()
        if verbose and n_before > len(df):
            print(f'[过滤] 去除 {n_before - len(df)} 条 1900 年前的记录')

    # 2. 构建 datetime
    years = df['year'].fillna(2000).astype(int)
    months = df['month'].fillna(1).astype(int).clip(1, 12)
    days = df['day'].fillna(1).astype(int).clip(1, 28)
    df['datetime'] = pd.to_datetime(
        dict(year=years, month=months, day=days), errors='coerce'
    )
    df = df.dropna(subset=['datetime'])
    if verbose:
        print(f'[目录] {len(df)} 条事件')

    # 3. 余震删除
    if do_remove_aftershocks:
        df = remove_aftershocks(df, verbose=verbose)

    # 4. 完整性震级
    if mag_threshold is None:
        mag_threshold = estimate_magnitude_completeness(df)
    if verbose:
        print(f'[震级下限] M ≥ {mag_threshold}')

    # 5. 构建网格
    lat_min, lat_max = np.floor(df['latitude'].min()), np.ceil(df['latitude'].max())
    lon_min, lon_max = np.floor(df['longitude'].min()), np.ceil(df['longitude'].max())

    lat_edges = np.arange(lat_min, lat_max + grid_size, grid_size)
    lon_edges = np.arange(lon_min, lon_max + grid_size, grid_size)

    n_grids = (len(lat_edges) - 1) * (len(lon_edges) - 1)
    if verbose:
        print(f'[网格] {grid_size}°×{grid_size}° 共 {n_grids} 个网格')
        print(f'[范围] 经度 {lon_min}–{lon_max}  纬度 {lat_min}–{lat_max}')
        mm = 'D-T + Z值' if method == 'both' else method.upper()
        print(f'[方法] {mm}  震级下限 M≥{mag_threshold}  最少 {min_events} 事件/网格')

    # 6. 网格扫描
    global_catalog_end = df['datetime'].max()
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

            n_above_mc = (grid_events['magnitude'] >= mag_threshold).sum()
            if n_above_mc < min_events / 2:
                continue

            # D-T 法
            if method in ('dt', 'both'):
                dt_results = _detect_quiescence_dt_grid(
                    grid_events, mag_threshold, sigma_mult=sigma_mult,
                    min_gap_days=min_gap_days, min_events=min_events,
                    global_catalog_end=global_catalog_end
                )
                for r in dt_results:
                    r['grid_lat'] = round((s + n) / 2, 2)
                    r['grid_lon'] = round((w + e) / 2, 2)
                    r['grid_w'] = w
                    r['grid_e'] = e
                    r['grid_s'] = s
                    r['grid_n'] = n
                    r['n_events_grid'] = len(grid_events)
                    r['mc_used'] = mag_threshold
                    all_results.append(r)

            # Z值法
            if method in ('zvalue', 'both'):
                z_results = _detect_quiescence_z_grid(
                    grid_events, mag_threshold,
                    window_days=z_window, step_days=z_step,
                    z_threshold=z_threshold,
                    min_events=min_events,
                    min_duration_days=min_duration_days
                )
                for r in z_results:
                    r['grid_lat'] = round((s + n) / 2, 2)
                    r['grid_lon'] = round((w + e) / 2, 2)
                    r['grid_w'] = w
                    r['grid_e'] = e
                    r['grid_s'] = s
                    r['grid_n'] = n
                    r['n_events_grid'] = len(grid_events)
                    r['mc_used'] = mag_threshold
                    all_results.append(r)

            if verbose and scanned % max(1, n_grids // 10) == 0:
                print(f'  扫描进度: {scanned}/{n_grids} ({scanned*100//n_grids}%)  '
                      f'已发现 {len(all_results)} 个平静时段')

    if verbose:
        print(f'[完成] 扫描 {scanned} 个网格，检测到 {len(all_results)} 个平静时段')

    # 7. 整理结果
    if not all_results:
        if verbose:
            print('[结果] 未检测到满足条件的地震活动显著平静')
        return pd.DataFrame()

    result_df = pd.DataFrame(all_results)
    # 按平静开始时间排序
    result_df = result_df.sort_values('quiescence_start').reset_index(drop=True)

    # 去重合并 → 构建空间连续平静区
    result_df = _build_quiescence_regions(result_df, grid_size)

    # 后验证：确保每个平静区内没有任何 ≥ 阈值的事件
    if len(result_df) > 0:
        result_df = _validate_regions_against_catalog(result_df, df, mag_threshold)

    if verbose and len(result_df) > 0:
        print(f'[去重后] {len(result_df)} 个独立平静时段')
        print()
        _print_summary(result_df)

    # 8. 保存
    if output_path:
        result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        if verbose:
            print(f'\n[保存] {output_path}')

    return result_df


def _build_quiescence_regions(df, grid_size, min_overlap_ratio=0.3):
    """
    将个体网格平静检测结果合并为空间连续的封闭平静区。

    使用空时联合聚类：两个网格属于同一平静区当且仅当：
    1. 空间相邻（共享网格边）
    2. 平静时段有足够重叠（≥ min_overlap_ratio × 较短时段长度）

    返回
    -------
    pd.DataFrame 每行一个平静区
    """
    if len(df) <= 1:
        if len(df) == 1:
            return _single_grid_to_region(df, grid_size)
        return df

    df = df.sort_values('quiescence_start').reset_index(drop=True)
    n = len(df)

    # ── 构建空时邻接矩阵 ──
    # i 和 j 相邻 ⇔ 网格相邻 且 时间段有显著重叠
    adj = {i: [] for i in range(n)}
    for a in range(n):
        ra = df.iloc[a]
        for b in range(a + 1, n):
            rb = df.iloc[b]

            # 空间相邻检查
            if not _cells_adjacent(
                ra['grid_w'], ra['grid_e'], ra['grid_s'], ra['grid_n'],
                rb['grid_w'], rb['grid_e'], rb['grid_s'], rb['grid_n']
            ):
                continue

            # 时间重叠检查
            a_start, a_end = ra['quiescence_start'], ra['quiescence_end']
            b_start, b_end = rb['quiescence_start'], rb['quiescence_end']
            overlap_days = (min(a_end, b_end) - max(a_start, b_start)).days
            shorter = min((a_end - a_start).days, (b_end - b_start).days)
            if shorter <= 0:
                continue
            if overlap_days < min_overlap_ratio * shorter:
                continue

            adj[a].append(b)
            adj[b].append(a)

    # ── DFS 找连通分量 ──
    used = set()
    components = []
    for start in range(n):
        if start in used:
            continue
        comp = []
        stack = [start]
        while stack:
            v = stack.pop()
            if v in used:
                continue
            used.add(v)
            comp.append(v)
            for nb in adj[v]:
                if nb not in used:
                    stack.append(nb)
        components.append(comp)

    # ── 每个分量 → 汇总为平静区 ──
    regions = []
    for comp in components:
        sub = df.iloc[comp]
        cells = []
        for _, row in sub.iterrows():
            cells.append({
                'w': row['grid_w'], 'e': row['grid_e'],
                's': row['grid_s'], 'n': row['grid_n'],
            })

        # 外边界
        boundary = _compute_region_boundary(cells)

        # 汇总指标
        region = {}
        region['quiescence_start'] = sub['quiescence_start'].min()
        region['quiescence_end'] = sub['quiescence_end'].max()
        region['duration_days'] = round(
            (region['quiescence_end'] - region['quiescence_start']) / np.timedelta64(1, 'D'), 1)
        region['mag_level'] = sub['mc_used'].iloc[0] if 'mc_used' in sub.columns else None
        region['n_grids'] = len(comp)
        region['n_events_region'] = sub['n_events_grid'].max() if 'n_events_grid' in sub.columns else 0
        region['region_boundary'] = boundary
        region['region_area_deg2'] = round(len(comp) * grid_size * grid_size, 2)

        # 合并方法标签
        methods = sub['method'].unique()
        region['method'] = '+'.join(sorted(set('+'.join(methods).split('+'))))

        # D-T 指标取最大
        if 'threshold_days' in sub.columns:
            region['threshold_days'] = sub['threshold_days'].max()
            region['mean_gap_days'] = sub['mean_gap_days'].max()
            region['std_gap_days'] = sub['std_gap_days'].max()
        if 'p95_days' in sub.columns:
            region['p95_days'] = sub['p95_days'].max()

        # Z值指标
        if 'z_peak' in sub.columns:
            region['z_peak'] = sub['z_peak'].max()

        # 事件指标
        if 'last_event_mag' in sub.columns:
            region['last_event_mag'] = sub['last_event_mag'].max()
        if 'next_event_mag' in sub.columns:
            region['next_event_mag'] = sub['next_event_mag'].max()

        regions.append(region)

    return pd.DataFrame(regions)


def _cells_adjacent(w1, e1, s1, n1, w2, e2, s2, n2):
    """判断两个网格是否空间上属于同一平静区（4连通相邻或同一网格）"""
    # 同一网格
    if (abs(w1 - w2) < 1e-6 and abs(e1 - e2) < 1e-6 and
        abs(s1 - s2) < 1e-6 and abs(n1 - n2) < 1e-6):
        return True
    # 水平相邻：纬度范围相同，经度方向首尾相接
    same_lat = abs(s1 - s2) < 1e-6 and abs(n1 - n2) < 1e-6
    h_adj = same_lat and (abs(e1 - w2) < 1e-6 or abs(e2 - w1) < 1e-6)
    # 垂直相邻：经度范围相同，纬度方向首尾相接
    same_lon = abs(w1 - w2) < 1e-6 and abs(e1 - e2) < 1e-6
    v_adj = same_lon and (abs(n1 - s2) < 1e-6 or abs(n2 - s1) < 1e-6)
    return h_adj or v_adj


def _single_grid_to_region(df, grid_size):
    """将单网格结果转为区域格式"""
    row = df.iloc[0].to_dict()
    w, e, s, n = row['grid_w'], row['grid_e'], row['grid_s'], row['grid_n']
    # 区域字段
    row['region_boundary'] = [(round(w, 2), round(s, 2)), (round(e, 2), round(s, 2)),
                               (round(e, 2), round(n, 2)), (round(w, 2), round(n, 2))]
    row['region_area_deg2'] = round(grid_size * grid_size, 2)
    row['n_grids'] = 1
    row['mag_level'] = row.get('mc_used')
    row['n_events_region'] = row.get('n_events_grid', 0)
    # 移除旧的网格专用字段（保持输出干净）
    for old_key in ['grid_w', 'grid_e', 'grid_s', 'grid_n', 'grid_lat', 'grid_lon']:
        row.pop(old_key, None)
    return pd.DataFrame([row])


def _compute_region_boundary(cells):
    """
    计算一组网格单元的外边界多边形。

    算法：
    - 每个网格有4条边，统计每条边被多少网格共享
    - 只被1个网格拥有的边 = 外边界边
    - 将外边界边首尾相连形成闭合多边形

    返回
    -------
    list of (lon, lat) — 有序的闭合多边形顶点
    """
    from collections import Counter

    # 收集所有边：((x1,y1), (x2,y2))
    edges = Counter()
    for c in cells:
        w, e, s, n = c['w'], c['e'], c['s'], c['n']
        # 四条边，统一用 (min_point, max_point) 作为key
        top = ((w, n), (e, n))
        right = ((e, s), (e, n))
        bottom = ((w, s), (e, s))
        left = ((w, s), (w, n))
        for edge in [top, right, bottom, left]:
            key = tuple(sorted(edge))  # 规一化
            edges[key] += 1

    # 外边界 = count == 1 的边
    boundary_edges = [list(k) for k, v in edges.items() if v == 1]

    if not boundary_edges:
        # 回退：返回所有网格的外包矩形
        all_w = min(c['w'] for c in cells)
        all_e = max(c['e'] for c in cells)
        all_s = min(c['s'] for c in cells)
        all_n = max(c['n'] for c in cells)
        return [(all_w, all_s), (all_e, all_s), (all_e, all_n), (all_w, all_n)]

    # 将边首尾相连成多边形
    vertices = []
    remaining = list(boundary_edges)
    current = remaining.pop(0)
    vertices.append(current[0])
    vertices.append(current[1])

    while remaining:
        last_pt = vertices[-1]
        found = False
        for i, edge in enumerate(remaining):
            if _pts_equal(edge[0], last_pt):
                vertices.append(edge[1])
                remaining.pop(i)
                found = True
                break
            elif _pts_equal(edge[1], last_pt):
                vertices.append(edge[0])
                remaining.pop(i)
                found = True
                break
        if not found:
            break

    # 去掉首尾重复
    if len(vertices) > 1 and _pts_equal(vertices[0], vertices[-1]):
        vertices.pop()

    return [(round(x, 2), round(y, 2)) for x, y in vertices]


def _pts_equal(p1, p2):
    """两点近似相等"""
    return abs(p1[0] - p2[0]) < 1e-6 and abs(p1[1] - p2[1]) < 1e-6


def _validate_regions_against_catalog(regions_df, catalog_df, mag_threshold):
    """
    验证每个平静区：在平静时段内，区域内不得有任何 ≥ 阈值的地震事件。

    若发现违规事件，将平静结束时间截断到第一个违规事件之前。
    若截断后持续天数不足 min_gap_days，则丢弃该平静区。
    """
    if len(regions_df) == 0:
        return regions_df

    catalog = catalog_df.copy()
    # 确保有 datetime
    if 'datetime' not in catalog.columns:
        years = catalog['year'].fillna(2000).astype(int)
        months = catalog['month'].fillna(1).astype(int).clip(1, 12)
        days = catalog['day'].fillna(1).astype(int).clip(1, 28)
        catalog['datetime'] = pd.to_datetime(
            dict(year=years, month=months, day=days), errors='coerce')

    valid_rows = []
    for i, region in regions_df.iterrows():
        q_start = region['quiescence_start']
        q_end = region['quiescence_end']

        # 获取区域空间范围
        boundary = region['region_boundary']
        if isinstance(boundary, str):
            import ast
            boundary = ast.literal_eval(boundary)
        if not boundary:
            valid_rows.append(region)
            continue

        lons = [p[0] for p in boundary]
        lats = [p[1] for p in boundary]
        w, e = min(lons), max(lons)
        s, n = min(lats), max(lats)

        # 查找平静时段内、区域范围内的 ≥ 阈值事件
        violators = catalog[
            (catalog['latitude'] >= s) & (catalog['latitude'] <= n) &
            (catalog['longitude'] >= w) & (catalog['longitude'] <= e) &
            (catalog['magnitude'] >= mag_threshold) &
            (catalog['datetime'] > q_start) & (catalog['datetime'] < q_end)
        ].sort_values('datetime')

        if len(violators) > 0:
            # 截断到第一个违规事件
            first_v = violators.iloc[0]
            new_end = first_v['datetime']
            new_duration = round((new_end - q_start) / np.timedelta64(1, 'D'), 1)

            # 检查截断后是否仍满足最小持续天数
            min_dur = region.get('min_gap_days', 30) if 'threshold_days' in region else 90
            if new_duration < 30:  # 硬下限30天
                continue  # 丢弃

            # 更新区域
            region_copy = region.copy()
            region_copy['quiescence_end'] = new_end
            region_copy['duration_days'] = new_duration
            region_copy['next_event_mag'] = first_v['magnitude']
            region_copy['next_event_time'] = first_v['datetime']
            region_copy['_truncated'] = True
            valid_rows.append(region_copy)
        else:
            valid_rows.append(region)

    result = pd.DataFrame(valid_rows)
    # 删除辅助列
    if '_truncated' in result.columns:
        result = result.drop(columns=['_truncated'])
    return result.reset_index(drop=True)


def _print_summary(df):
    """打印检测结果摘要（区域格式）。"""
    print(f'{"#":<4} {"开始":<12} {"结束":<12} {"持续/天":<9} {"震级档次":<10} '
          f'{"方法":<14} {"面积/deg²":<10} {"阈值":<10} {"前/后M":<12}')
    print('─' * 100)
    for i, (_, r) in enumerate(df.iterrows(), 1):
        s = str(r['quiescence_start'])[:10]
        e = str(r['quiescence_end'])[:10]
        mag = r.get('mag_level', '')
        mag_str = f'M≥{mag}' if mag else ''
        method = r.get('method', '')
        area = r.get('region_area_deg2', '')
        thresh = r.get('threshold_days', '')
        if pd.isna(thresh) or thresh == '':
            thresh = f'Z={r.get("z_peak", "")}'
        else:
            thresh = f'{thresh}d'
        last_m = r.get('last_event_mag', '')
        next_m = r.get('next_event_mag', '')
        if pd.isna(last_m):
            last_m = '?'
        if pd.isna(next_m):
            next_m = '—'
        mm = f'M{last_m}→M{next_m}'
        print(f'{i:<4} {s:<12} {e:<12} {r["duration_days"]:<9.0f} '
              f'{mag_str:<10} {method:<14} {str(area):<10} {str(thresh):<10} {mm:<12}')

        # 显示边界
        boundary = r.get('region_boundary', [])
        if isinstance(boundary, str):
            boundary = eval(boundary) if boundary else []
        if boundary:
            pts = ', '.join([f'({x:.1f},{y:.1f})' for x, y in boundary])
            print(f'    平静区边界({len(boundary)}顶点): {pts}')
        print()


# ═══════════════════════════════════════════════════════════
# 6. 命令行入口
# ═══════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description='检测地震活动显著平静（网格扫描）')
    parser.add_argument('input', type=str, help='输入文件 (.eqt / .csv)')
    parser.add_argument('-o', '--output', type=str, default=None, help='输出 CSV 路径')
    parser.add_argument('-g', '--grid-size', type=float, default=1.0, help='网格大小（度）')
    parser.add_argument('-m', '--method', type=str, default='both',
                        choices=['dt', 'zvalue', 'both'], help='检测方法')
    parser.add_argument('--mc', type=float, default=None, help='震级下限（不指定则自动估算）')
    parser.add_argument('--no-remove-aftershocks', action='store_true', help='不删除余震')
    parser.add_argument('--sigma-mult', type=float, default=2.0, help='D-T σ 倍乘系数')
    parser.add_argument('--min-gap-days', type=float, default=30, help='D-T 最短平静时长（天）')
    parser.add_argument('--z-window', type=int, default=180, help='Z值法滑动窗口（天）')
    parser.add_argument('--z-step', type=int, default=30, help='Z值法步长（天）')
    parser.add_argument('--z-threshold', type=float, default=2.0, help='Z值显著性阈值')
    parser.add_argument('--min-duration-days', type=float, default=90, help='Z值最短平静持续天数')
    parser.add_argument('--min-events', type=int, default=20, help='网格最少事件数')
    args = parser.parse_args()

    detect_quiescence(
        args.input,
        grid_size=args.grid_size,
        mag_threshold=args.mc,
        method=args.method,
        do_remove_aftershocks=not args.no_remove_aftershocks,
        sigma_mult=args.sigma_mult,
        min_gap_days=args.min_gap_days,
        z_window=args.z_window,
        z_step=args.z_step,
        z_threshold=args.z_threshold,
        min_duration_days=args.min_duration_days,
        min_events=args.min_events,
        output_path=args.output,
        verbose=True
    )


if __name__ == '__main__':
    main()
