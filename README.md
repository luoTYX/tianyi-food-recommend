# 天依美食雷达 🍜

> 「不知道吃啥……雷达扫一下！」—— 洛天依

手机常驻上传定位 → 群聊里喊一声 → 天依帮你用高德地图找附近好吃的。

---

## 怎么工作的

```
手机(App/Tasker) ──定时POST位置──→ 服务器(Python HTTP)
                                      │
群友：找吃的 / 想吃火锅 ────────────→ AstrBot 插件
                                      │
                                      ├── 拉取最新定位（或群友指定地点）
                                      ├── 调高德 API 搜周边餐厅
                                      └── 天依语气回复，带导航链接
```

---

## 项目结构

```
├── server/                    # 位置接收服务 (Python, 零依赖)
│   └── server.py
├── plugin/food_recommend/     # AstrBot 插件
│   ├── main.py                # 核心逻辑
│   ├── metadata.yaml
│   ├── _conf_schema.json      # WebUI 可配置
│   └── requirements.txt
├── android_app/               # Android 定位上传 App
│   └── app/src/main/java/com/tianyi/radar/
│       ├── MainActivity.java
│       └── LocationService.java
├── tasker/                    # Tasker 配置（备选方案）
│   ├── UploadLocation.tsk.xml
│   └── TimedTrigger.prf.xml
└── README.md
```

---

## 一、部署定位服务器

### 要求
- Linux 服务器（CentOS/Ubuntu/Alibaba Cloud Linux 均可）
- Python 3.6+
- 开放 80/443 端口（或通过 nginx 反代）

### 步骤

**1. 上传代码**

把 `server/server.py` 放到服务器任意目录，比如 `/home/admin/tianyi_radar/`。

**2. 启动服务**

```bash
cd /home/admin/tianyi_radar
nohup python3 server.py > /tmp/tianyi.log 2>&1 &
```

服务监听 `0.0.0.0:8899`，提供以下接口：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/location` | POST | Tasker/App 上传位置 |
| `/api/location/latest?secret=xxx` | GET | 获取最新位置 |
| `/api/health` | GET | 健康检查 |

**3. 配置 nginx 反代（推荐）**

在 nginx 配置的 server 块中添加：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8899/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

这样就能通过 `http://你的服务器/api/` 访问位置服务。

**4. （可选）systemd 自启**

```bash
sudo ln -s /home/admin/tianyi_radar/tianyi-radar.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tianyi-radar
sudo systemctl start tianyi-radar
```

---

## 二、安装 AstrBot 插件

### 方式 A：WebUI 上传

1. 把 `plugin/food_recommend/` 下四个文件打成 zip（文件平铺在zip根目录，不套文件夹）
2. AstrBot WebUI → 插件管理 → 上传安装
3. 启用插件

### 方式 B：手动放置

```bash
cp -r plugin/food_recommend AstrBot/data/plugins/tianyi_food_recommend
docker restart astrbot_xxx  # 或用 WebUI 重载插件
```

### 配置插件

在 WebUI 插件设置中填写：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `amap_key` | 高德「Web服务」API Key | 必填 |
| `location_server` | 定位服务器地址 | `http://8.130.43.250` |
| `location_secret` | 共享密钥 | 和 server.py 里的 `SECRET` 一致 |
| `search_radius` | 搜索半径(米) | 1500 |
| `result_count` | 返回几条结果 | 5 |

> **高德 Key 申请：** https://console.amap.com/dev/key/app → 创建应用 → 服务平台选「**Web服务**」→ 获取 Key

---

## 三、手机端定位上传

### 推荐：天依雷达 App

已编译好 APK 在项目根目录。

1. 安装 `天依雷达.apk`
2. 打开后授予定位权限（需要「始终允许」后台定位）
3. 调节上传间隔（默认15分钟）
4. 打开开关 → 通知栏显示「天依雷达」即为运行中
5. 点「测试上传」可以立刻传一次验证

**省电技巧：** 间隔调到 30-60 分钟；室内用「仅网络定位」可进一步省电（改代码中 `GPS_PROVIDER` 为 `NETWORK_PROVIDER`）。

### 备选：Tasker

导入 `tasker/` 目录下的两个 xml：
- `UploadLocation.tsk.xml`（获取GPS + POST）
- `TimedTrigger.prf.xml`（每5分钟触发）

### 备选：GPSLogger

| 设置 | 值 |
|------|-----|
| URL | `http://你的服务器/api/location` |
| HTTP方法 | POST |
| Content-Type | `application/json` |
| 请求体 | `{"lat":%LAT,"lng":%LON,"accuracy":%ACC,"secret":"tianyi_food_radar_2024"}` |
| 信任自签证书 | 开启 |

---

## 四、群聊使用

| 说 | 效果 |
|---|---|
| `找吃的` | 用手机定位搜附近美食 |
| `找吃的 徐家汇` | 搜徐家汇附近美食 |
| `想吃火锅` | 搜附近火锅 |
| `想吃奶茶 静安寺` | 搜静安寺附近奶茶店 |
| `附近有什么好吃的推荐` | 自动触发搜索 |
| `我在哪` | 查看定位状态 |

每条推荐包含：店名、评分、距离、人均消费、地址、高德导航链接。

---

## 五、架构说明

```
┌─────────────────────────────────────────────────────────┐
│                      服务器 (8.130.43.250)                │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │ nginx :80/443│───→│ server.py    │  ← 零依赖 HTTP    │
│  │ /api/* 反代   │    │ :8899        │     存最新一条位置  │
│  └──────────────┘    └──────────────┘                   │
│         ↑                        ↑                      │
│         │                        │                      │
│  ┌──────┴──────┐         ┌──────┴──────────────────┐   │
│  │ AstrBot容器  │         │ 手机 App (LocationManager)│   │
│  │ food插件     │         │ 原生API，不用Google服务   │   │
│  │ 高德API调用  │         │ 间隔可调，WakeLock防休眠  │   │
│  └─────────────┘         └─────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**安全性说明：**
- 定位数据只存最新一条，不保留历史轨迹
- 接口有简单共享密钥校验
- 建议生产环境加 HTTPS + 更严格的鉴权

---

## 六、开发

```bash
# 服务端本地跑
cd server && python3 server.py

# 插件调试：放到 AstrBot 的 data/plugins/ 下即可

# Android App 编译
# 用 Android Studio 打开 android_app/ → Build → APK
# 或用命令行（需 JDK 21 + Android SDK）：
export JAVA_HOME=/path/to/jdk
cd android_app && ./gradlew assembleDebug
```

---

## 七、常见问题

**Q: 手机 App 闪退？**
A: 检查定位权限是否授予。华为/鸿蒙设备需手动去「设置→应用→天依雷达→权限」开启「位置信息→始终允许」。

**Q: 上传失败？**
A: 点「测试上传」看通知栏提示。检查手机网络能访问服务器、服务器 8899 端口是否被防火墙拦截。

**Q: 群友搜到的全是我的位置？**
A: 加上地点参数就行，比如 `找吃的 上海虹桥`。群友不需要装 App。

**Q: 插件不显示？**
A: AstrBot 日志里找 `tianyi` 关键字看报错。常见原因：没装 aiohttp（容器已自带）、config 里 amap_key 没填。

**Q: 高德 API 收费吗？**
A: 「Web服务」API 每日免费 5000 次调用，个人用绰绰有余。

---

## License

MIT

---

<p align="center">
  <b>@依一壹1</b>
  <br/>
  <sub>华风夏韵 · 洛水天依  #66CCFF</sub>
</p>
