# Wyckoff Analysis Plan

## 目标

为 Market Analyst 增加一套基于理查德·威科夫（Richard Wyckoff）量价分析方法论的确定性结构识别工具，识别股票当前所处的吸筹（Accumulation）或派发（Distribution）交易区间、区间内的经典事件序列，以及由此得出的阶段性方向判断。这套结论在 Market Analyst 的技术面综合判断中拥有明确高于其他技术证据（几何形态、趋势模板、常规指标）的权重。

分两个子模块顺序开发：

- **Stage 1（本计划实现范围）：** 结构/事件识别层——交易区间探测、吸筹/派发经典事件识别、Phase A-E 判定、方向与权重输出。
- **Stage 2（后续迭代，见"后续迭代"一节，本计划不实现）：** Volume Spread Analysis（VSA）逐 K 线努力与结果背离打分，作为提升 Stage 1 置信度的辅助证据源。

## 核心原则

延续 `CHART_PATTERN_ANALYSIS_PLAN.md` 与 `MINERVINI_TREND_TEMPLATE_PLAN.md` 的原则：

1. **结构由代码识别，LLM 负责解释。** 不允许 LLM 仅凭 CSV 自行声称识别出某个威科夫事件或阶段。
2. **禁止未来数据。** 所有计算只能使用 `curr_date` 当日或之前的数据。
3. **使用自适应阈值。** 价格与成交量判据结合 ATR、价格比例、20 日均量比值，避免固定百分比在不同资产上失真。
4. **提供证据。** 每个识别到的事件必须包含日期、价格、成交量佐证和文字证据。
5. **允许中性。** 没有识别出清晰交易区间时，方向判断必须是 `neutral`，不得为了给出结论而勉强判定方向。
6. **权重是策略声明，不是回测产物。** `dominant_weight` 是项目级的固定常量，随工具结果一起返回，不由数据反推计算；具体数值后续可通过回测校准，但不是本计划的验收条件。
7. **不预判尚未形成的阶段。** Phase 判定只反映已经出现的事件序列；尚未出现的后续事件（例如还没有出现的 SOS）不得提前假设。

## 数据流

默认回看窗口 `look_back_days=504`（约两年交易日）。吸筹/派发交易区间常常持续数月甚至跨年，窗口过短会把尚未走完的区间截断成看不出结构的片段。

```text
Ticker + Analysis Date
          │
          ▼
load_ohlcv（缓存、代码规范化、日期截断，默认取约两年）
          │
          ▼
ATR + 交易区间探测（wyckoff_range）
          │
          ▼
吸筹事件识别（wyckoff_accumulation）  派发事件识别（wyckoff_distribution）
          │                                   │
          └───────────────┬───────────────────┘
                           ▼
              汇总方向 / 置信度 / 权重（wyckoff_bias）
                           │
                           ▼
                结构化 JSON 报告
                           │
                           ▼
     Market Analyst 以此为技术面结论主锚点，其余证据只能同向调节
```

## 算法设计

### 交易区间探测（`wyckoff_range.py`）

- 复用与 `chart_patterns.py` 一致的枢轴点检测（中心窗口确认局部高低点，默认 `pivot_span=3`）。
- 在回看窗口内寻找价格反复在一个相对稳定的高低边界之间震荡的区段：边界宽度需达到最低 ATR 倍数门槛，且区间内至少各有两次有效触碰上下边界。高、低边界的两组触点还必须在时间上有重叠（不能一组触点全部早于另一组），否则会把两个不同时期、互不相关的价位误配成同一个区间——实现过程中发现并修复了这个问题。
- 标记区间的 `start_date`、`range_high`、`range_low`，以及成交量高潮候选点（单日成交量显著高于此前 20 日均量，且伴随价格大幅波动）——这些候选点是后续 SC/BC 判定的输入，不在本模块直接下结论。
- 若窗口内找不到满足条件的区间，返回 `kind = "none"`，交由 `wyckoff_bias` 统一处理为中性。
- 判断一个区间"现在是否仍然有效"，用的是**当前收盘价与区间边界的距离**（不超过一个区间高度的缓冲），而不是"最近一次有效触碰枢轴点距今多少天"。吸筹/派发过程本身就会有长时间没有新极值出现的安静阶段（横盘等待），如果用触碰新枢轴点的时间来判断区间是否"过期"，会把仍然有效、只是暂时安静的结构错误地丢弃成 `neutral`。早期实现里确实这样做过（触碰点必须落在窗口最后约 60 个交易日内），后来改成价格邻近度判断。

### 吸筹事件识别（`wyckoff_accumulation.py`）

在已识别的候选区间基础上，按时间顺序尝试匹配以下经典事件，每个事件都有独立的量价判据：

- **PS（Preliminary Support，初步支撑）：** 下跌趋势中首次出现明显放量企稳。
- **SC（Selling Climax，抛售高潮）：** 加速下跌后出现的极端放量（相对 20 日均量的比值门槛）长下影或收盘明显回升。搜索范围是区间起点前后一段窗口内的**原始 K 线**，而不是只在已经聚类成区间边界的枢轴点里找——真实的抛售高潮经常发生在区间真正稳定下来之前，价格往往还会再多跌几天才见底，导致高潮那根 K 线的价位和最终区间边界有一段距离、不会被聚类进边界触点，如果只在边界触点里找就会漏掉（实现过程中通过真实行情复盘发现并修复了这个问题）。窗口内如果有多根 K 线都满足放量门槛，取**时间上最早**的一根，而不是成交量最大的一根——SC 的定义是"启动这个区间的那根 K 线"，如果按成交量选，后面 Phase C 里一根放量更夸张的 Spring/Terminal Shakeout 反而会被误判成 SC（合成数据测试发现的问题）。
- **AR（Automatic Rally，自动反弹）：** SC 之后的快速反弹，反弹高点初步定义区间上沿候选。
- **ST（Secondary Test，二次测试）：** 价格回落重新靠近 SC 附近区域，但成交量和跌幅小于 SC，验证支撑有效。
- **Spring / Terminal Shakeout：** 价格短暂跌破区间下沿（超出 ATR 缓冲），随后收盘收回区间内。Spring 和 Terminal Shakeout 是同一类 Phase C 测试的两种不同表现，不能用统一的"缩量"描述：Spring 通常缩量（安静吸筹，不引人注意）；Terminal Shakeout 则往往是放量的剧烈震仓（用力洗出浮筹）。两种量能特征都是合法的 Phase C 确认，工具输出的证据文字必须明确说明该次跌破属于哪一种，而不是笼统地假设一定缩量（早期实现里就是这个假设，被真实行情复盘推翻——NKE 2026-07-01 那次 spring 是 3.1 倍放量的 Terminal Shakeout，不是缩量 Spring）。
- **Test：** Spring 之后再次靠近区间下沿但不再创新低、量能进一步萎缩。
- **SOS（Sign of Strength，强势信号）：** 放量向上突破区间上沿，或区间内出现放量长阳线且收盘接近最高点。
- **LPS（Last Point of Support，最后支撑点）：** SOS 之后价格回调但不跌破新支撑（原区间上沿或 SOS 低点），缩量。
- **BU（Back Up / "Backing Up to the Creek"）：** LPS 之后价格再次靠近突破点做最后确认，随后继续上行。

### 派发事件识别（`wyckoff_distribution.py`）

吸筹侧的镜像逻辑，方向相反：

- **PSY（Preliminary Supply）**、**BC（Buying Climax）**、**AR（Automatic Reaction）**、**ST（Secondary Test）**、**UTAD（Upthrust After Distribution）**、**SOW（Sign of Weakness）**、**LPSY（Last Point of Supply）**、**UT（Upthrust）**。
- 判据与吸筹侧一一对应但方向相反（例如 UTAD 对应 Spring：短暂突破区间上沿后放量不足、收盘收回区间内）。

### Phase 判定

两侧模块各自基于已匹配的事件集合给出 `current_phase`（A-E）：

- **Phase A：** 只出现区间形成的初期事件（PS/SC/AR/ST 或 PSY/BC/AR/ST），趋势的下跌/上涨动能开始被遏制。
- **Phase B：** 区间内多次触碰边界但尚无 Spring/UTAD 或 SOS/SOW。
- **Phase C：** 出现 Spring/Test 或 UTAD（关键的"测试"阶段）。
- **Phase D：** 出现 SOS/LPS 或 SOW/LPSY，方向确认增强。
- **Phase E：** 价格确认脱离区间（呼应 `chart_patterns.py` 里箱体突破确认的 ATR 缓冲规则）。
- 若两侧都没有匹配到 Phase A 所需的最低事件集合，`current_phase = "undetermined"`。

### 方向 / 置信度 / 权重汇总（`wyckoff_bias.py`）

- 若吸筹侧识别到有效区间而派发侧没有（反之亦然），采用该侧结果。
- 若两侧都识别到区间（理论上少见，例如复杂结构），采用 Phase 更靠后（更接近 D/E）、事件证据更完整的一侧；打平时输出 `neutral` 并在 `weight_note` 中说明原因。
- 若两侧都没有识别到有效区间，`trading_range.kind = "none"`，`phase_bias = "neutral"`，`current_phase = "undetermined"`。
- `confidence`（0.0-1.0）：由已匹配事件数量、量能佐证清晰度、Phase 推进程度共同决定，规则与 `chart_patterns.py` 现有形态的置信度评分风格一致。
- `dominant_weight`：固定策略常量，默认 `0.6`，不随本次识别结果的强弱变化。

## 输出接口

工具名称：

```python
get_wyckoff_structure(
    symbol: str,
    curr_date: str,
    look_back_days: int = 504,
) -> str
```

返回 JSON 示例：

```json
{
  "symbol": "AAPL",
  "analysis_date": "2026-07-03",
  "trading_range": {
    "kind": "accumulation",
    "range_high": 195.4,
    "range_low": 178.2,
    "start_date": "2025-11-03",
    "status": "developing"
  },
  "events": [
    {
      "event": "selling_climax",
      "date": "2025-11-10",
      "price": 178.9,
      "volume_ratio": 2.4,
      "evidence": ["closing off the low on 2.4x 20-day avg volume after a sharp decline"]
    },
    {
      "event": "spring",
      "date": "2026-05-02",
      "price": 176.8,
      "volume_ratio": 0.7,
      "evidence": ["undercut range_low by 0.4 ATR on below-average volume, closed back inside range"]
    }
  ],
  "current_phase": "C",
  "phase_bias": "bullish",
  "confidence": 0.72,
  "dominant_weight": 0.6,
  "weight_note": "Wyckoff structural reading anchors the technical verdict; other technical evidence may adjust confidence within this direction but must not override it unless phase_bias is neutral/undetermined."
}
```

`trading_range.status` 取值 `forming`（区间尚未出现关键测试事件）、`developing`（已出现 Spring/UTAD 等 Phase C 事件）、`confirmed`（已出现 SOS/SOW 等 Phase D 事件）、`failed`（区间被无效突破打破且未纳入假突破逻辑，留给下一次调用重新识别新结构）。

## Market Analyst 接入

Market Analyst 必须：

1. 在最终报告前调用 `get_wyckoff_structure`。
2. 将 `phase_bias`、`current_phase` 与关键 `events` 作为技术面结论的主锚点，单独成段，先于其他技术证据呈现。
3. 应用冲突消解规则：
   - `phase_bias` 为 `bullish` 或 `bearish` 时，`get_chart_patterns`、`get_trend_template`、常规指标只能在该方向内调节置信度，不得给出相反方向的最终技术结论；如存在强烈冲突证据，报告需明确指出"与威科夫结构性解读冲突"，但仍以威科夫方向作为主线。
   - `phase_bias` 为 `neutral`（含 `trading_range.kind == "none"`）时，其他技术证据正常参与综合判断，不受压制。
4. 报告必须点名列出识别到的威科夫事件及其日期、价格，不得只写方向性结论而没有具体事件支撑。
5. Markdown 表格中新增一行反映 `current_phase` / `phase_bias` / `dominant_weight`。
6. 不得从原始 CSV 中额外虚构工具未识别出的事件或阶段。

## 文件结构

```text
tradingagents/dataflows/wyckoff_range.py
    共享交易区间探测（区间高低边界、成交量高潮候选点），复用 chart_patterns.py 的 Pivot/find_pivots

tradingagents/dataflows/wyckoff_events.py
    吸筹/派发共享的方向参数化事件识别引擎（实现过程中从两侧抽出，避免镜像逻辑重复两遍）：
    PS/PSY, SC/BC, AR, ST, Spring/UTAD, Test, SOS/SOW, LPS/LPSY, BU/UT + Phase A-E 判定 + confidence 评分

tradingagents/dataflows/wyckoff_accumulation.py
    吸筹侧薄封装：仅在 prior_trend == "down" 时调用 wyckoff_events 并打上 accumulation 标签

tradingagents/dataflows/wyckoff_distribution.py
    派发侧薄封装：仅在 prior_trend == "up" 时调用 wyckoff_events 并打上 distribution 标签

tradingagents/dataflows/wyckoff_bias.py
    汇总吸筹/派发两侧结果，输出最终 phase_bias / confidence / dominant_weight

tradingagents/agents/utils/wyckoff_tools.py
    LangChain 工具包装

tradingagents/agents/utils/agent_utils.py
    工具公共导出

tradingagents/agents/analysts/market_analyst.py
    工具绑定与提示词权重规则

tradingagents/graph/trading_graph.py
    market ToolNode 注册

tests/test_wyckoff_range.py
    共享交易区间探测的合成 OHLCV 单元测试

tests/test_wyckoff_events.py
    共享事件引擎的证据文字单元测试（放量/缩量 Spring 的证据文字区分）

tests/test_wyckoff_accumulation.py
    吸筹侧合成 OHLCV 单元测试

tests/test_wyckoff_distribution.py
    派发侧合成 OHLCV 单元测试

tests/test_wyckoff_bias.py
    方向/置信度/权重汇总逻辑单元测试

tests/test_market_toolnode.py
    追加 get_wyckoff_structure 的 ToolNode 接线测试
```

## 测试计划

测试使用合成 OHLCV，避免网络行情变化影响算法验证。

- 交易区间探测：能在震荡区间中识别出高低边界；纯趋势行情（无震荡）应返回 `kind = "none"`。长时间横盘、没有新枢轴点触碰但价格仍在区间附近时，区间不应失效；价格已经远离区间（超过一个区间高度）之后，旧区间不应再被识别为当前有效结构。
- 吸筹侧：构造教科书式序列（SC→AR→ST→Spring→Test→SOS→LPS）应按顺序识别全部事件，且 `current_phase` 推进到 D 或 E；只构造到 Spring 为止的序列应停在 Phase C；没有放量佐证的候选点不得被识别为 SC/Spring/SOS；抛售高潮价位偏离最终区间边界（不在边界聚类触点内）时依然应该被识别为 SC；窗口内有更晚、成交量更夸张的候选（例如放量 Spring）时，仍应选时间上最早的一根作为 SC。
- 事件引擎：放量 Spring/UTAD 的证据文字必须提示"剧烈震仓"，缩量的必须提示"安静吸筹"，不能只报数字不给解读。
- 派发侧：镜像用例（BC→AR→ST→UTAD→SOW→LPSY），断言同上。
- 汇总逻辑：两侧都无区间时输出 `neutral` 且 `dominant_weight` 仍然返回；只有一侧识别到区间时采用该侧结果；`confidence` 随事件数量与质量单调变化的基本合理性检查。
- 分析日期之后的数据不得参与识别结果（未来数据泄漏检查，做法与 `test_chart_patterns.py` 一致）。
- Market ToolNode 必须注册 `get_wyckoff_structure`。

## 验收标准

- 新增测试全部通过。
- 直接受影响的测试文件不出现回归；本次改动涉及共享工具导出（`agent_utils.py`）与图节点注册（`trading_graph.py`），按 CLAUDE.md 的验证策略需额外跑一次 `pytest -q` 和 `ruff check .` 全量检查。
- `ruff check` 通过。
- Market Analyst 可以实际调用新工具，报告中体现威科夫结论作为技术面主锚点。
- 输出不包含分析日期之后的数据。
- 每个识别到的事件都有可审计的日期、价格与成交量证据。

## 当前实施状态

- [x] 交易区间探测（`wyckoff_range.py`，含高低触点时间重叠约束）
- [x] 吸筹/派发共享事件识别引擎（`wyckoff_events.py`）
- [x] 吸筹侧事件识别与 Phase 判定（`wyckoff_accumulation.py`）
- [x] 派发侧事件识别与 Phase 判定（`wyckoff_distribution.py`）
- [x] 方向/置信度/权重汇总（`wyckoff_bias.py`）
- [x] LangChain 工具包装（`wyckoff_tools.py`）
- [x] Market Analyst 与 market ToolNode 接入
- [x] 合成行情单元测试（区间探测、吸筹、派发、汇总、ToolNode 接线）
- [x] 完整项目回归测试（`pytest -q` + `ruff check .`）

验证结果：

```text
新增 Wyckoff 测试：20 passed（区间 5、事件引擎 2、吸筹 5、派发 4、汇总 4，另加 test_market_toolnode.py 接线断言更新）
完整测试：544 passed, 2 skipped（跳过项与本次改动无关：langchain_aws 未安装、DEEPSEEK_API_KEY 未设置）
ruff check .：All checks passed

真实行情复盘（2026-07-07，抽样，共两轮）：
第一轮（修复 SC 搜索范围后）：AAPL/COIN/NKE 识别为 accumulation，TSLA/NVDA/GOOGL/PLTR 识别为 distribution；QQQ（两年阶梯式上涨，非典型横盘）、AMD/META/AMZN/NFLX/MSFT 仍为 neutral，符合"没有清晰吸筹/派发结构时不得强行给方向"的原则。
第二轮（用户指出 NKE 2026-07-01 的放量 Spring 证据文字没有体现量能特征后）：修复 SC 时间优先级 + Spring/UTAD 证据文字量能感知，NKE 正确报告"3.1 倍放量的 Terminal Shakeout"；部分标的的具体 Phase 因 SC 选取更准确而调整（如 TSLA C→E、COIN C→A），方向本身保持稳定。
```

## Stage 2 实施状态

- [x] 逐 K 线 VSA 检测器（8 种经典效果/结果信号，`wyckoff_vsa_signals.py` 6 个仅需单根 K 线的检测器 + `wyckoff_vsa_range_signals.py` 2 个需要交易区间边界的检测器；两个文件系因 150 行/文件上限拆分）
- [x] VSA 编排层（`wyckoff_vsa.py`）：限定在活跃交易区间窗口内、按 `curr_date` 截断、confirming/contradicting 判定、置信度调整（单信号 ±0.05，总量上限 ±0.15）
- [x] 接入 `wyckoff_bias.py`：中性读数不受影响，非中性读数新增 `vsa_signals` 字段并调整 `confidence`
- [x] 合成行情单元测试（bar-only 检测器、range-aware 检测器、编排层、`wyckoff_bias.py` 接线）
- [x] 隔离回归测试（按 CLAUDE.md 默认验证策略，仅测受影响文件，未触及跨模块共享状态，无需全量套件）

验证结果：

```text
隔离测试：26 passed（bar-only 检测器 9、range-aware 检测器 5、编排层 5、wyckoff_bias 接线 6、
market ToolNode 接线 1，覆盖 tests/test_wyckoff_vsa_bar_signals.py、
tests/test_wyckoff_vsa_range_signals.py、tests/test_wyckoff_vsa.py、
tests/test_wyckoff_bias.py、tests/test_market_toolnode.py）
ruff check（8 个新增/改动文件）：All checks passed
```

设计文档：`docs/superpowers/specs/2026-07-09-wyckoff-vsa-design.md`
实施计划：`docs/superpowers/plans/2026-07-09-wyckoff-vsa-implementation.md`

## 后续迭代

1. ~~Stage 2：VSA（Volume Spread Analysis）模块~~ — 已完成，见上「Stage 2 实施状态」。
2. ~~用类似 `scripts/backtest_chart_patterns.py` 的 walk-forward 脚本对 `dominant_weight`（默认 0.6）、`confidence` 评分公式、各事件的成交量比值门槛，以及新增的 VSA 信号阈值（`NARROW_SPREAD_ATR` 等）做历史校准。~~ — 报告脚本已完成，见 `scripts/backtest_wyckoff.py`（`docs/superpowers/specs/2026-07-09-wyckoff-calibration-design.md`）；脚本只产出按 `(current_phase, vsa_effect)` 分桶的胜率报告，具体常量调整仍需人工阅读报告后决定，非本次范围。
3. ~~复杂结构处理：目前区间/事件识别假设一个回看窗口内出现单一主导交易区间；后续可扩展处理"区间失败后在更大范围重新构筑新区间"的复合结构（呼应 `chart_patterns.py` 里 `structure_may_be_expanding` 的思路）。~~ — 调研后发现该字面描述的场景已大体被 `detect_trading_range` 自身的候选筛选逻辑覆盖（优先选最近触及的区间、价格漂移过远即排除旧区间）；真正的缺口是 Phase D/E 达成后从未检查突破是否真的站稳。已实现 `wyckoff_invalidation.py`（`docs/superpowers/specs/2026-07-09-wyckoff-invalidation-design.md`）：突破后若价格收盘反向穿越原区间边界，读数标记为 `invalidated`，`phase_bias` 强制为 `neutral`、`confidence` 归零，不再作为有效方向性结论呈现。
4. 评估是否需要把威科夫结论的权重规则延伸到 bull/bear researcher 与 risk 辩论等下游 Agent；这会涉及修改目前尚未被本项目定制过的上游文件，需要用户单独明确批准后才能进行。

> 本功能用于研究和辅助分析，不构成投资建议，也不会自动执行交易。
