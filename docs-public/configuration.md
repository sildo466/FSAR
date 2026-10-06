# 配置文件详解

> 语言：中文 | [English](configuration.en.md)

FSAR 的运行时行为几乎全部由一个 YAML 配置文件驱动。本页逐段讲解每个配置项的含义、默认值与取值范围。

## 配置文件在哪里

| 文件 | 作用 |
|---|---|
| `config/fsar.yaml.template` | 随仓库发布的**只读模板**，列出全部配置项与默认值 |
| `~/.fsar/config/fsar.yaml` | **你自己的配置**，首次运行时由模板复制生成 |

- 首次启动若 `~/.fsar/config/fsar.yaml` 不存在，FSAR 会把模板复制过去。
- 之后由图形界面（onboarding 向导、设置页）或直接手工编辑这个文件来修改。
- 删除整个 `~/.fsar/` 目录即可把 FSAR 重置为干净状态（配置、记忆、缓存、日志一并清除）。

> 下面所有默认值均取自 `config/fsar.yaml.template`。

---

## onboarding — 向导状态

记录首次使用向导的进度，通常由界面自动维护，无需手改。

```yaml
onboarding:
  completed: false        # 是否已完成向导
  completed_at: null      # 完成时间
  completed_steps: []     # 已完成的步骤
  skipped_steps: []       # 跳过的步骤
  started_at: null
  last_step: null         # 上次停留的步骤
```

## agent — 智能体档位

```yaml
agent:
  tier: medium
```

`tier` 控制智能体循环的推理/执行强度，共有多个档位（默认 `medium`，最高可达 `ultra`）。档位越高，模型在工具调用与规划上投入越多。

> 注意：`agent.tier` 与下文 `reflection.intensity` 是两个互不相干的"强度"旋钮，不要混淆。

## chat — 默认模型

```yaml
chat:
  default_model:
    kind: model
    provider: ""    # 提供商名（对应 llm.providers[] 中的某一项）
    model: ""       # 模型名
```

新会话默认使用的聊天模型。留空时由界面选择。

---

## workspace — 工作区与输出目录

```yaml
workspace:
  output_dir: ""    # agent 保存生成文件（报告/网页/图片/脚本等）的目录
```

agent 生成成果文件时的保存位置。留空时默认 `~/FSAR-workspace`（当前用户主目录下的 `FSAR-workspace` 文件夹）。即使给了 agent 全盘访问权限，它也会把生成的文件存到这里的任务命名子文件夹，而不会默认存到桌面。配置成你想要的绝对路径即可。

---

## security — 安全防护（重点）

FSAR 的核心卖点是"纵深防御"。这一段配置各个安全层。完整的机制说明见仓库根目录的 [`SECURITY.md`](../SECURITY.md)。

```yaml
security:
  hardline_disabled_classes: []   # 关闭某些 hardline 拦截类（A–I），默认全开
  power_user_mode: false          # 高级用户模式（放宽部分确认）
  custom_sensitive_paths: []      # 额外的敏感路径（需确认才能访问）
  always_allow_paths: []          # 始终放行、无需确认的路径
```

- **hardline_disabled_classes**：hardline 是无条件的命令拦截地板，分 A–I 九类（磁盘破坏、系统生命周期、持久化、提权、资源耗尽、服务控制、网络安全配置、下载即执行、文件系统完整性）。默认全部启用；除非你完全清楚后果，否则不要在这里添加项。

### security.skills — 技能（Python skill）安全

```yaml
  skills:
    review_required: true         # 运行技能前是否需要审阅
    subprocess_env:               # 子进程环境变量清洗
      enabled: true
      allow: [PATH, HOME, LANG, TMPDIR, SYSTEMROOT, USERPROFILE]  # 白名单
      strip_prefixes: [API_KEY, TOKEN, SECRET, AUTH]              # 剥离含这些词的变量
    llm_review:
      enabled: false              # 是否额外用一个小模型审阅技能
```

`subprocess_env` 确保运行技能时，子进程只能看到白名单里的环境变量，并且任何名字带 `API_KEY/TOKEN/SECRET/AUTH` 的变量都会被剥掉——提供商密钥不会泄漏给技能代码。

### security.mcp — MCP 服务器安全

```yaml
  mcp:
    review_required: true         # 安装/启用 MCP 服务器前是否需要审阅
    cwd_pinning:
      enabled: true               # 把 MCP 服务器的工作目录固定住
      require_dir: true           # 必须显式指定目录
```

### security.egress — 网络出口控制

```yaml
  egress:
    enabled: false                # 默认关闭；开启后对技能/命令的外联做准入
    mode: deny                    # deny=默认拒绝仅放行 allowlist；allow=默认放行仅拦 blocklist
    allowlist:
      - "api.openai.com:443"
      - "api.anthropic.com:443"
      - "127.0.0.0/8"
    blocklist:
      - "*.onion"
      - "169.254.0.0/16"          # 屏蔽链路本地/元数据地址
```

### security.redaction — 输出脱敏

```yaml
  redaction:
    enabled: true
    max_string_length: 16384      # 超长字符串截断，避免日志/上下文泄漏与膨胀
    patterns: []                  # 额外的脱敏正则
```

### security.memory — 记忆写入净化

```yaml
  memory:
    write_sanitization:
      enabled: true
      block_on_match: true        # 命中规则时直接拒绝写入
      custom_patterns: []
```

防止把密钥等敏感内容写进长期记忆。

### security.content_screening — 提示注入筛查

```yaml
  content_screening:
    enabled: true                 # 默认开启：新部署即生效
    threshold: 0.62               # 置信度 >= 此值即判为风险
    scan_on_startup: true         # 启动时后台巡检已存内容
```

用模型判定「这是正常的角色扮演/用户自述，还是一次针对模型的指令注入」——正则抓不到靠语境才有害的载荷。配了 `llm.judge` 就走 JEV，否则用当前激活的 LLM。

- **写入时**：每次写记忆（事实、经验、偏好、行为模式、任务反思）都在后台线程筛一次，不阻塞对话。
- **启动时**分两种情况：配了 `llm.judge` 就**每次开机全量重扫**（JEV 调用不要钱）；没配 JEV 则**只扫上次之后的新增/改动**——否则每次开机都会烧你自己的 API 额度。首次运行时存量内容只登记水位、不扫。
- **命中后**：从原位置移入隔离区，并在 GUI 的「通知」页列出，可**恢复**或**永久删除**。恢复过的内容按哈希进白名单，之后跳过检测。
- **角色卡**命中时只清空文本字段，不删卡片行（会话还引用着卡 id）。
- **筛查不可用时（没配模型 / 超时 / 调用失败）不隔离任何东西**，只在通知页显示本次有多少条没筛到。

### security.visitor_screening — 对外部成员发言的筛查

```yaml
  visitor_screening:
    enabled: false                # 默认关闭——原因见下
    threshold: 0.7                # 置信度 >= 此值即封禁该凭证
```

逐行读取房间外部成员发来的每一句话，当这句话试图操纵模型、攻击他人、刷屏，或伸手够这台机器时，封禁该成员的凭证。默认关闭，因为它可以凭模型的判断收走一份凭证——那是一个决定，不是一个默认值。

### security.file_read_blacklist — 文件读取黑名单

```yaml
  file_read_blacklist:
    enabled: true
    defaults: true                # 启用默认黑名单：~/.ssh/*、~/.aws/credentials、~/.gnupg/*、*.key、*.pem、id_rsa
    extra_patterns: []            # 额外禁止读取的模式
```

### 其它安全开关

```yaml
  session:
    no_trust_mode: false          # 禁止"本会话信任"，每次都确认
  small_agent_review:
    enabled: false                # 用小模型对高风险操作做二次复核
```

---

## notifications — 通知流

```yaml
notifications:
  review:
    enabled: true                 # 隔离通知
  release:
    enabled: true                 # 更新的 GitHub 版本
    include_prerelease: false     # 让稳定版也听到预发布
  announcement:
    enabled: true                 # 来自仓库的官方公告
```

三类通知可以各自关闭；信息流的分类筛选与之一一对应。`release.include_prerelease` 就是把稳定版变成"连 beta 也听"的那个开关。

## github — API 令牌

```yaml
github:
  token: ""                       # 可选；提高 Releases API 的速率上限
```

更新检查与公告拉取不带令牌也能工作，只是受 GitHub 匿名速率限制。检查频繁或撞到限制时再配。

---

## llm — 大模型提供商

```yaml
llm:
  active: ""          # 当前激活的提供商名
  providers: []       # 提供商列表，每一项含 name/provider/base_url/api_key/model 等
  vision_model:       # 可选的专用视觉模型（image_analyze / Computer Use 用）
    base_url: ""      # 留空 = 用当前激活的聊天模型
    api_key: ""
    model: ""
  judge:              # 可选的逐条相关性裁判（记忆注入用）
    base_url: ""      # 留空 = 关闭，注入回落到优先级顺序
    api_key: ""
    model: ""
```

- 支持 OpenAI、Anthropic、Google、DeepSeek，以及任意 OpenAI 兼容端点；本地模型可用 Ollama / LM Studio。
-  provider 行可写 `format: responses`，让调用走 OpenAI Responses API（`/v1/responses`）而非 chat completions。在 GUI 里把某个 openai 预设的 family 设为 "OpenAI Responses" 时会自动写入。
- `vision_model` 只在配置后启用；否则图像分析走当前激活的聊天模型。
- `judge` 必须说 JEV 的协议——它返回的是带类型的判定而非文本，所以普通的 OpenAI 兼容模型塞不进来。`base_url` 与 `api_key` 支持 `${ENV_VAR}`。在设置页的「模型」标签里配置。

## tts — 语音合成

```yaml
tts:
  active: ""           # 激活的 TTS 提供商
  autoplay: false      # 是否自动朗读回复
  default_voice: ""    # 默认音色
  providers: []
```

## asr — 语音识别

```yaml
asr:
  active: ""      # 激活的 ASR 提供商
  language: ""    # 识别语言（留空自动）
  providers: []
```

---

## social — 社交平台桥接

同一个引擎可通过 Telegram、飞书（Lark）、微信收发；每个平台可独立覆盖角色卡与用户卡。

```yaml
social:
  telegram:
    enabled: false
    bot_token: ""
  feishu:
    enabled: false
    app_id: ""
    app_secret: ""
    verification_token: ""
    encrypt_key: ""
  wechat:
    enabled: false
    account_id: ""
    bot_token: ""
    base_url: ""
    character_card_id: null   # 该平台专用角色卡（null=用全局）
    user_card_id: null
```

## memory — 记忆与反思

```yaml
memory:
  short_term_window: 50          # 短期记忆保留的最近消息数
  reflection_interval_hours: 12  # 空闲批量反思的最小间隔（小时）
  reflection_intensity: medium   # 反思强度（多档可调，默认 medium）
  inject_budget_chars: 2400      # 所有注入候选共享的字符预算
  inject_candidate_cap: 40       # 裁判最多评多少条候选
  inject_score_floor: 0.35       # 相关性低于此值的丢弃
  inject_max_item_chars: 600     # 单条上限
  enable_rating_prompt: true     # 是否提示用户为回复打分
  embedder:                      # 语义嵌入（语义记忆/召回用）
    provider: ""
    base_url: ""
    model: ""
    api_key: ""
    timeout: 60
```

召回按相关性打包进一份共享预算，而不是按位置截断，所以不会被从句子中间切断。预算刻意接近旧的截断上限：只有候选池超过它时，裁判才值得存在。可在「设置 → 高级」中编辑。（它取代了 `recall_max_chars`，后者是为按位置截断调的。）

## llm_cache — 提供商 prompt 缓存记账

**本地没有响应缓存。** 磁盘级 L1/L2 缓存已被移除；剩下的只是对**提供商自己**服务端 prompt 缓存的记账（Anthropic `cache_control`、Gemini `cachedContents`），其标记在提供商支持时仍然会照常应用。

```yaml
llm_cache:
  retention: short          # 记账的保留策略
  use_responses_api: false  # 遗留开关；更推荐在 llm.providers[] 里按提供商设 format="responses"
```

## gui — 界面服务

```yaml
gui:
  host: 127.0.0.1   # 后端监听地址（默认仅本机）
  port: 8765        # 端口；浏览器访问 http://127.0.0.1:8765
```

## logging — 日志

```yaml
logging:
  level: INFO       # 日志级别；日志写入 ~/.fsar/data/logs/
```

## permissions — 工具权限

```yaml
permissions:
  mode: normal      # 会话模式：strict / normal / trust（影响何时弹确认）
  tools: {}         # 按工具的 trust/ask/deny 配置
  path_rules: []    # 路径规则（命中即拒绝）
```

`mode` 与风险等级共同决定一个工具调用是直接放行、需要确认、还是拒绝。详见 [`SECURITY.md`](../SECURITY.md) 中"风险引擎"一节。

## mcp — MCP 服务器清单

```yaml
mcp:
  servers: []       # 已安装的 MCP 服务器（名称、命令、参数、env 等）
```

## reflection — 反思触发器

```yaml
reflection:
  intensity: medium       # 反思强度（4 档，默认 medium）
  triggers:
    per_task: true        # 每个任务结束后反思
    on_failure: true      # 失败时反思
    idle_batch:           # 空闲批量反思
      enabled: false
      threshold_events: 20   # 累计多少事件触发
      threshold_hours: 12    # 或距上次多少小时触发
```

三种反思模式可并存：`per_task`（每任务）、`on_failure`（失败时）、`idle_batch`（空闲批量）。反思会重读对话并更新用户画像（显式偏好 / 推断特征 / 行为模式），下次会话开场即带入。

## user / style — 用户与外观

```yaml
user:
  display_name: ""        # 用户显示名
  birthday: null          # MM-DD；角色会记住这一天
  birthday_letter_shown: null   # 最近一次写信的年份

style:
  theme: system           # 主题：system / light / dark
  font_scale: 1.0         # 字体缩放
  density: comfortable    # 密度：comfortable / compact
  motion: subtle          # 动效强度
  locale: en              # 界面语言（en / zh-Hans / zh-Hant / ja / de / fr）
  per_page_overrides: {}  # 按页面的样式覆盖
```

`birthday` 也会由 onboarding 向导询问。填了它，角色才会为这一天做点什么。

## time — 时间感知

```yaml
time:
  enabled: true           # 把真实日期与离开时长注入提示词
  gap_floor_minutes: 120  # 低于这个时长，就不加"你离开了…"那一句
```

开启后，提示词里带上今天的日期、你离开了多久，以及召回记忆的年龄，于是角色不再把上个月当成今天。

## lan — 局域网房间监听

```yaml
lan:
  enabled: false          # 总开关：关掉就完全不开 socket
  bind_host: "0.0.0.0"    # 0.0.0.0 会跟着这台机器加入任何网络
  port: 8766
  cert_dir: ""            # 留空 = ~/.fsar/security/lan
```

这是外部房间成员的**总**开关；房间自己还要设 `lan_enabled`。`0.0.0.0` 正是它的用途——跟着机器走到它加入的任何网络——但这也就意味着咖啡馆的 wifi 能碰到这个端口，所以在那种地方请关掉。每个外部成员都有自己的凭证（有效期、首次使用的地址绑定、速率预算）；详见 [`SECURITY.md`](../SECURITY.md)。

## plugins / external_skills — 扩展

```yaml
plugins: []           # 插件
external_skills: []   # 外部技能（外部目录中的 Python skill）
```

---

## 延伸阅读

- 安全机制全景与漏洞报告流程：[`SECURITY.md`](../SECURITY.md)
- 参与开发：[`CONTRIBUTING.md`](../CONTRIBUTING.md)
- 第三方许可：[`THIRD_PARTY_LICENSES/`](../THIRD_PARTY_LICENSES/)
