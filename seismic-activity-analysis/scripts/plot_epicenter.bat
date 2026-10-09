@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================================
REM  Epicenter Distribution Map Script (GMT5)
REM
REM  Environment variables:
REM    GMT_INPUT      - input data file (space-separated: lon lat mag)
REM    GMT_OUTPUT     - output file path (without extension)
REM    GMT_REGION     - plot region (W/E/S/N)
REM    GMT_TITLE      - map title (optional)
REM    GMT_SHOW_TOPO  - show topography 1/0 (default 0)
REM    GMT_SHOW_FAULTS- show active faults 1/0 (default 1)
REM    GMT_PROJECTION - projection (default M6i)
REM ============================================================

REM -- defaults --
if "%GMT_PROJECTION%"=="" set GMT_PROJECTION=M6i
if "%GMT_SHOW_TOPO%"==""   set GMT_SHOW_TOPO=0
if "%GMT_SHOW_FAULTS%"=="" set GMT_SHOW_FAULTS=1
if "%GMT_TITLE%"==""       set GMT_TITLE=Epicenter Map

set R=%GMT_REGION%
set J=%GMT_PROJECTION%
set output=%GMT_OUTPUT%.ps
set pngoutput=%GMT_OUTPUT%.png
set eqdata=%GMT_INPUT%
set topodata=%GMT_DATADIR%\earth_relief_15s.grd

REM -- work in GMT data directory for GIS files --
pushd "%GMT_DATADIR%"

REM -- GMT style --
gmt gmtset MAP_FRAME_TYPE=plain
gmt gmtset MAP_TICK_LENGTH=-0.2c
gmt gmtset MAP_FRAME_PEN=0.65p
gmt gmtset FONT_ANNOT=10p,4
gmt gmtset FORMAT_GEO_MAP=ddd:mmF
gmt gmtset MAP_ANNOT_OFFSET=2p

REM -- init PS --
gmt psxy -R%R% -J%J% -T -K -P >"%output%"

REM -- topography (optional, slow) --
if "%GMT_SHOW_TOPO%"=="1" (
    echo   [GMT] Rendering topography...
    gmt grdcut %topodata% -R%R% -G"%TEMP%\cutTopo.grd"
    gmt grdgradient "%TEMP%\cutTopo.grd" -Ne0.7 -A50 -G"%TEMP%\cutTopo_i.grad"
    gmt makecpt -Cgray -T-60000/2000/500 -Z >"%TEMP%\colorTopo.cpt"
    gmt grdimage "%TEMP%\cutTopo.grd" -I"%TEMP%\cutTopo_i.grad" -R%R% -J%J% -C"%TEMP%\colorTopo.cpt" -E300 -K -O >>"%output%"
)

REM -- basemap frame --
gmt psbasemap -R%R% -J%J% -BWSen -Baf -K -O >>"%output%"

REM -- admin boundaries --
if exist xian.gmt   gmt psxy xian.gmt   -R%R% -J%J% -W0.1p,darkgrey -K -O >>"%output%"
if exist shi.gmt    gmt psxy shi.gmt    -R%R% -J%J% -W0.2p,black    -K -O >>"%output%"
if exist sheng.gmt  gmt psxy sheng.gmt  -R%R% -J%J% -W0.4p,black    -K -O >>"%output%"

REM -- city markers & labels --
if exist shenghuichengshi.gmt (
    gmt psxy shenghuichengshi.gmt -R%R% -J%J% -Sc5.5p -W0.5p,black -K -O >>"%output%"
    gmt pstext shenghuichengshi.gmt -R%R% -J%J% -Dj0.15c -F+f9p,36+jTC+h -K -O >>"%output%"
)
if exist dijichengshizhudi.gmt (
    gmt psxy dijichengshizhudi.gmt -R%R% -J%J% -Sc4p -W0.35p,black -K -O >>"%output%"
    gmt pstext dijichengshizhudi.gmt -R%R% -J%J% -Dj0.1c -F+f7p,36+jTC+h -K -O >>"%output%"
)
if exist xianzhu.gmt (
    gmt psxy xianzhu.gmt -R%R% -J%J% -Sc1p -W0.2p,black -K -O >>"%output%"
    gmt pstext xianzhu.gmt -R%R% -J%J% -Dj0.05c -F+f3p,36+jTC+h -K -O >>"%output%"
)

REM -- active faults (optional) --
if "%GMT_SHOW_FAULTS%"=="1" (
    if exist CN-faults.gmt gmt psxy CN-faults.gmt -R%R% -J%J% -W0.4p,red -K -O >>"%output%"
)

REM -- epicenters sized by magnitude --
if exist "%eqdata%" (
    gawk "{if($3>=7.0)                     print $1, $2}" "%eqdata%" | gmt psxy -R%R% -J%J% -Sc9p -W0.5p,black -Gred -K -O >>"%output%"
    gawk "{if($3>=6.0 && $3<7.0)          print $1, $2}" "%eqdata%" | gmt psxy -R%R% -J%J% -Sc7p -W0.5p,black -Gred -K -O >>"%output%"
    gawk "{if($3>=5.0 && $3<6.0)          print $1, $2}" "%eqdata%" | gmt psxy -R%R% -J%J% -Sc6p -W0.5p,black -Gred -K -O >>"%output%"
    gawk "{if($3>=4.0 && $3<5.0)          print $1, $2}" "%eqdata%" | gmt psxy -R%R% -J%J% -Sc5p -W0.5p,black -Gred -K -O >>"%output%"
    gawk "{if($3>=3.0 && $3<4.0)          print $1, $2}" "%eqdata%" | gmt psxy -R%R% -J%J% -Sc4p -W0.5p,black -Gred -K -O >>"%output%"
    gawk "{if($3>=2.0 && $3<3.0)          print $1, $2}" "%eqdata%" | gmt psxy -R%R% -J%J% -Sc3p -W0.5p,black -Gred -K -O >>"%output%"
    gawk "{if($3>=1.0 && $3<2.0)          print $1, $2}" "%eqdata%" | gmt psxy -R%R% -J%J% -Sc2p -W0.5p,black -Gred -K -O >>"%output%"
)

REM -- legend --
(
echo H 10 36 Legend
echo S 0.1i c 4.5p red black 0.2i  Earthquake
echo S 0.1i c 6p   red black 0.2i  Ms5.0-5.9
echo S 0.1i c 7p   red black 0.2i  Ms6.0-6.9
echo S 0.1i c 9p   red black 0.2i  Ms>=7.0
) >"%TEMP%\legend.txt"
if "%GMT_SHOW_FAULTS%"=="1" (
    echo S 0.1i - 30p red - 0.5i  Active Fault >>"%TEMP%\legend.txt"
)
gmt pslegend "%TEMP%\legend.txt" -R%R% -J%J% -DjBL+w3c --FONT_ANNOT_PRIMARY=7p,36 -F+p0.5p+gwhite -K -O >>"%output%"

REM -- title --
echo %GMT_TITLE% | gmt pstext -R%R% -J%J% -F+cTC+f12p,4,black -N -K -O >>"%output%"

REM -- finalize --
gmt psxy -R -J -T -O >>"%output%"

REM -- cleanup gmt temp files --
del /q gmt.* 2>nul

REM -- convert to PNG (600 dpi) --
gmt psconvert "%output%" -A -C-sFONTPATH=C:\Windows\Fonts -D. -E600 -Tg
if exist "%pngoutput%" (
    echo   [GMT] Done: %pngoutput%
) else (
    echo   [GMT] Warning: PNG conversion may have failed, PS saved: %output%
)

REM -- cleanup topography temp files --
del /q "%TEMP%\cutTopo.grd"    2>nul
del /q "%TEMP%\cutTopo_i.grad" 2>nul
del /q "%TEMP%\colorTopo.cpt"  2>nul
del /q "%TEMP%\legend.txt"     2>nul

popd
endlocal
