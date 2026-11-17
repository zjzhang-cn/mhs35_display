# MHS35 独立显示程序

在 MHS35（MHS-3.5" RPi Display，ILI9486 + ADS7846 触摸，480×320）上显示**你指定的内容**。
程序直接写 Linux 帧缓冲（fbtft），不依赖 X11、Wayland 或 fbcp，可单独运行。

## 目录内容

```
mhs35_display/
├── mhs35disp.py          # 通用显示入口：指定文字/图片
├── mhs35weather.py       # 北京天气卡通显示入口，定时刷新
├── mhs35dash.py          # 多卡片仪表盘：天气/时间日历/主机信息，触摸切换
├── install.sh            # 独立安装/卸载 MHS35 overlay（不依赖 LCD-show）
├── overlays/
│   └── mhs35.dtbo        # MHS35 device-tree overlay
├── udev/
│   └── 99-mhs35-touch-ignore.rules  # 让桌面/libinput 忽略 ADS7846 触摸
├── mhs35fb/
│   ├── __init__.py
│   ├── framebuffer.py    # 帧缓冲探测、mmap、RGB565 输出
│   ├── render.py         # Pillow 文本/图片渲染
│   ├── weather.py        # 天气获取、卡通场景、缓存
│   ├── cards.py          # 时钟日历、主机信息、页面指示
│   └── touch.py          # ADS7846 触摸读取与点击检测
├── systemd/
│   ├── mhs35-weather.service
│   └── mhs35-dashboard.service
├── requirements.txt
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
- 安装 `udev/99-mhs35-touch-ignore.rules`，让桌面（libinput/Wayfire）忽略 ADS7846。触摸设备仍由 `mhs35dash` 直接读取，HDMI 桌面上的鼠标键盘不受影响。
- 安装后需要重启：`sudo reboot`；加 `--reboot` 可自动重启。
- 卸载后重启可恢复 HDMI 输出，并移除上述 udev 规则。

## 前置条件

1. MHS35 的 device-tree overlay 已启用。可以直接使用本目录自带脚本（不依赖 LCD-show）：

   ```bash
   cd mhs35_display
   sudo ./install.sh 90
   sudo reboot
   ```

   也可以使用 LCD-show 仓库的 `sudo ./MHS35-show 90`。重启后应出现 `fb_ili9486` 帧缓冲设备，通常为 `/dev/fb1`，分辨率 480×320。

2. Python 3 与 Pillow；numpy 可选（有则转换更快）：

   ```bash
   sudo apt install python3-pil python3-numpy
   ```

3. 当前用户需要能读写 `/dev/fbN`（`video` 组），否则用 `sudo` 运行。

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

# 列出帧缓冲设备（* 表示自动选中的 MHS35）
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
| `--preview PNG` | 只渲染到 PNG，不写屏 |
| `--list` | 列出帧缓冲设备 |
| `--demo` | 显示测试彩条 |
| `--quiet` | 不输出成功提示 |

## 天气模式（北京 · 卡通 · 定时刷新）

```bash
# 显示一帧后退出
python3 mhs35weather.py --once

# 不接屏，先生成 PNG 预览
python3 mhs35weather.py --preview weather.png

# 常驻运行，每 10 分钟刷新一次（默认）
python3 mhs35weather.py --interval 600

# 失败后 60 秒重试；网络不好时可调大 --timeout
python3 mhs35weather.py --interval 600 --retry 60 --timeout 10
```

画面内容：北京天气卡通场景（太阳/月亮、云朵、雨雪雷雾）、当前温度与天气、最高/最低温、湿度、风向风力、空气质量与 PM2.5、本机 IP 与网卡名、数据更新时间。

- 数据源：默认 `auto`，优先 `t.weather.itboy.net`（国内可直连），失败后尝试 Open-Meteo。
- 缓存：成功数据写入 `~/.cache/mhs35_weather.json`。断网时继续显示上次数据，并出现橙色 `离线 · 上次数据` 标记，恢复网络后自动刷新。
- 刷新间隔由 `--interval` 控制（默认 600 秒），失败重试由 `--retry` 控制（默认 60 秒）。
- 其他参数：`--provider itboy|open-meteo|auto`、`--lat`/`--lon`、`--font`、`--fb`、`--quiet`。

### 开机自动运行（systemd）

```bash
sudo cp ~/mhs35_display/systemd/mhs35-weather.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mhs35-weather
sudo systemctl status mhs35-weather
```

服务文件默认使用用户 `pi`、目录 `/home/pi/mhs35_display`；如不同请先修改。日志：`journalctl -u mhs35-weather -f`。

## 多卡片仪表盘（触摸切换）

```bash
python3 mhs35dash.py                 # 天气 → 时间日历 → 主机信息
python3 mhs35dash.py --start clock   # 从时钟卡片开始
python3 mhs35dash.py --preview dash.png --card host
```

- 在屏幕任意位置轻触，切换到下一张卡片；底部三个圆点指示当前页，左下角有“轻触切换”提示。
- 天气卡片：与 `mhs35weather.py` 相同的卡通场景，后台每 `--interval` 秒刷新；IP 只在主机卡片显示。
- 时间日历卡片：大号数字时钟（含秒）、日期/星期、当月日历，今天高亮。
- 主机信息卡片：主机名/核心数、IP/网卡、内核、CPU 温度、负载、内存、磁盘使用率、运行时长。
- 触摸自动查找 ADS7846 设备；可用 `--touch-device /dev/input/eventN`、`--no-touch`、`--touch-debug` 调试原始事件。
- 同一时间只能有一个程序写 `/dev/fb1`；运行仪表盘前先停掉天气服务。

### 开机自动运行（仪表盘）

```bash
sudo systemctl disable --now mhs35-weather
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
ssh pi@<pi-ip> 'python3 ~/mhs35_display/mhs35weather.py --once'
```

## 说明

- 自动探测顺序：优先 `ili9486`/`fbtft` 名称的设备，其次 480×320/320×480 的非 DRM 帧缓冲；不会误写 HDMI 的 `vc4drmfb`。
- 输出格式为 RGB565（16bpp），若帧缓冲为 32bpp 则按 BGRX 输出。
- 天气数据无需 API key，只需网络；Open-Meteo 在部分网络下不可达时会自动改用 itboy。
- 触摸输入（ADS7846）未包含在本程序中。
