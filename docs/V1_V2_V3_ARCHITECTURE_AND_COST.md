先给你一个核心结论：

**V1、V2、V3 的主要区别只在“如何决定执行哪些节点、以什么顺序执行”。**  
`JD / Company / Salary / Match / Report` 这些业务节点是三套版本共用的，并没有各写一套。

另外需要特别区分：

- **MCP/Tavily 负责搜索**
- **LLM 不负责搜索**
- 搜索结果回来以后，当前项目的 `Company` 和 `Salary` 都使用 Python 规则解析，不使用 LLM 分析原始搜索结果

---

## 一、V1：Fixed Router 固定路由

### 执行链路

```text
START
  ↓
Intake
  ↓
JD
  ↓
根据用户选择的分析目标，由代码确定节点
  ├── Company ─┐
  ├── Salary ──┼→ Report → END
  └── Match ───┘
```

如果选择了全部分析目标：

```text
Intake → JD → Company、Salary、Match 并行 → Report → END
```

如果只选择岗位匹配：

```text
Intake → JD → Match → Report → END
```

固定路由代码在 [builder.py](/Users/xuyihao/projects/job-agent/app/graph/builder.py:43)。

### V1 谁负责路由

V1 没有使用 Supervisor，也没有让 LLM 判断下一个节点。

它直接根据：

```python
analysis_targets = ["company", "salary", "match"]
```

由代码返回需要执行的节点：

```python
def route_fixed_agents(state):
    targets = state.get("analysis_targets")
    return targets or ["company", "salary", "match"]
```

因此 V1 的特点是：

- 路由成本最低
- 路由结果稳定
- 不会选错节点
- 不具备根据自然语言动态判断任务的能力

---

## 二、V2：LLM Supervisor 循环决策

### 执行链路

```text
START
  ↓
Intake
  ↓
JD
  ↓
Supervisor
  ↓
选择一个节点
  ↓
Company / Salary / Match
  ↓
Supervisor
  ↓
继续选择下一个节点
  ↓
……
  ↓
Supervisor 选择 Report
  ↓
Report
  ↓
END
```

完整分析时可能是：

```text
Intake
→ JD
→ Supervisor
→ Company
→ Supervisor
→ Match
→ Supervisor
→ Salary
→ Supervisor
→ Report
→ END
```

但 Company、Salary、Match 的实际顺序由 LLM 决定，不一定和上面一致。

代码在 [builder.py](/Users/xuyihao/projects/job-agent/app/graph/builder.py:58)。

### Supervisor 每次拿到什么

每次执行完成一个业务节点后，再回到 Supervisor。Supervisor 会拿到：

```json
{
  "question": "分析岗位匹配度、公司情况和预计薪资",
  "completed_agents": ["company", "match"]
}
```

然后调用 LLM：

```python
result = await self._router_model.ainvoke(
    [
        (
            "system",
            "你是岗位分析工作流的路由器……"
        ),
        (
            "human",
            json.dumps(
                {
                    "question": question,
                    "completed_agents": completed_agents,
                },
                ensure_ascii=False,
            ),
        ),
    ]
)
```

LLM 返回结构化结果：

```python
RouterDecision(
    next_agent="salary",
    reason="用户需要薪资信息，并且 salary 尚未执行",
)
```

相关实现位于 [model.py](/Users/xuyihao/projects/job-agent/app/services/model.py:249)。

### V2 的特点

- 每次只决定下一个节点
- 每执行完一个节点，就重新调用一次 LLM
- 能展示完整的 Supervisor 决策过程
- LLM 调用次数最多
- 成本和延迟通常也是三个版本里最高的
- 纯 LLM 路由仍可能重复选择、提前选择 Report，因此代码中还需要最大步数等保护

---

## 三、V3：Planner 一次性规划 + 规则校验

### 执行链路

```text
START
  ↓
Intake
  ↓
JD
  ↓
Planner（LLM 只调用一次）
  ↓
生成执行计划
  ↓
代码校验、去重、兜底
  ↓
Company、Salary、Match 按计划并行执行
  ↓
Report
  ↓
END
```

例如 Planner 一次性返回：

```json
{
  "selected_agents": ["company", "salary", "match"],
  "reason": "用户需要公司、薪资和岗位匹配分析"
}
```

后端对结果进行校验：

```python
selected_agents = remove_duplicates(plan.selected_agents)

if not selected_agents:
    selected_agents = ["company", "salary", "match"]
```

然后 LangGraph 根据这个列表一次性调度节点。

代码位置：

- [builder.py](/Users/xuyihao/projects/job-agent/app/graph/builder.py:74)
- [planner.py](/Users/xuyihao/projects/job-agent/app/graph/nodes/planner.py:15)
- [hybrid.py](/Users/xuyihao/projects/job-agent/app/graph/routers/hybrid.py:1)

### V3 的特点

- LLM 负责理解用户意图，并一次性制定计划
- 后端规则负责校验计划是否合法
- Company、Salary、Match 可以并行执行
- Planner 通常只调用一次 LLM
- 比 V2 成本更低、延迟更小
- 比 V1 更灵活
- 是当前三个版本中工程上最平衡的一种

---

# 四、每个节点到底使用规则还是 LLM

| 节点 | V1 | V2 | V3 | 主要职责 |
|---|---|---|---|---|
| Intake | 规则 | 规则 | 规则 | 校验、清洗输入，读取用户资料 |
| JD | LLM，失败后规则降级 | LLM，失败后规则降级 | LLM，失败后规则降级 | 从 JD 提取技能、经验、学历等 |
| Company | MCP 搜索 + 规则解析 | MCP 搜索 + 规则解析 | MCP 搜索 + 规则解析 | 搜索并提取公司公开信息 |
| Salary | MCP 搜索 + 规则解析 | MCP 搜索 + 规则解析 | MCP 搜索 + 规则解析 | 搜索并计算薪资区间 |
| Match | 规则 | 规则 | 规则 | 计算技能、经验、学历匹配分 |
| Supervisor | 不存在 | LLM，多次调用 | 不存在 | 每次决定下一个节点 |
| Planner | 不存在 | 不存在 | LLM，一次调用 | 一次性决定需要执行的节点 |
| Report | LLM，失败后模板降级 | LLM，失败后模板降级 | LLM，失败后模板降级 | 根据已有结构化结果生成报告 |

这里说的是你当前 `MODEL_BACKEND=openai` 的运行方式。

---

## 五、JD 到底是规则解析还是 LLM 解析

这个不是由 V1/V2/V3 决定的，而是由模型后端决定的。

### 当前 OpenAI 模式

V1、V2、V3 都使用 LLM 解析 JD：

```python
self._jd_model = self._model.with_structured_output(JDInfo)
```

调用：

```python
result = await self._jd_model.ainvoke(
    [
        (
            "system",
            "从招聘JD中抽取结构化要求。"
            "只记录原文明确表达的内容，不要猜测。",
        ),
        ("human", jd_text),
    ]
)
```

因为绑定了：

```python
with_structured_output(JDInfo)
```

所以模型不能随意返回一段文字，而是要返回类似：

```python
JDInfo(
    required_skills=["Java", "Python", "MySQL"],
    required_experience_years=3,
    education_requirement="本科及以上",
    responsibilities=[...],
)
```

代码在 [model.py](/Users/xuyihao/projects/job-agent/app/services/model.py:237)。

### LLM 调用失败时

例如：

- API Key 错误
- 网络错误
- 模型无权限
- 输出不符合结构
- 请求超时

JD 节点会降级到本地规则：

```python
try:
    jd_info = await deps.model.extract_jd(jd_text)
except Exception:
    jd_info = await DeterministicAnalysisModel().extract_jd(jd_text)
```

本地规则主要通过：

- 已知技能关键词表
- 正则表达式提取工作年限
- 关键词识别学历

因此准确地说：

> V1、V2、V3 默认都用 LLM 解析 JD；LLM 失败时，三者都会降级为规则解析。

如果设置：

```env
MODEL_BACKEND=mock
```

那么三个版本都会直接使用本地规则，不调用 OpenAI。

---

# 六、Company 和 Salary 的搜索、解析方式

## Company 节点

### 第一步：MCP 搜索

Company 节点构造类似这样的查询：

```text
米哈游 公司 官网 业务 规模
```

然后调用：

```python
results = await deps.search.search(query)
```

如果当前配置的是 MCP 搜索网关，实际链路是：

```text
Company Node
    ↓
SearchGateway
    ↓
MCP Client
    ↓
搜索 MCP Server
    ↓
Tavily API
    ↓
互联网搜索结果
```

代码在 [company.py](/Users/xuyihao/projects/job-agent/app/graph/nodes/company.py:21)。

### 第二步：规则过滤和解析

搜索结果返回后，没有交给 LLM，而是经过本地 Python 规则：

```python
matched_results = filter_company_results(
    company_name,
    results,
)
```

它会检查：

- 标题和正文是否包含目标公司名
- 是否属于允许的公司别名
- 是否出现其他公司的混淆内容
- 来源是否具有足够可信度

然后：

```python
company_info = build_company_info(
    company_name,
    matched_results,
)
```

提取：

- 企业性质
- 上市情况
- 公开业务
- 总部位置
- 员工规模
- 可信度
- 来源

核心规则在 [company_analyzer.py](/Users/xuyihao/projects/job-agent/app/tools/company_analyzer.py:167)。

所以三个版本都是：

```text
MCP 搜索 → 公司名匹配 → 来源过滤 → 关键词/正则解析
```

**没有任何一个版本让 LLM 直接分析 Company 的原始搜索结果。**

---

## Salary 节点

### 第一步：公司专属搜索

例如：

```text
米哈游 上海 AI 后端 相关岗位 薪资 招聘 月薪
```

### 第二步：规则筛选

搜索结果必须同时满足一定条件：

- 公司名称匹配
- 岗位方向匹配
- 城市匹配
- 包含明确的薪资表达
- 薪资数字在合理范围内

例如通过正则识别：

```text
25K-40K
30k·16薪
月薪 30000-45000
```

### 第三步：市场降级搜索

如果公司专属薪资找不到，才会使用市场范围：

```text
上海 AI 后端工程师 工资 薪资 招聘 月薪
```

并明确标记：

```text
这是市场参考，不是米哈游公司的直接薪资证据
```

最后通过规则计算中位区间、样本数和可信度。

代码位置：

- [salary.py](/Users/xuyihao/projects/job-agent/app/graph/nodes/salary.py:74)
- [salary_calculator.py](/Users/xuyihao/projects/job-agent/app/tools/salary_calculator.py:190)

因此 Company 和 Salary 在三个版本里都是：

```text
MCP/Tavily 搜索
       ↓
Python 规则过滤
       ↓
Python 规则解析
       ↓
形成结构化信息
```

LLM 最后只会在 Report 节点看到已经过滤过的结构化结果，而不会直接看到全部原始搜索内容。

---

# 七、Match 节点为什么不用 LLM

Match 是确定性评分：

```text
技能：70 分
经验：20 分
学历：10 分
总分：100 分
```

例如：

```python
skill_score = matched_skills / required_skills * 70
experience_score = ...
education_score = ...
total_score = skill_score + experience_score + education_score
```

代码在 [match_scorer.py](/Users/xuyihao/projects/job-agent/app/tools/match_scorer.py:38)。

不用 LLM 的好处是：

- 相同输入一定得到相同分数
- V1/V2/V3 可以公平比较
- 分数具有可解释性
- 不产生额外 Token 成本
- 不会出现模型主观给出 95 分、但说不清依据的问题

---

# 八、Report 节点使用 LLM 做什么

Report 节点不会再次搜索，也不应该生成新的事实。

它拿到：

```text
JD 结构化结果
Company 结构化结果
Salary 结构化结果
Match 结构化结果
Sources
```

然后让 LLM 把这些内容组织为自然语言报告：

```python
report = await self._model.ainvoke(
    [
        (
            "system",
            "只允许根据输入中已有的结构化事实生成报告。"
            "不得补充、推断或编造不存在的信息。",
        ),
        (
            "human",
            json.dumps(report_payload, ensure_ascii=False),
        ),
    ]
)
```

如果报告模型调用失败，则使用本地模板拼接。

所以 Report 属于：

```text
LLM 表达和总结
而不是 LLM 搜索或事实发现
```

---

# 九、Token 是怎么获得的

你的理解基本正确，但要稍微修正一点：

> `ainvoke()` 返回模型回答；Token 数据存在 OpenAI 响应的 usage metadata 中。项目通过 LangChain callback 在调用外层收集这些数据，而不是让业务代码直接从 `result` 中取一个 metrics 对象。

## 原始模型响应

普通的：

```python
response = await model.ainvoke(messages)
```

返回的通常是 `AIMessage`，其中可能包含：

```python
response.usage_metadata
```

形式类似：

```python
{
    "input_tokens": 1250,
    "output_tokens": 280,
    "total_tokens": 1530
}
```

OpenAI 原始响应也会包含类似的 usage 信息，只是 LangChain 帮我们统一包装了字段。

## 项目中的收集方式

当前项目使用：

```python
from langchain_core.callbacks import get_usage_metadata_callback
```

例如 JD 节点：

```python
with get_usage_metadata_callback() as usage:
    jd_info = await deps.model.extract_jd(state["jd_text"])

usage_result = token_usage(usage)
```

`await` 完成后，模型响应已经返回，这时 callback 中就能取得本次调用的 Token 使用量。

然后汇总：

```python
def token_usage(callback):
    metadata = list(callback.usage_metadata.values())

    input_tokens = sum(
        int(item.get("input_tokens", 0))
        for item in metadata
    )

    output_tokens = sum(
        int(item.get("output_tokens", 0))
        for item in metadata
    )

    total_tokens = sum(
        int(item.get("total_tokens", 0))
        for item in metadata
    )

    return {
        "token_usage": total_tokens or input_tokens + output_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
```

代码在 [common.py](/Users/xuyihao/projects/job-agent/app/graph/nodes/common.py:13)。

随后存入节点指标：

```python
NodeMetric(
    node="jd",
    latency_ms=5796,
    input_tokens=1250,
    output_tokens=280,
    token_usage=1530,
    model_calls=1,
)
```

LangGraph State 会累积每个节点的 `NodeMetric`，API 最后再汇总并返回前端。

---

# 十、成本是怎么计算的

以当前 `gpt-4.1-mini` 为例，项目配置的是：

```text
输入：$0.40 / 1,000,000 tokens
输出：$1.60 / 1,000,000 tokens
```

这也与当前官方标准价格一致。[OpenAI GPT-4.1 mini 文档](https://developers.openai.com/api/docs/models/gpt-4.1-mini)

计算公式：

```python
input_cost = input_tokens / 1_000_000 * 0.40
output_cost = output_tokens / 1_000_000 * 1.60

total_cost = input_cost + output_cost
```

项目里的实际代码相当于：

```python
amount = (
    Decimal(input_tokens) * input_price
    + Decimal(output_tokens) * output_price
) / Decimal(1_000_000)
```

代码在 [costs.py](/Users/xuyihao/projects/job-agent/app/services/costs.py:33)。

## 举例

假设一次 JD 解析：

```text
输入：2,000 tokens
输出：300 tokens
```

输入成本：

```text
2,000 ÷ 1,000,000 × $0.40
= $0.0008
```

输出成本：

```text
300 ÷ 1,000,000 × $1.60
= $0.00048
```

总成本：

```text
$0.0008 + $0.00048
= $0.00128
```

大约是人民币不到一分钱。

---

# 十一、三个版本的典型 LLM 调用次数

假设用户选择完整分析：Company、Salary、Match。

## V1

```text
JD：1 次
Report：1 次
```

总计通常：

```text
2 次 LLM 调用
```

Company、Salary、Match 都不调用 LLM。

## V2

```text
JD：1 次
Supervisor → Company：1 次
Supervisor → Salary：1 次
Supervisor → Match：1 次
Supervisor → Report：1 次
Report：1 次
```

总计通常：

```text
6 次 LLM 调用
```

所以 V2 最适合展示动态 Agent 决策，但成本和延迟最高。

## V3

```text
JD：1 次
Planner：1 次
Report：1 次
```

总计通常：

```text
3 次 LLM 调用
```

无论 Planner 最后选择一个还是三个业务节点，Company、Salary、Match 本身都不会增加 LLM 调用。

---

最后可以把三个版本概括成：

```text
V1：代码决定执行计划
V2：LLM 每一步决定下一个节点
V3：LLM 一次性制定计划，代码负责校验和执行
```

而节点能力始终是：

```text
JD      → LLM 结构化抽取，失败时规则降级
Company → MCP 搜索 + 规则解析
Salary  → MCP 搜索 + 规则解析
Match   → 本地规则评分
Report  → LLM 汇总，失败时模板降级
```
