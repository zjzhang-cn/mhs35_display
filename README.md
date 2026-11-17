# MHS35 独立显示程序

在 MHS35（MHS-3.5" RPi Display，ILI9486 + ADS7846 触摸，480×320）上显示**你指定的内容**。
程序直接写 Linux 帧缓冲（fbtft），不依赖 X11、Wayland 或 fbcp，可单独运行。

## 目录内容

```
mhs35_display/
├── mhs35disp.py          # 通用显示入口：指定文字/图片
├── mhs35dash.py          # 多卡片仪表盘：天气/时间日历/主机信息，触摸切换
├── install.sh            # 独立安装/卸载 MHS35 overlay（不依赖 LCD-show）
├── overlays/
│   └── mhs35.dtbo        # MHS35 device-tree overlay
├── udev/
│   └── 99-mhs35-touch-ignore.rules  # 让桌面/libinput 忽略 SPI 触摸
├── mhs35fb/
│   ├── __init__.py
│   ├── framebuffer.py    # 帧缓冲探测、mmap、RGB565 输出
│   ├── render.py         # Pillow 文本/图片渲染
│   ├── weather.py        # 天气门面与运行循环
│   ├── weather_model.py  # 天气数据模型与位置常量
│   ├── weather_providers.py  # CMA/itboy/Open-Meteo/AQ 与合并
│   ├── weather_display.py    # 天气卡通场景与面板渲染
│   ├── weather_cache.py  # 天气缓存
│   ├── net.py            # 主机信息 IP 辅助
│   ├── cards.py          # 时钟日历、主机信息、页面指示
│   └── touch.py          # SPI 触摸读取与点击检测
├── systemd/
│   └── mhs35-dashboard.service
├── requirements.txt
├── AGENTS.md             # 维护与开发约定
└── README.md
```

## 安装/卸载显示驱动（独立于 LCD-show）

`install.sh` 只做显示所需的 overlay、SPI 和旋转配置，不安装 X11 校准、fbturbo 或 fbcp，适合配合本项目的帧缓冲程序使用。

```bash
sudo ./install.sh              # 默认 rotate=90
sudo ./install.sh 0            # 其他旋转：0/90/180/270
sudo ./install.sh --dry-run    # 只查看将要执行的修改
sudo ./install.sh --uninstall  # 移除 overlay 行和 mhs35.dtbo
sudo ./install.sh --install-deps   # 同时安装 python3-pil / python3-numpy
```

- 安装前会把 `/boot/firmware/config.txt`（旧系统为 `/boot/config.txt`）备份为 `config.txt.bak-mhs35-<时间>`。
- 自动启用 `dtparam=spi=on`，复制 `overlays/mhs35.dtbo`，写入 `dtoverlay=mhs35:rotate=90`。
- 安装 `udev/99-mhs35-touch-ignore.rules`，让使用 libinput 的桌面环境（如 Wayfire）忽略 SPI0 CS1 触摸。触摸设备仍由 `mhs35dash` 直接读取，HDMI 桌面上的鼠标键盘不受影响。
- 安装后需要重启：`sudo reboot`；加 `--reboot` 可自动重启。
- 卸载后重启可恢复 HDMI 输出，并移除上述 udev 规则。

## 前置条件

1. MHS35 的 device-tree overlay 已启用。可以直接使用本目录自带脚本（不依赖 LCD-show）：

   ```bash
   cd mhs35_display
   sudo ./install.sh 90
   sudo reboot
   ```

   也可以使用 LCD-show 仓库的 `sudo ./MHS35-show 90`。重启后应出现面板的帧缓冲设备（通常为 `/dev/fb0` 或 `/dev/fb1`），分辨率 480×320。

2. Python 3 与 Pillow；numpy 可选（有则转换更快）：

   ```bash
   sudo apt install python3-pil python3-numpy
   ```

3. 当前用户需要能读写 `/dev/fbN`（`video` 组）和 `/dev/input/event*`（`input` 组）；权限不足时用 `sudo` 运行。

## 用法

```bash
# 显示两行文字
python3 mhs35disp.py "Hello" "MHS35 480x320"

# 指定颜色、字号、对齐
python3 mhs35disp.py --text "温度: 42C" --text "状态: 正常" \
    --bg '#101820' --fg '#00ff88' --font-size 32

# 显示图片，并在上方叠加文字
python3 mhs35disp.py --image logo.png --fit contain --text "Booting..."

# 从文件读取内容
printf 'Line 1\nLine 2\n' > status.txt
python3 mhs35disp.py --text-file status.txt

# 列出帧缓冲设备（* 表示自动选中的 MHS35，含 SPI bus/address）
python3 mhs35disp.py --list

# 显示测试彩条
python3 mhs35disp.py --demo

# 没有接屏或 overlay 未启用时，先渲染成 PNG 检查效果
python3 mhs35disp.py --demo --preview demo.png
python3 mhs35disp.py "你好" --preview hello.png --size 480x320
```

显示完成后程序即退出，屏幕会保留最后一帧。

### 常用参数

| 参数 | 说明 |
| --- | --- |
| `--text LINE` | 追加一行文字，可重复 |
| `--text-file PATH` | 从 UTF-8 文件读取文字行，可重复 |
| `--image PATH` | 背景图片 |
| `--fit contain\|cover\|stretch` | 图片适配方式，默认 `contain` |
| `--bg / --fg COLOR` | 背景色 / 文字色，支持 `#RRGGBB` 或颜色名 |
| `--font PATH` | 指定 TTF 字体；默认自动选择，含中文时优先 DroidSansFallback |
| `--font-size PX` | 字号；过大会自动缩小以适配屏幕 |
| `--align / --valign` | 水平 / 垂直对齐 |
| `--rotate 0\|90\|180\|270` | 内容顺时针旋转（overlay 已按 90° 配置时可保持 0） |
| `--fb PATH` | 手动指定帧缓冲，默认自动探测 |
| `--size WxH` | 仅用于 `--preview` 的渲染尺寸，默认自动探测（不可用时为 480x320） |
| `--preview PNG` | 只渲染到 PNG，不写屏 |
| `--list` | 列出帧缓冲设备 |
| `--demo` | 显示测试彩条 |
| `--quiet` | 不输出成功提示 |

## 天气卡片与数据源

天气显示由 `mhs35dash.py` 的天气卡片提供，可先渲染预览：

```bash
python3 mhs35dash.py --preview weather.png --card weather
```

画面内容：北京天气卡通场景（太阳/月亮、云朵、雨雪雷雾）、当前温度与天气、最高/最低温、湿度、风向风力、空气质量与 PM2.5、数据更新时间。天空配色按本地时间在清晨、白天、黄昏、夜晚之间切换；本机 IP 只在仪表盘的主机信息卡片中显示。

- 数据源：默认 `auto`，优先 `weather.cma.cn`（中国气象局，北京站 `54511`）；失败或关键字段不全时按 itboy → Open-Meteo 回退。
- 空气质量：天气源不含 PM2.5 时（CMA / Open-Meteo），先请求 itboy，失败后再请求 `air-quality-api.open-meteo.com`；PM2.5 按中国浓度标准换算等级，空气质量请求失败不影响天气显示。
- 缓存：成功数据写入 `$XDG_CACHE_HOME/mhs35_weather.json`（默认 `~/.cache/mhs35_weather.json`）。断网时继续显示上次数据，并出现橙色 `离线 · 上次数据` 标记，恢复网络后自动刷新。
- 刷新间隔由 `mhs35dash.py --interval` 控制（默认 600 秒），失败重试由 `--retry` 控制（默认 60 秒）。
- 其他参数：`--provider cma|itboy|open-meteo|auto`、`--lat`/`--lon`、`--size`、`--font`、`--fb`、`--quiet`。
- `--lat`/`--lon` 只对 Open-Meteo 生效（CMA 使用固定站号 `54511`，itboy 固定为北京），画面中的城市名固定显示“北京”。

## 多卡片仪表盘（触摸切换）

```bash
python3 mhs35dash.py                 # 天气 → 时间日历 → 主机信息
python3 mhs35dash.py --start clock   # 从时钟卡片开始
python3 mhs35dash.py --preview dash.png --card host
```

- 在屏幕任意位置轻触，切换到下一张卡片；底部三个圆点指示当前页，左下角有“轻触切换”提示。
- 天气卡片：北京天气卡通场景，后台每 `--interval` 秒刷新；IP 只在主机卡片显示。
- 时间日历卡片：大号数字时钟（含秒）、日期/星期、当月日历，今天高亮。
- 主机信息卡片：主机名/核心数、IP/网卡、内核、CPU 温度、负载、内存、磁盘使用率、运行时长。
- 天气刷新参数：`--interval`（默认 600）、`--retry`（默认 60）、`--timeout`（默认 8）、`--provider`、`--lat`/`--lon`。
- 触摸自动查找 SPI0 CS1（bus address `spi0.1`）上同时具备 ABS_X/ABS_Y 和按下能力（压力轴或 `BTN_TOUCH`）的输入设备，不按设备名匹配；可用 `--touch-device /dev/input/eventN`、`--no-touch`、`--touch-debug` 调试原始事件。
- 同一时间只能有一个程序写 `/dev/fbN`；运行仪表盘前先停掉其他写屏程序。

### 开机自动运行（仪表盘）

```bash
sudo cp ~/mhs35_display/systemd/mhs35-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mhs35-dashboard
sudo systemctl status mhs35-dashboard
```

日志：`journalctl -u mhs35-dashboard -f`。

## 部署到 Pi

```bash
scp -r mhs35_display pi@<pi-ip>:~/
ssh pi@<pi-ip> 'python3 ~/mhs35_display/mhs35disp.py "Hello MHS35"'
```

## 说明

- 自动探测：只选择 SPI0 CS0（bus address `spi0.0`）上的 480×320/320×480 帧缓冲，判断依据是 `/sys/class/graphics/fbN` 的 bus/address，不按设备名称匹配；DRM/HDMI 帧缓冲不会被写入。
- 触摸设备同样按 SPI0 CS1（`spi0.1`）识别；显示设备不在 `spi0.0` 或触摸设备不在 `spi0.1` 时，可分别用 `--fb` / `--touch-device` 手动指定。
- 输出格式为 RGB565（16bpp），若帧缓冲为 32bpp 则按 BGRX 输出。
- 天气数据无需 API key，只需网络；默认 `auto` 先请求 CMA，失败或字段不全时依次尝试 itboy 和 Open-Meteo；`--provider` 可强制单一数据源（此时没有回退）。
- CMA 默认使用北京站 `54511`；其他城市可修改 `mhs35fb/weather.py` 中的 `CMA_STATION_ID`。
- PM2.5 等级按中国标准由浓度换算：≤35 优、≤75 良、≤115 轻度污染、≤150 中度污染、≤250 重度污染，更高为严重污染。
- `weather.cma.cn` 在部分网络下可能触发访问校验；此时 `auto` 会自动回退到 itboy / Open-Meteo。
- 触摸输入未包含在 `mhs35disp.py` 中。
