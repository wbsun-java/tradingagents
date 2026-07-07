# Minervini Trend Template Plan

## 目标

在 `get_chart_patterns`（几何形态识别）之外，为 Market Analyst 增加一套独立的、基于均线和52周高低点的量化"阶段筛选"工具，来源于 Mark Minervini《股票魔法师》里的趋势模板（Trend Template）。这不是一种图形形态，而是一套8条数值门槛判断，用来判断股票当前是不是处于适合做多的"第二阶段上升趋势"。

## 核心原则

延续 `CHART_PATTERN_ANALYSIS_PLAN.md` 的原则：全部由代码计算，LLM 只负责解释结果，不允许 LLM 自行判断"是不是符合趋势模板"。

## 八条标准

1. 现价 > 150日均线 且 > 200日均线
2. 150日均线 > 200日均线
3. 200日均线至少上升1个月
4. 50日均线 > 150日均线 > 200日均线
5. 现价 > 50日均线
6. 现价比52周最低点高至少30%
7. 现价离52周最高点不超过25%
8. 相对强度：股票价格相对基准指数（默认 SPY）的比值创新高

前7条直接用原版书里的门槛数字，没有做任何调整；第8条是简化近似，说明见下。

## 关于相对强度（第8条）的简化

Minervini/IBD 原版的 RS 排名是把这只股票和全市场几千只股票比较，排出百分位。这个项目目前是单只股票分析，没有全市场数据库做这种排名。这里用的替代指标是：**股票收盘价 / 基准指数收盘价** 这条比值曲线，如果它现在处于近一年的最高点，就判定相对强度达标——逻辑是"跑赢大盘并且还在持续跑赢，创出相对强度新高"，但这不是精确的百分位排名，只是一个方向性的近似。

基准指数默认用 SPY，可以通过工具参数覆盖成其他指数；如果基准数据拉取失败，这一条会被跳过（不计入分母），不会导致整个工具报错。

## 输出接口

```python
get_trend_template(symbol: str, curr_date: str, benchmark: str = "SPY") -> str
```

返回 JSON，包含 `stage_2_uptrend`（是否8条全过）、`passed_count`/`total_criteria`、每条的布尔结果、以及均线/52周高低点的具体数值。

## 文件结构

```text
tradingagents/dataflows/trend_template.py
    八条标准的计算核心

tradingagents/agents/utils/trend_template_tools.py
    LangChain 工具包装

tradingagents/agents/utils/agent_utils.py
    工具公共导出

tradingagents/agents/analysts/market_analyst.py
    工具绑定与提示词约束

tradingagents/graph/trading_graph.py
    market ToolNode 注册

tests/test_trend_template.py
    合成行情单元测试（上升趋势全过、下降趋势全不过、历史不足不报错、相对强度两种方向、benchmark拉取失败的降级）

tests/test_market_toolnode.py
    ToolNode 接线回归测试
```

## 当前实施状态

- [x] 8条标准的计算逻辑（含相对强度近似）
- [x] 历史数据不足200天时不报错，相关标准直接判否
- [x] 基准指数拉取失败时优雅降级，不影响其余7条
- [x] Market Analyst 和 market ToolNode 接入
- [x] 单元测试（6个）+ ToolNode 接线测试
- [x] 用真实数据（AAPL、TSLA）验证：AAPL 7/8 通过，TSLA 3/8（现价跌破50/150/200日均线），符合预期
- [ ] 相对强度用更严谨的方法校准（比如换成更长/更短的比较窗口，或者接入多只股票做近似百分位）
- [ ] 用 `scripts/backtest_chart_patterns.py` 同类思路做一个针对趋势模板的历史校验脚本

验证结果：

```text
完整测试：524 passed, 2 skipped
新增趋势模板测试：6 passed
ruff check .：All checks passed
```

## 后续

下一步做 **VCP（波动收缩形态）**：识别价格从高点开始的一系列逐步收窄的回调，且回调时成交量萎缩，最后放量突破前高。这是一个真正的形态识别，会作为新的独立模块加入，`target_price` 沿用现有"突破价 ± 形态自身高度"的惯例。

> 本功能用于研究和辅助分析，不构成投资建议，也不会自动执行交易。
