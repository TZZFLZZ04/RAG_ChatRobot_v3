# 发现与决策：ChatRobot 前端体验升级

## 需求
- 参考 `ui-ux-pro-max` 与 `awesome-design-md` 优化现有前端页面。
- 同时遵循 `planning-with-files-zh`、`karpathy-guidelines` 与 `grill-me`。
- 交付可运行的前端实现，而非仅给建议。

## 研究发现
- 项目为 Python 3.11 FastAPI RAG 应用，前端采用原生 HTML/CSS/JavaScript。
- 当前页面包括 `index.html`、`register.html`、`evaluations.html`，共享样式主要在 `app/frontend/static/app.css`。
- 根目录现有规划文件属于 2026-07-13 的 RAG 重构任务，本次采用独立作用域避免覆盖。
- 当前 Git 元数据不可用，修改范围将通过文件级检查与测试验证。
- 前端规模为 3 个 HTML 页面、约 992 行共享 CSS，以及约 2,156 行页面 JavaScript；实现时应优先保持现有 DOM id 与事件绑定。
- `CLAUDE.md` 明确要求“理解需求 → 分析结构 → 确认影响范围 → 制定方案并经用户审批 → 修改 → 测试”；因此本轮先完成审计和方案，获得批准后才修改前端源码。
- 三个页面目前已经共享 `app.css`，主页面包含登录、知识库/文档管理、上传队列、文档详情、会话历史与流式问答；评估页包含运行表单、报告历史和逐 case 详情。
- 当前视觉采用暖米色、陶土橙与青绿色，大圆角、玻璃质感和大面积渐变；产品气质偏生活方式，和企业级 AI 运维工作台的高密度场景略有错位。
- `--workspace-panel-height: 1000px`、聊天区固定 460px 高度、1240px 即全量单列，容易造成超长滚动和中等屏幕空间浪费。
- 主页面首屏 Hero 信息较重，登录后仍占据大量垂直空间；高频的知识库、文档和问答操作没有稳定的应用级导航层。
- 多个表单字段使用 `<div class="field"><span>…</span>`，缺少与输入控件关联的原生 `label`；toast/状态提示也未声明 `aria-live`。
- CSS 为输入框提供焦点样式，但按钮与链接没有统一 `:focus-visible`，也缺少 `prefers-reduced-motion` 处理。
- JavaScript 通过大量固定 DOM id 获取元素，并动态生成 `.document-card`、`.conversation-item`、`.message`、`.eval-*` 等组件；必须保留现有 id 和这些类名，或同步进行最小映射调整。
- UI/UX Pro Max 将产品匹配为“AI/Chatbot Platform + Knowledge Base + Analytics Dashboard”：共同建议是 AI-native minimal、清晰层级、低彩度中性色、单一紫/靛蓝强调色，以及数据密集但可钻取的评估视图。
- 设计系统综合检索的 landing pattern 误匹配为 Newsletter，且颜色建议与其自身“避免 AI 紫粉渐变”存在冲突；这两项不采用，只保留 Soft UI Evolution、Inter/系统无衬线、轻微阴影、150–300ms 反馈和 WCAG AA 检查。
- UX 细项优先级：可见焦点、正确键盘顺序、表单提交反馈、无横向溢出、合适 input type/inputmode；当前 viewport 配置已正确。
- Awesome DESIGN.md 候选库包含 Linear、Notion、Supabase、Claude、Stripe、Vercel 等；下一步将从 Linear、Notion、Supabase 中按工作台密度与可访问性择一。
- Awesome 视觉参考最终选择 Supabase：白色/浅灰画布、近黑正文、单一翡翠绿强调、6–12px 技术型圆角、细边框、轻阴影和紧凑产品 UI，最适合知识库、异步状态与评估数据并存的工作台。
- Linear 的深色单模式会显著改变当前用户习惯且增加状态色对比工作；Notion 更偏内容创作和营销式留白，均不如 Supabase 契合本项目。
- 本机 8000、8080、8765 端口均未监听；首次用项目 venv 隐藏启动 Uvicorn 后进程在响应前退出，需要捕获前台错误后决定浏览器审计路径。
- 项目 `venv` 已失效，解释器指向不存在的 Python 3.10；系统 Anaconda Python 可用，含 FastAPI 0.115.0 与 Uvicorn 0.31.0，可用于本地只读页面审计。
- 系统 Python 启动的 Uvicorn 进程保持运行但超过 10 秒仍未监听 8765，表现为应用导入或初始化阻塞；需先单独验证 `app.main` 导入。
- 桌面实测（1280×720）：首屏 Hero 高约 290px，占用明显；暖色渐变、大阴影、34px 大圆角与胶囊按钮使界面偏宣传页，登录表单与真正任务区被推到首屏下半部。
- 桌面页面无横向溢出（页面宽 1265，视口宽 1280），但首屏信息重复：标题、功能徽章、四个未登录统计和功能预览同时出现，主任务聚焦不足。
- 移动端实测（375×812）：Hero 高 797px，登录区从 y=835 才开始，意味着用户完整滚过一屏宣传内容后才能登录；页面总高 1930px，虽无横向溢出但任务路径过长。
- 移动端 Hero 把四个统计卡全部纵向展开，未登录时数据均为 0/未选择，信息价值低却占用约 430px。
- 注册页桌面实测（1280×720）：Hero 高 254px，表单从 y=306 开始；表单被横向拉满到约 1190px，阅读与输入扫描距离过大，缺少聚焦的认证卡片布局。
- 主登录页和注册页均没有 `label[for]`，浏览器审计确认关联标签数为 0。
- 评估页桌面未登录态：Hero 高 292px，先展示 4 个空统计，再展示登录提示与登录门槛卡；同一“需登录”信息重复两次，页面右下大面积留白。
- 评估页移动端（375×812）：Hero 高 766px，登录提示 y=798、登录门槛 y=873，用户同样需要滚过整屏无效零值统计才能执行返回登录。
- 实施前复查确认共享 CSS 没有预处理或构建依赖，可原位替换设计令牌和布局规则；动态组件所需 class 均集中在同一文件。
- `app.js::renderAuthState()` 与 `evaluations.js::renderAuthState()` 是统计区显隐的唯一必要 JavaScript 触点；无需改变认证、请求或数据状态结构。
- UI 最终检查确认当前实现已覆盖：44px 主交互目标、150–160ms 反馈、禁用/加载按钮、系统字体无阻塞、无图片资源、z-index 仅用于 toast、reduced-motion、关联标签与实时状态播报。
- Quick Reference 将 skip link 列为关键无障碍项；三个页面需要增加统一的“跳到主要内容”链接及稳定的 `#mainContent` 包装目标。
- 浏览器首次复验仍读取旧 DOM（缺少新 `workspaceStats` id），确认是同一 localhost URL 的缓存命中而非源码缺失；交付页面应对本次 CSS/JS 变更加版本查询参数。
- 新移动端登录页（375×812）Hero 高 270px、登录区 y=296，较基线分别减少 527px 和提前 539px；统计区默认隐藏，7 个页面字段标签与 skip link 均生效，页面无横向溢出。
- 768×576、1024×768、1440×900 均无横向溢出；Hero 分别为 272/205/218px，登录区 y=304/237/250。1024px 以上恢复双栏认证工作台，768px 自动单列。
- 1440px 桌面视觉已呈现白色/浅灰技术型层级、单一绿色主 CTA、紧凑圆角和细边框；首屏完整容纳 Hero、登录卡与功能卡。
- 注册页复验：375px 下 Hero 302px、表单 y=328 且宽 355px；1280px 下 Hero 186px、表单 y=218 且稳定限制为 560px，解决原先约 1190px 超宽输入问题。
- 评估页复验：375px 下 Hero 261px、登录门槛 y=342；1440px 下 Hero 218px、登录门槛 y=305。空统计在未登录态均隐藏，且两种宽度无横向溢出。
- 最终触摸检查发现内联 `.text-link` 和移动端 `.mini-button` 仍可能低于 44px，需要在 CSS 中补齐移动触摸高度。
- 补齐后 375px 自动检查显示所有可见交互元素高度均 ≥44px、无横向溢出、存在 4 个 aria-live 区域，并能检测到 reduced-motion 规则。
- 浏览器的两种 Tab 注入方式均未把焦点从 `body` 移到 skip link；DOM、href、目标 id 与 focus CSS 均存在，但该环境未能完成端到端键盘焦点跳转验证。
- 实测对比度：Hero 辅助文字 5.07:1、主按钮 7.37:1、字段标签 8.04:1，均满足普通文本 WCAG AA；浏览器控制台无 warning/error。

## 技术决策
| 决策 | 理由 |
|------|------|
| 不引入新前端框架或构建工具 | 保持部署模型简单，减少与 FastAPI 静态托管的耦合变化 |
| 优先改 CSS 与语义结构，谨慎修改 JS | 直接提升体验并降低行为回归风险 |
| UI/UX Pro Max 负责可访问性、交互与响应式 | 按技能的职责分工执行 |
| Awesome DESIGN.md 负责视觉语言 | 保证颜色、排版、层次与组件风格一致 |
| 前端源码修改前必须提交方案等待用户批准 | 遵循用户提供的 `CLAUDE.md` 明确流程要求 |
| 优先消除固定高度和过早单列断点 | 直接改善桌面信息密度、笔记本适配和移动端滚动体验 |
| 补齐语义 label、aria-live、focus-visible 与 reduced-motion | 满足 UI/UX Pro Max 的最高优先级可访问性要求 |
| 采用 Supabase-inspired 视觉层，不复制品牌资产 | 其技术型白色画布和紧凑 UI 与 RAG 工作台定位最接近 |

## 待审批实施方案
1. **视觉基础**：把暖米色/陶土渐变改为白色与浅灰层级，翡翠绿仅用于主 CTA 和焦点；圆角收紧到 6–14px，阴影降为细微层级，使用系统无衬线字体避免网络字体依赖。
2. **首屏与导航**：压缩 Hero 为应用级页头；未登录时隐藏无意义的零值统计，让登录或登录门槛在移动端首屏出现；登录后保留用户、知识库和任务摘要。
3. **工作台布局**：移除 1000px/460px 硬编码高度，桌面保持知识库/问答并列，中屏合理折叠；评估页使用 runner/history/detail 网格区而非三个等高巨型面板。
4. **认证页面**：注册页改为聚焦的窄表单卡和简洁说明区，控制输入行宽；保留注册后返回登录的现有流程。
5. **可访问性**：补齐 label/for、autocomplete、aria-live、focus-visible、触摸目标与 reduced-motion；不新增未授权业务功能。
6. **兼容与测试**：保留全部 DOM id/API；仅在 `app.js`、`evaluations.js` 增加认证态统计显隐等必要 UI 状态，不改请求逻辑；扩充 `test_web_page.py` 的语义标记断言。

## 预计修改文件
- `app/frontend/index.html`
- `app/frontend/register.html`
- `app/frontend/evaluations.html`
- `app/frontend/static/app.css`
- `app/frontend/static/app.js`
- `app/frontend/static/evaluations.js`
- `tests/test_web_page.py`

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| `grill-me` 未提供可调用的 `/grilling` 工具 | 将严格访谈转化为显式问题、假设、反例和验收清单 |
| 会话恢复脚本失败且未产生恢复报告 | 已直接读取全部旧规划文件并创建独立规划作用域 |
| 文件统计命令首次出现 PowerShell 管道语法错误 | 改用中间变量收集 `foreach` 输出后成功 |
| Awesome 参考检索命令误传 PowerShell 参数给 `rg` | 已获得候选列表；下一步用纯 `rg`/直接读取，不重复该命令 |
| Uvicorn 隐藏启动后退出且没有日志 | 改用前台限时诊断以捕获导入或配置错误 |
| 项目 venv 的解释器路径失效 | 使用系统 Anaconda Python，不修改依赖或虚拟环境 |
| 系统 Python 的 Uvicorn 未进入监听状态 | 停止仅为审计创建的进程，拆分为模块导入诊断 |
| 响应式检查中的 viewport 变量未跨调用保留 | 重新从 browser capability 获取，不重建或切换浏览器 |

## 资源
- `C:/Users/林镇州/Desktop/CLAUDE.md`
- `AGENTS_a_c.md`
- `AGENTS.md`
- `app/frontend/`

## 视觉/浏览器发现
- 1280×720 登录页首屏：Hero 占据约 40% 可视高度，暖色渐变和大圆角视觉重量较高；登录输入区域刚进入首屏，主要 CTA 靠近底部。
- 页面层级可读，但营销信息、统计卡和功能卡同时争夺注意力，缺少轻量应用导航。
- 375×812 登录页：整屏几乎只有 Hero 和无效的零值统计，登录表单完全不可见；这是当前最明确的移动端体验问题。
- 1280×720 注册页：超宽单列表单降低聚焦感，适合改为窄认证卡 + 简洁价值说明的双栏结构。
- 评估页未登录态在桌面和移动端都过度展示空统计；应在未认证时压缩 Header，并把登录门槛作为首要内容。
- 改造后 375px 首屏已完整显示 Hero、评估入口、登录表单与注册链接；1440px 首屏完整显示认证双栏，任务焦点明显改善。
- 注册页和评估页在 375/1280/1440 下视觉一致，主要动作均进入首屏，表单阅读宽度受控。
- 375px 触摸目标扫描无低于 44px 的可见交互项；reduced-motion 和 live region 检查通过。

## Milvus 连接故障诊断（2026-08-06）
- 前端目录与页面测试中没有 `milvus` 或 `VECTOR_BACKEND` 引用；上一轮 UI 改动不包含后端配置、Docker 或向量存储代码。
- 当前 `.env` 明确选择 `VECTOR_BACKEND=milvus`，宿主机配置为 `MILVUS_HOST=localhost`、`MILVUS_PORT=19530`，且未设置 `MILVUS_URI`。
- `docker-compose.yml` 会把 API/Worker 容器的 `MILVUS_HOST` 强制覆盖为 `milvus`；Milvus、etcd、MinIO 又都受 `milvus` profile 控制，普通 `docker compose up` 不会自动启动它们。
- API 容器内的实际配置是 `vector_backend=milvus`、`milvus_host=milvus`、`milvus_port=19530`、未设置 URI；与报错目标完全一致。
- Docker 状态显示 API、Worker、PostgreSQL、Redis 均已运行约 5 分钟，但 Milvus、etcd、MinIO 已在两周前退出；宿主机 19530 未监听。因此直接根因是 Milvus 依赖栈未运行，而不是参数格式或前端请求格式。
- 结构性诱因是 Milvus 依赖栈受 Compose profile 控制且没有随当前 API/Worker 启动；如继续使用 Milvus，应显式启动该 profile；如本地开发不需要 Milvus，可切回 FAISS 并重建 API/Worker 容器。

## README 运行指南改造（2026-08-06）
- README 已有“本地运行”和“Docker 整站模式”，但整站命令仍是 `docker compose up --build`；该命令不会启用 `milvus` profile，与 `.env` 选择 `VECTOR_BACKEND=milvus` 时的实际部署要求冲突。
- 全 Docker 模式需要明确要求 `.env` 使用 `VECTOR_BACKEND=milvus`，并使用 `docker compose --profile milvus ...` 启动、查看、记录日志和停止。
- 为满足生产建议，应把基础设施启动、容器内 Alembic 迁移、API/Worker 启动按顺序列出；本地开发仍保留宿主机 Uvicorn/Celery + Docker PostgreSQL/Redis 的轻量流程。
- `docker-compose.yml` 已把 API/Worker 的 PostgreSQL、Redis、Milvus 主机名覆盖为 Compose 服务名，因此无需为全 Docker 模式另建环境文件或修改应用代码。
- README 已将两种运行模式分开，并补充全 Docker 的生产环境变量、首次部署/升级、日常启动、日志、健康检查与停止命令。
- `docker compose --profile milvus config --quiet` 校验通过；profile 展开后包含 `etcd`、`minio`、`milvus`、`postgres`、`redis`、`worker`、`api` 七个服务。
- 严格审视后保留最小改动范围：不修改 Compose 服务定义或应用代码；README 明确说明 `DATABASE_URL`/`MILVUS_URI` 的覆盖风险，以及 Milvus 模式不可遗漏 profile。

## 生产化工作台重构（2026-08-11）
- 用户明确允许较大调整，目标从“现代化视觉”升级为“像真实正在使用的生产页面”：需要强化固定应用框架、任务导航、运行状态、信息密度和长期操作感，而非继续扩展营销式 Hero。
- 技术栈仍是原生 HTML/CSS/JavaScript，且没有 `.openai/hosting.json`；本轮继续在现有 FastAPI 静态前端内实施，不引入前端框架或独立托管层。
- 既有规划记录显示 DOM id、动态 class、认证请求和 API 契约是主要兼容边界；较大调整应集中在语义结构、布局、组件视觉和少量 UI 状态编排。
- 当前三页仍以大块 `hero` 开场，主工作台登录后是两个并列巨型面板，缺少真实 SaaS 常见的品牌栏、主导航、面包屑/页面标题、环境与运行状态、稳定内容画布；这正是页面仍像 Demo 而不像“正在使用”的主要原因。
- `app.js` 和 `evaluations.js` 已在认证态切换 `body.is-authenticated`，可用纯 CSS/结构调整区分登录落地页与生产工作台，无需改变认证流程。
- 主页面动态逻辑依赖现有 82 个左右 DOM id 和 `.document-card`、`.conversation-item`、`.message`、`.status-*` 等 class；这些可以原样保留，同时移动其容器位置并增添不参与业务逻辑的导航/说明结构。
- 当前设计令牌与表单可访问性基础较好，但颜色层级偏单一、卡片数量过多、所有区域都使用同等边框/圆角，导致信息优先级不足；生产化调整应减少“每块都是卡片”，加强页框架、侧栏、表格/列表密度与上下文栏。
- 评估页已有 3 列 runner/history/detail 的业务结构，适合改造成运维分析台；注册页适合采用更克制的分栏身份页。三个页面的静态资源版本目前不一致，需要交付时统一更新以避免缓存。
- UI/UX Pro Max 将该产品匹配为高密度、实时运营型企业 Dashboard：优先最大化数据可见性、行级悬停反馈、明确加载状态、44px 交互目标、顺序标题、键盘导航和 375/768/1024/1440 响应式；推荐的紫粉 AI 调色与现有企业知识产品气质不符，将保留其结构/密度建议而不采用该颜色。
- 本轮设计旋钮确定为 variance 4、motion 3、density 8：视觉变化有辨识度但不实验化，动画只做 150–220ms 状态反馈，不引入 GSAP 或滚动表演。
- Awesome DESIGN.md 候选搜索中，`linear.app` 最接近稳定生产应用壳；Airtable/Intercom 可作为数据工具和企业支持场景的对照。下一步完整读取候选后选定单一主参考。
- 已完整读取 Linear.app 参考。采用：4px 间距基准、6/8/12px 圆角、表面层级 + 发丝边框代替大阴影、Inter/系统字体、紧凑 14px 操作文本、单一 `#5e6ad2` 靛紫用于品牌/主按钮/焦点、无渐变与无装饰性高光卡片。
- 不直接复制其纯黑营销画布：本项目是长时间阅读文档和检查评估结果的生产工具，采用深色导航壳承载 Linear 气质，主内容使用冷白/浅灰表面以提升长文本与表单可读性；语义成功/警告/失败色只用于状态。
- 选定的信息架构：认证后为固定左侧产品导航 + 顶部页面上下文 + 工作区概览 + 主任务画布；知识库、文档、会话、评估通过稳定导航定位，主页面保留原有两大业务区域但重新组织为“资源管理 / AI 对话”的生产工作流。
- 页面测试对 `workspaceStats` / `evalHeroStats` 的精确 class 字符串、表单 label、选择器属性和脚本内容有契约断言；实施时保留这些字符串或同步调整测试，优先保留以降低无意义回归。
- 主/评估脚本已经完整覆盖认证态、加载、轮询、流式对话、上传队列与动态列表；本轮不需要改变请求或状态模型。HTML 可移动现有 id，CSS 可重写，JS 仅在出现真实布局状态需求时修改。
- 响应式侧栏不引入汉堡菜单和新状态管理：桌面使用固定窄侧栏，中屏压缩为横向导航条，移动端允许导航横向滚动并把任务区单列，避免新增不可验证的交互复杂度。
- 实施已落地为“深色稳定应用框架 + 冷白任务画布”：顶栏承载品牌、环境、用户和全局动作；侧栏提供概览/知识库/文档/AI 对话/评估定位；工作区概览与状态卡进入业务画布，不再放在营销 Hero 中。
- 登录/注册页面改为产品身份页，强调隔离、异步可观测和质量闭环；评估页改为质量运营台，仍保留 runner/history/detail 的三段业务逻辑。
- 内置浏览器及其最小 Node 会话均因“无法写入 kernel assets”失败，真实截图/交互验收在当前环境不可用；后续验证将覆盖服务响应、HTML 契约、DOM 唯一性、label/anchor 对应、JS 语法、CSS 响应式规则与完整 pytest，但不会把这些静态检查误报为视觉实测。
- 静态复核发现 375px 认证顶栏可能被品牌最小列宽和三个全局动作挤压，已在 560px 以下切换为仅显示品牌图标的双列顶栏，保留评估、刷新和退出入口。
- 最终 UI 规则复核强调：关键加载必须反馈、z-index 使用有限层级、输入在移动端避免小于 16px、触摸目标至少 44px、按压态不能引发布局跳动。现有脚本已有按钮禁用/进度/轮询文本，本轮补齐了品牌链接、横向移动导航和顶栏动作的 44px 触摸面积、移动输入 16px 以及按压反馈。
- 当前页面没有图片或第三方字体，避免了图片 CLS、字体阻塞与额外网络请求；图标全部使用同一套 1.6px 描边内联 SVG，并配文字标签。
- 最终验证结果：82 passed、1 skipped；Python 编译、三份 JS 语法、100 个页面 DOM id 唯一性、所有 label/页内锚点目标、三页与 CSS 的本地 200 响应均通过。
- 关键对比度全部满足 WCAG AA：正文 17.39:1、辅助文本 5.32:1、顶栏 7.99:1、侧栏 7.18:1、主按钮 4.70:1、强调文本 8.46:1。
- 页面测试新增生产化结构契约：产品顶栏、工作台侧栏、概览区、注册产品面板与评估应用壳；改造未修改 API、认证、上传、检索、对话或评估脚本逻辑。
- 真实浏览器截图与多断点实际渲染未完成，原因是内置浏览器最小运行会话无法写入自身资源；CSS 已覆盖 1450/1320/1050/900/760/560 断点并执行静态检查，但该项应在浏览器环境恢复后复验。

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
