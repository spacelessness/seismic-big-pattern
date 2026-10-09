# 本地专用数据（不推送数据文件）

`data/local/` 除本文件外均被 Git 忽略。这里用于需要申请、许可不明、仅限内部研究或体积较大的文件。

首次收集已下载、逐字节锁定并验证 GMT 中文社区的 7 个文件（约 40 MB）：CAFD 断层、3 个地块边界、2 个行政边界文件和十段线。它们未被复制进可再分发目录。克隆仓库后请自行恢复：

```bash
python scripts/fetch_public_data.py --include-local --acknowledge-terms
python scripts/validate_public_data.py --include-local
```

这里的 `--acknowledge-terms` 仅表示已阅读上游说明，并非获得商业使用或再分发授权。若用途不获允许，不应下载/使用。若以后得到明确的数据许可或权利人授权，应先记录依据，再决定是否入库。

详细来源、限制、官方申请方法见 [中国官方数据说明](../../docs/china-official-data.md)。官方原始行政边界建议放在 `official-admin/`，大型地形或其他外部产品可放在各自子目录；不要用 `git add -f` 将这些文件直接强推入库。
