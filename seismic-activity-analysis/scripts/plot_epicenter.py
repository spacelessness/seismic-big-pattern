#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
震中分布图绘制脚本 (Python 封装)

通过动态生成 GMT 批处理脚本绘制带有地理投影的震中分布图。
支持 EQT、CSV、DataFrame 等多种输入格式。

可作为命令行工具使用，也可作为模块导入：

    from plot_epicenter import plot_epicenter
    plot_epicenter('catalog.eqt', 'output.png', region=(100, 120, 35, 45))

命令行用法：
    python plot_epicenter.py input.eqt -o output.png -r 100/120/35/45
"""

import sys
import os
import shutil
import tempfile
import subprocess
import argparse
from pathlib import Path
import pandas as pd


# ── GMT 路径 ──
_GMT_SHAREDIR = os.environ.get('GMT5_SHAREDIR', r'D:\Program Files\gmt5\share')
_GMT_BIN = str(Path(_GMT_SHAREDIR).parent / 'bin')
_GMT_EXE = os.path.join(_GMT_BIN, 'gmt.exe')
_GAWK_EXE = os.path.join(_GMT_BIN, 'gawk.exe')


def _parse_input(input_data):
    """将多种输入格式统一转为 DataFrame（需含 longitude/latitude/magnitude 列）。"""
    if isinstance(input_data, pd.DataFrame):
        df = input_data.copy()
    elif isinstance(input_data, (str, Path)):
        path = Path(input_data)
        if not path.exists():
            raise FileNotFoundError(f'输入文件不存在: {path}')
        if path.suffix.lower() == '.eqt':
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from read_eqt import read_eqt
            df = read_eqt(str(path))
        elif path.suffix.lower() == '.csv':
            try:
                df = pd.read_csv(path, encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(path, encoding='gbk')
        else:
            try:
                df = pd.read_csv(path, sep=r'\s+', encoding='utf-8')
            except Exception:
                raise ValueError(f'不支持的文件格式: {path.suffix}')
    else:
        raise TypeError(f'input_data 类型不支持: {type(input_data)}')

    _col_map = {
        'longitude': 'longitude', 'lon': 'longitude', 'lng': 'longitude',
        'latitude': 'latitude', 'lat': 'latitude',
        'magnitude': 'magnitude', 'mag': 'magnitude', 'm': 'magnitude',
    }
    df = df.rename(columns={c: _col_map[c] for c in df.columns
                             if c.lower() in _col_map})
    required = ['longitude', 'latitude', 'magnitude']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f'缺少必需的列: {missing}')
    return df


def _compute_region(lons, lats, pad=0.5):
    """从经纬度范围自动计算绘图区域，带边距。"""
    w = float(lons.min()) - pad
    e = float(lons.max()) + pad
    s = float(lats.min()) - pad
    n = float(lats.max()) + pad
    return (round(w, 2), round(e, 2), round(s, 2), round(n, 2))


def _find_gis_file(names, gis_dir):
    """在 GIS 目录中查找文件，返回第一个存在的路径。"""
    for name in names:
        p = Path(gis_dir) / name
        if p.exists():
            return str(p)
    return None


def _escape_batch(text):
    """转义批处理特殊字符，防止被 cmd 误解。"""
    for ch in ['%', '^', '&', '<', '>', '|', '!']:
        text = text.replace(ch, f'^{ch}')
    return text


def _generate_batch(gis_dir, xyz_path, output_base, region_str, title,
                    show_topo, show_faults, projection):
    """
    动态生成 GMT 批处理脚本（GBK 编码写入）。

    使用 pushd 切换到 GIS 数据目录，然后用裸中文文件名引用底图数据，
    完全模仿用户已验证可用的原始 bat 脚本结构。
    """
    gis = Path(gis_dir)
    topodata = gis / 'earth_relief_15s.grd'

    # 探测实际存在的 GIS 文件（用 Python 确认存在性，再用裸名写入 bat）
    gis_files = {}
    for key, names in [
        ('xian', ['xian.gmt']),
        ('shi', ['shi.gmt']),
        ('sheng', ['sheng.gmt']),
        ('shenghui', ['省会城市.gmt']),
        ('diji', ['地级城市驻地.gmt', '地级市驻地.gmt']),
        ('xiancheng', ['县城驻地.gmt']),
    ]:
        gis_files[key] = _find_gis_file(names, gis_dir)

    fault_names = []
    for n in ['CN-faults.gmt', '2010活动断层数据.TXT']:
        if (gis / n).exists():
            fault_names.append(n)

    # GhostScript 路径探测
    gs_candidates = [
        r'C:\DssTech\gs\gs9.26\bin\gswin64c.exe',
        r'C:\Program Files\gs\gs9.26\bin\gswin64c.exe',
        r'C:\Program Files\gs\bin\gswin64c.exe',
        r'C:\Program Files (x86)\gs\bin\gswin32c.exe',
    ]
    gs_path = ''
    for gs in gs_candidates:
        if Path(gs).exists():
            gs_path = gs
            break
    gs_flag = f' -G{gs_path}' if gs_path else ''

    lines = []
    A = lines.append
    gmt = _GMT_EXE
    gwk = _GAWK_EXE

    A('@echo off')
    A('setlocal')
    A(f'set R={region_str}')
    A(f'set J={projection}')
    A(f'set output={output_base}.ps')
    A(f'set eqdata={xyz_path}')
    A('')

    # 切换到 GIS 数据目录（关键：之后用裸文件名引用底图）
    A(f'pushd "{gis_dir}"')
    A('')

    # GMT 样式
    A(f'"{gmt}" gmtset MAP_FRAME_TYPE=plain MAP_TICK_LENGTH=-0.2c MAP_FRAME_PEN=0.65p')
    A(f'"{gmt}" gmtset FONT_ANNOT=10p,4 FORMAT_GEO_MAP=ddd:mmF MAP_ANNOT_OFFSET=2p')
    A('')

    # 初始化 PS
    A(f'"{gmt}" psxy -R%R% -J%J% -T -K -P >"%output%"')
    A('')

    # 地形（可选）
    if show_topo and topodata.exists():
        A('echo [GMT] Rendering topography...')
        A(f'"{gmt}" grdcut earth_relief_15s.grd -R%R% -G"%TEMP%\\_topo.grd"')
        A(f'"{gmt}" grdgradient "%TEMP%\\_topo.grd" -Ne0.7 -A50 -G"%TEMP%\\_topo_i.grad"')
        A(f'"{gmt}" makecpt -Cgray -T-60000/2000/500 -Z >"%TEMP%\\_topo.cpt"')
        A(f'"{gmt}" grdimage "%TEMP%\\_topo.grd" -I"%TEMP%\\_topo_i.grad" -R%R% -J%J% -C"%TEMP%\\_topo.cpt" -E300 -K -O >>"%output%"')
        A('')

    # 底图边框
    A(f'"{gmt}" psbasemap -R%R% -J%J% -BWSen -Baf -K -O >>"%output%"')
    A('')

    # 行政边界（裸文件名，pushd 后直接可用）
    for key, pen, fname in [
        ('xian', '0.1p,darkgrey', 'xian.gmt'),
        ('shi', '0.2p,black', 'shi.gmt'),
        ('sheng', '0.4p,black', 'sheng.gmt'),
    ]:
        if gis_files.get(key):
            A(f'"{gmt}" psxy {fname} -R%R% -J%J% -W{pen} -K -O >>"%output%"')
    A('')

    # 城市点位 + 标注
    if gis_files.get('shenghui'):
        A(f'"{gmt}" psxy 省会城市.gmt -R%R% -J%J% -Sc5.5p -W0.5p,black -K -O >>"%output%"')
        A(f'"{gmt}" pstext 省会城市.gmt -R%R% -J%J% -Dj0.15c -F+f9p,36+jTC+h -K -O >>"%output%"')
    if gis_files.get('diji'):
        # 用探测到的实际文件名
        dijifile = Path(gis_files['diji']).name
        A(f'"{gmt}" psxy {dijifile} -R%R% -J%J% -Sc4p -W0.35p,black -K -O >>"%output%"')
        A(f'"{gmt}" pstext {dijifile} -R%R% -J%J% -Dj0.1c -F+f7p,36+jTC+h -K -O >>"%output%"')
    if gis_files.get('xiancheng'):
        A(f'"{gmt}" psxy 县城驻地.gmt -R%R% -J%J% -Sc1p -W0.2p,black -K -O >>"%output%"')
        A(f'"{gmt}" pstext 县城驻地.gmt -R%R% -J%J% -Dj0.05c -F+f3p,36+jTC+h -K -O >>"%output%"')
    A('')

    # 活动断裂
    if show_faults:
        for fn in fault_names:
            A(f'"{gmt}" psxy "{fn}" -R%R% -J%J% -W0.4p,red -K -O >>"%output%"')
        A('')

    # 震中（按震级分档）
    A(f'"{gwk}" "{{if($3>=7.0) print $1, $2}}" "%eqdata%" | "{gmt}" psxy -R%R% -J%J% -Sc9p -W0.5p,black -Gred -K -O >>"%output%"')
    A(f'"{gwk}" "{{if($3>=6.0&&$3<7.0) print $1, $2}}" "%eqdata%" | "{gmt}" psxy -R%R% -J%J% -Sc7p -W0.5p,black -Gred -K -O >>"%output%"')
    A(f'"{gwk}" "{{if($3>=5.0&&$3<6.0) print $1, $2}}" "%eqdata%" | "{gmt}" psxy -R%R% -J%J% -Sc6p -W0.5p,black -Gred -K -O >>"%output%"')
    A(f'"{gwk}" "{{if($3>=4.0&&$3<5.0) print $1, $2}}" "%eqdata%" | "{gmt}" psxy -R%R% -J%J% -Sc5p -W0.5p,black -Gred -K -O >>"%output%"')
    A(f'"{gwk}" "{{if($3>=3.0&&$3<4.0) print $1, $2}}" "%eqdata%" | "{gmt}" psxy -R%R% -J%J% -Sc4p -W0.5p,black -Gred -K -O >>"%output%"')
    A(f'"{gwk}" "{{if($3>=2.0&&$3<3.0) print $1, $2}}" "%eqdata%" | "{gmt}" psxy -R%R% -J%J% -Sc3p -W0.5p,black -Gred -K -O >>"%output%"')
    A('')

    # 图例
    leg = '%TEMP%\\_legend.txt'
    A(f'(echo H 10 36 Legend')
    A(f'echo S 0.1i c 4.5p red black 0.2i  Earthquake')
    A(f'echo S 0.1i c 6p   red black 0.2i  Ms5.0-5.9')
    A(f'echo S 0.1i c 7p   red black 0.2i  Ms6.0-6.9')
    A(f'echo S 0.1i c 9p   red black 0.2i  Ms>=7.0')
    if show_faults:
        A(f'echo S 0.1i - 30p red - 0.5i  Active Fault')
    A(f') >"{leg}"')
    A(f'"{gmt}" pslegend "{leg}" -R%R% -J%J% -DjBL+w3c --FONT_ANNOT_PRIMARY=7p,36 -F+p0.5p+gwhite -K -O >>"%output%"')
    A('')

    # 标题
    A(f'echo {_escape_batch(title)} | "{gmt}" pstext -R%R% -J%J% -F+cTC+f12p,4,black -N -K -O >>"%output%"')
    A('')

    # 收尾
    A(f'"{gmt}" psxy -R -J -T -O >>"%output%"')
    A('del /q gmt.* 2>nul')
    A('')

    # 返回工作目录，PNG 转换（不用 -A，已在某些 PS 内容下导致黑图）
    A('popd')
    A(f'"{gmt}" psconvert "%output%" -C-sFONTPATH=C:\\Windows\\Fonts -D. -E600 -Tg{gs_flag}')
    A('if exist "map.png" (echo [GMT] Done) else (echo [GMT] Warning: PNG may have failed)')

    # 清理
    A('del /q "%TEMP%\\_topo.grd" 2>nul')
    A('del /q "%TEMP%\\_topo_i.grad" 2>nul')
    A('del /q "%TEMP%\\_topo.cpt" 2>nul')
    A(f'del /q "{leg}" 2>nul')
    A('endlocal')

    return '\r\n'.join(lines)


def plot_epicenter(input_data, output_path, region=None, title='震中分布图',
                   mag_min=None, mag_max=None, show_topo=False, show_faults=True,
                   projection='M6i', gis_dir=None, verbose=True):
    """
    绘制震中分布图。

    参数
    ----------
    input_data : str, Path, or pd.DataFrame
        输入数据：.eqt / .csv 文件路径，或含 lon/lat/mag 列的 DataFrame
    output_path : str or Path
        输出 PNG 文件路径
    region : tuple (w, e, s, n) or None
        绘图区域，None 则自动推算
    title : str
        地图标题
    mag_min, mag_max : float or None
        震级筛选
    show_topo : bool
        是否渲染地形底图（耗时长）
    show_faults : bool
        是否叠加活动断裂
    projection : str
        GMT 投影，默认 'M6i'
    gis_dir : str or None
        GIS 底图目录，默认 $GMT_DATADIR
    verbose : bool
        打印进度信息

    返回
    -------
    Path
        输出 PNG 文件路径
    """
    # 1. 解析输入
    df = _parse_input(input_data)

    # 2. 震级筛选
    if mag_min is not None:
        df = df[df['magnitude'] >= mag_min]
    if mag_max is not None:
        df = df[df['magnitude'] <= mag_max]
    if len(df) == 0:
        raise ValueError('筛选后无数据')

    # 3. 区域
    if region is None:
        region = _compute_region(df['longitude'], df['latitude'])
        if verbose:
            print(f'[区域] {region[0]}/{region[1]}/{region[2]}/{region[3]}')
    region_str = f'{region[0]}/{region[1]}/{region[2]}/{region[3]}'

    # 4. 输出路径（用临时目录避免中文路径导致 GMT psconvert 失败）
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix='gmt_'))
    work_base = str(work_dir / 'map')
    final_png = output_path
    final_ps = output_path.with_suffix('.ps')

    # 5. GIS 目录
    if gis_dir is None:
        gis_dir = os.environ.get('GMT_DATADIR', r'E:\GMT_DATEBASE')

    # 6. 写 XYZ 数据 (lon lat mag)
    xyz_path = output_path.with_suffix('.xyz')
    df[['longitude', 'latitude', 'magnitude']].to_csv(
        xyz_path, sep=' ', index=False, header=False, encoding='utf-8'
    )

    # 7. 动态生成批处理脚本（GBK 编码，含中文文件名）
    bat_content = _generate_batch(
        gis_dir=gis_dir, xyz_path=str(xyz_path), output_base=work_base,
        region_str=region_str, title=title, show_topo=show_topo,
        show_faults=show_faults, projection=projection
    )
    bat_path = work_dir / 'plot.bat'
    with open(bat_path, 'w', encoding='gbk') as f:
        f.write(bat_content)

    # 8. 执行批处理（在临时工作目录中运行，避免中文路径问题）
    if verbose:
        print(f'[绘图] 区域={region_str}  事件={len(df)}  '
              f'震级=M{df["magnitude"].min():.1f}-M{df["magnitude"].max():.1f}')

    result = subprocess.run(
        ['cmd', '/c', str(bat_path)],
        capture_output=True,
        timeout=600,
        cwd=str(work_dir)
    )
    stdout_str = result.stdout.decode('gbk', errors='replace').strip()
    stderr_str = result.stderr.decode('gbk', errors='replace').strip()

    if verbose and stdout_str:
        for line in stdout_str.split('\n'):
            if line.strip():
                print(f'  {line.strip()}')
    if result.returncode != 0 and stderr_str:
        print(f'[GMT stderr] {stderr_str}', file=sys.stderr)

    # 9. 收集结果并清理
    xyz_path.unlink(missing_ok=True)

    work_png = Path(f'{work_base}.png')
    work_ps = Path(f'{work_base}.ps')

    if work_png.exists():
        shutil.copy2(work_png, final_png)
        if verbose:
            print(f'[完成] {final_png}')
        result_path = final_png
    elif work_ps.exists():
        shutil.copy2(work_ps, final_ps)
        if verbose:
            print(f'[警告] PNG 转换失败，PS 已保存: {final_ps}')
        result_path = final_ps
    else:
        bat_path_debug = output_path.with_suffix('.bat')
        shutil.copy2(bat_path, bat_path_debug)
        result_path = None

    # 清理工作目录
    shutil.rmtree(work_dir, ignore_errors=True)

    if result_path is None:
        raise RuntimeError(f'绘图失败。调试用批处理: {bat_path_debug}\nstderr: {stderr_str}')
    return result_path


def main():
    parser = argparse.ArgumentParser(description='绘制震中分布图（GMT 引擎）')
    parser.add_argument('input', type=str, help='输入文件 (.eqt / .csv)')
    parser.add_argument('-o', '--output', type=str, required=True, help='输出 PNG 路径')
    parser.add_argument('-r', '--region', type=str, default=None,
                        help='绘图区域 西/东/南/北，省略则自动')
    parser.add_argument('-t', '--title', type=str, default='震中分布图')
    parser.add_argument('--mag-min', type=float, default=None)
    parser.add_argument('--mag-max', type=float, default=None)
    parser.add_argument('--topo', action='store_true', help='显示地形底图')
    parser.add_argument('--no-faults', action='store_true', help='不显示断裂')
    parser.add_argument('-p', '--projection', type=str, default='M6i')
    args = parser.parse_args()

    region = None
    if args.region:
        parts = args.region.split('/')
        if len(parts) != 4:
            print('错误: --region 格式应为 西/东/南/北', file=sys.stderr)
            sys.exit(1)
        region = tuple(float(p) for p in parts)

    plot_epicenter(
        args.input, args.output,
        region=region, title=args.title,
        mag_min=args.mag_min, mag_max=args.mag_max,
        show_topo=args.topo, show_faults=not args.no_faults,
        projection=args.projection
    )


if __name__ == '__main__':
    main()
