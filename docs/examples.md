# Examples

## Bug fix

Request:

```text
$cs 修复库存不足时订单仍被提交的问题
```

At the start, the Agent runs:

```bash
python3 .codestable/tools/cs_knowledge.py brief \
  --task '修复库存不足时订单仍被提交的问题'
```

After identifying `src/orders/service.py` and `OrderService.create`, it refreshes the brief with that scope. The brief may reveal:

- an accepted local-transaction decision;
- a stable inventory error code;
- a rollback acceptance rule;
- a known row-lock performance risk.

The Agent then implements and tests normally. It records one task note and cards only for newly established or changed long-term truths.

## New interface

A task adding an export API may create cards in:

- `requirements`: export format and filtering rules;
- `interfaces`: endpoint, request, response and failure contract;
- `data-model`: snapshot fields or cursor state;
- `compatibility`: additive API/version behavior;
- `performance-risks`: maximum export size and streaming constraint;
- `security-boundaries`: tenant/auth scope;
- `acceptance`: matrix for empty, large, unauthorized and partial-failure cases;
- `decisions`: synchronous vs asynchronous export choice.

It should not create all categories mechanically. Empty categories remain explicit gaps in the next brief.

## Changed decision

Suppose an old card says:

```text
K-20260701-090000-01-a1b2c3d4
订单导出同步生成 CSV。
```

The system now adopts asynchronous object-storage exports. The new decision card includes:

```json
{
  "category": "decisions",
  "title": "大批量订单导出采用异步作业",
  "knowledge": "超过同步阈值的订单导出进入异步作业并返回 job id。",
  "rationale": "同步请求会超过网关超时并占用应用 worker。",
  "implications": [
    "接口需要 job status 查询",
    "对象下载链接必须有租户和时效边界"
  ],
  "confidence": "accepted",
  "status": "current",
  "supersedes": ["K-20260701-090000-01-a1b2c3d4"]
}
```

The old card remains in Git history and the Wiki, but normal briefs omit it.

## No durable learning

A task that only updates a one-off fixture may have:

```json
{
  "task": {
    "title": "更新一次性演示数据",
    "status": "completed",
    "summary": "替换了演示环境的过期样例。",
    "result": "演示页面恢复。",
    "verification": ["manual demo smoke check"],
    "knowledge_summary": "只写 task-note；一次性演示数据没有未来可复用的稳定结论。"
  },
  "items": []
}
```

CodeStable still writes a task note. It does not manufacture a long-term card just to fill a category.

## 完整示例：D-0007 履约事件演进

这是合成案例，不对应任何真实组织、仓库或用户。

### 应长期保留的决策

`D-0007` 的原子决策卡应保留：

- 原始失败模式：数据库已经提交，但消息发布失败；
- 业务不变量：发货任务和 outbox 记录同一事务持久化；
- 提交点：消息发送发生在事务提交之后；
- 交付语义：dispatcher 至少一次发布，消费者按 `event_id` 幂等；
- 依赖边界：领域层不依赖具体消息客户端；
- 主要替代方案：直接发布和分布式两阶段提交，以及未采用理由；
- 运维后果：允许重复投递，但不允许业务事件永久丢失；
- 验证原子性、失败重试和幂等性的集成测试；
- 状态、适用仓库范围、来源任务和取代关系。

这些内容跨消息系统实现仍会限制未来设计，所以值得长期保留。客户端版本、
临时重试次数、调试命令、中间补丁、事故原始日志、机器名和一次性部署细节
只进入任务记录或受控档案。已经失效的旧路径可留在历史范围中，但不应冒充
当前有效引用。

示意卡片：

```json
{
  "category": "decisions",
  "title": "D-0007 发货事件事务 outbox",
  "knowledge": "发货任务与待发布事件必须在同一数据库事务中持久化；提交后由独立 dispatcher 至少一次发布，消费者按 event_id 幂等，领域层不依赖具体消息客户端。",
  "context": "直接发布可能产生数据库成功但事件永久丢失的部分成功。",
  "rationale": "本地事务能以较小边界保证业务记录和待发布事件同时存在。",
  "alternatives": ["数据库提交后直接发布", "分布式两阶段提交"],
  "consequences": ["允许 dispatcher 重试和重复投递", "消费者必须按 event_id 幂等"],
  "future_use": [
    {"change": "替换消息系统", "actor": "消息适配器维护者", "constraint": "不得绕过事务 outbox"},
    {"change": "调整 dispatcher 并发或批量策略", "actor": "投递维护者", "constraint": "至少一次投递与事件 ID 幂等保持不变"}
  ],
  "scopes": [
    {"repository": "self", "path": "shipment/service.py", "symbol": "create_shipment"},
    {"repository": "shared-contracts", "path": "events/shipment.py", "symbol": "ShipmentCreated"},
    {"repository": "future-messaging", "path": "events/shipment.py", "symbol": "ShipmentCreated"}
  ],
  "topics": ["shipment-flow"],
  "evidence": [
    {
      "kind": "test",
      "artifact": "ShipmentTests.test_transactional_outbox",
      "result": "业务记录和 outbox 同时提交或回滚",
      "supports": "发货任务与待发布事件共享事务提交点"
    },
    {
      "kind": "test",
      "artifact": "ConsumerTests.test_event_id_idempotency",
      "result": "重复事件 ID 只产生一次业务效果",
      "supports": "消费者按 event_id 幂等"
    }
  ],
  "confidence": "accepted",
  "status": "current",
  "supersedes": ["K-D-0006"],
  "supersession_reason": "旧方案不能保证业务事件不丢失。"
}
```

`future-messaging` 未配置时仍可检索，但引用检查必须报告“无法验证”，不能
报告文件缺失。`shared-contracts` 配置本地映射后才能验证仓库内路径。

### 六个月后的替换任务

任务是“替换消息系统，并为 dispatcher 增加批量发送”。如果 D-0007 确实
改变了工作，任务记录可写：

```json
{
  "card_id": "K-D-0007",
  "card_revision": 1,
  "use": "changed-design",
  "detail": "把改动限制在发布适配器和 dispatcher，保留业务事务内的 outbox 写入。",
  "before": "任务允许业务层直接调用新的消息客户端。",
  "after": "最终只替换发布适配器，并在 dispatcher 中增加批量发送。",
  "evidence": [
    {
      "kind": "implementation",
      "artifact": "shipment/service.py#create_shipment",
      "result": "领域入口仍只写发货任务和 outbox。",
      "supports": "对应 D-0007 的事务提交点与依赖边界。"
    },
    {
      "kind": "test",
      "artifact": "ShipmentTests.test_publish_failure_is_retryable",
      "result": "发布失败后原 outbox 记录仍可重试。",
      "supports": "验证至少一次发布且不重新创建业务记录。"
    },
    {
      "kind": "test",
      "artifact": "ConsumerTests.test_duplicate_event_id",
      "result": "重复 event_id 只产生一次业务效果。",
      "supports": "验证 D-0007 的消费端幂等要求。"
    }
  ]
}
```

这条记录足以证明影响，因为它同时给出被使用卡片、使用类型、公开的方案
差异、可核查产物、观察结果和逐项对应关系。只在最终回复列出 D-0007、只
写“沿用 outbox”、实现本来就符合但没有具体检查结论，或完成后依据 diff
反向补写引用，都只能算“看过”，不能算“用过”。

### 是否新增决策卡

“dispatcher 必须按业务实体保持相对顺序，并由契约约束批量上限语义”在
获得用户/架构决定或接口与测试确认、且未来替换消息系统仍须遵守时，可以
创建正交的 `D-0008` 卡。它未被 D-0007 完整覆盖，但也没有推翻 D-0007，
因此 `supersedes` 必须为空。

如果“每批 25 条”只是当前客户端的性能调优值，它只进入任务记录。若新
实现仅落实 D-0007，则复用 D-0007 并记录真实使用证据，不创建同义卡。若
仅实现路径重命名而结论不变，则更新 D-0007 的范围并保留 `scope_history`。
只有事务保证、交付语义或依赖边界等长期结论真正变化时，才创建替代卡并
用 `supersedes` 指向 D-0007。
