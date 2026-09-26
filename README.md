# 岸桥小车导轨 · 拼接曲线审计

岸桥改造前复核小车导轨的拼接三次贝塞尔样条（按行进顺序 2–5 段，整数控制
点，统一最大曲率；可选统一最大转向变化率）。系统**不使用离散采样**：每段
的曲率判定点为两端点及 κ² 导数的**全部驻点**；零切向量通过速度平方多项式
的精确实根判定。填写最大转向变化率后，系统再按弧长对有符号曲率的变化率
dκ/ds 做同样的精确判定（段内限值 + 拼接处左右连续性），识别曲率虽未超限
却会使转向机构受到突变载荷的导轨。

## 架构

```
docker compose up --build         # 启动 web + api
# 浏览器打开 http://localhost:8080
```

| 服务 | 技术 | 容器端口 | 宿主机端口（可配置） |
| --- | --- | --- | --- |
| `web`  | nginx 静态页面 + 反代 `/api/` | 80 | `${WEB_PORT:-8080}` |
| `api`  | FastAPI + uvicorn | 8000 | `${API_PORT:-8001}` |
| `verify` | 一次性：构建 + 测试 + 业务冒烟 | — | profile `verify` |

- **Web 健康检查**：容器内 `wget /index.html`；页面还会经反代轮询
  `/api/health` 显示服务在线状态。
- **API 健康检查**：`GET /health`（容器内 urllib 检查 `status=ok`）。
- **宿主机端口**：复制 `.env.example` 为 `.env` 改 `WEB_PORT` / `API_PORT`。

## 一次性 verify 服务

```
docker compose --profile verify up --build --abort-on-container-exit \
    --exit-code-from verify
echo $?      # 0 通过，非 0 失败
```

`verify` 容器与运行中的 `api`/`web` 同网络，依次执行：

1. **构建**——所有镜像由 compose 在本命令中完成构建；
2. **代码测试**——`python -m pytest -q`（51 个单测/集成测，覆盖根隔离、
   多项式 GCD、几何、审计与 HTTP 层）；
3. **业务冒烟**——`scripts/smoke.py` 调用审计 API：通过样例、段内急弯超限、
   零切向量、拼接断接、非法输入、重复草稿稳定性，以及转向变化率的
   通过样例、段内超限、拼接突变、历史草稿响应不变。

退出码即结论：`0` 合格，`1` 及以上不合格。

## 审计逻辑（精确，无采样）

对每段三次贝塞尔，整数控制点 ⇒ 速度 `v(t)`、加速度 `a(t)`、速度平方
`S(t)=|v|²`（四次整系数多项式）以及

$$\kappa^2(t)=\frac{|v\times a|^2}{|v|^6}=\frac{N(t)}{D(t)}$$

驻点多项式 `N'D − ND'`（整系数，最高 11 次）。判定点：

- **端点** t=0、t=1；
- **全部驻点**：用 **Vincent–Descartes 实根隔离**（整数算术的对分 +
  符号判别，重根聚类到 1e-12）精确找出 [0,1] 内每个实根，不会漏根；
- **零切向量**：`S(t)=0` 的全部精确实根（端点直接判定，内部用根隔离）；
- 驻点与零速根重合时曲率无定义，通过**精确多项式 GCD / 无平方因子分解**
  严格剔除，而非数值邻近度猜测。

所有 κ 比较与连续性判定均为精确有理数运算（`max_curvature` 取其十进制
精确值 `Fraction(str(x))`），仅输出时转浮点。

按行进顺序逐项检查并稳定返回**最早问题**：位置连续 → 一阶切向量连续 →
零切向量（不可运行）→ 曲率连续 → 曲率限值，之后才进入下一段。

## 转向变化率审计（选填，`max_curvature_rate`）

填写统一最大转向变化率后，系统对**有符号曲率** κ = (v × a)/|v|³ 按弧长
求变化率（c = v × a，S = |v|² 均为整系数多项式）：

$$\frac{d\kappa}{ds}=\frac{2c'S-3cS'}{2S^{3}}$$

- **段内限值**：判定点为两端点及 (dκ/ds)² 驻点多项式
  `A'S − 3AS'`（A = 2c′S − 3cS′，整系数，最高 8 次）在 [0,1] 内的**全部
  实根**（同一 Vincent–Descartes 根隔离，与零速根用精确 GCD 剔除），
  逐点与限值做精确有理数比较，不以参数步长或显示采样代替判定；
- **拼接连续性**：相邻段连接处左右 dκ/ds 做精确有理数相等判定；
- 任一编辑都会使页面撤销旧结论；未填写该限制的草稿与既有审计响应
  **完全不变**（响应中不出现任何 rate 字段）。

## 返回

合格（HTTP 200, `ok=true`）：每段最大曲率及对应参数/坐标；启用转向变化率
审计时，每段同时给出最大转向变化率及其参数/坐标；
不合格（HTTP 200, `ok=false`）：最早问题的 `code`、`segment`（0 基）、
`parameter`、坐标、实际/限值或断接两侧值，并附该段（及邻段）控制点；
新增 `code`：`CURVATURE_RATE_EXCEEDED`（段内或端点超限，附 `curvature_rate`
与 `max_curvature_rate`）、`CURVATURE_RATE_DISCONTINUITY`（拼接处突变，附
`curvature_rate_end` / `curvature_rate_start` 与 `max_curvature_rate`）；
结构非法（HTTP 422）：`INVALID_INPUT`。

## 目录

```
backend/   FastAPI 服务、精确几何/根隔离、pytest、smoke 脚本与 Dockerfile
web/       原生 HTML/CSS/JS 页面、SVG 预览、nginx 反代与 Dockerfile
docker-compose.yml
.env.example
```

> 页面曲线预览的像素绘制是采样的，**仅用于显示**；所有审计结论只来自
> 服务端的精确根隔离与有理数比较。
